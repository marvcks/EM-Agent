#!/usr/bin/env python3
"""Deploy a commit-labelled EM-Agent image on the existing huoshan Compose stack."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

SOURCE = 'https://github.com/marvcks/EM-Agent'
UPSTREAM_REVISION = 'f07aebdf5cdd71f4a05ebcf30f8bef5e4e3b70b9'
FRONTEND = '/opt/agent-canvas/frontend'
STATE_DIRS = {
    'workspace': '/home/openhands/workspace',
    'browser-config': '/home/openhands/.config',
    'editor-state': '/home/openhands/.openvscode-server',
}
PROBE = '''
import json, os, urllib.request, urllib.parse
headers = {'X-Session-API-Key': os.environ['LOCAL_BACKEND_API_KEY']}
items, page = [], None
while True:
    query = '?' + urllib.parse.urlencode({'page_id': page}) if page else ''
    request = urllib.request.Request('http://127.0.0.1:8000/api/conversations/search' + query, headers=headers)
    result = json.load(urllib.request.urlopen(request, timeout=15))
    items.extend({'id': x['id'], 'status': x.get('execution_status')} for x in result.get('items', []))
    page = result.get('next_page_id')
    if not page: break
print(json.dumps(items))
'''
VERIFY_FILES = '''
import hashlib, json, os
from pathlib import Path
expected = json.load(__import__('sys').stdin)
root = Path('/home/openhands/workspace')
bad = []
for name, value in expected.items():
    p = root / name
    actual = ('link:' + os.readlink(p)) if p.is_symlink() else (hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
    if actual != value: bad.append(name)
print(json.dumps({'checked': len(expected), 'mismatches': bad}))
if bad: raise SystemExit(1)
'''


def run(*args, input=None):
    result = subprocess.run(args, input=input, capture_output=True, text=True)
    if result.returncode:
        # Commands never contain credentials; avoid printing captured API data.
        raise RuntimeError(f'Command failed: {args[:4]}\n{result.stderr[-2000:]}')
    return result.stdout


def render_compose(original, image_id, remove_frontend=True):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id):
        raise ValueError('Expected an immutable local image ID')
    if len(re.findall(r'^    image:.*$', original, flags=re.M)) != 1:
        raise ValueError('Expected exactly one Compose service image')
    result = re.sub(r'^    image:.*$', f'    image: {image_id}', original, flags=re.M)
    if remove_frontend:
        result = re.sub(r'^      - [^\n]*:' + re.escape(FRONTEND) + r'(?::ro)?\n', '', result, flags=re.M)
    if result.count('    volumes:\n') != 1:
        raise ValueError('Expected one service volume list')
    additions = []
    for name, destination in STATE_DIRS.items():
        line = f'      - ./{name}:{destination}\n'
        if line not in result:
            if destination in result:
                raise ValueError(f'Another mount owns {destination}')
            additions.append(line)
    return result.replace('    volumes:\n', '    volumes:\n' + ''.join(additions))


def atomic_write(path, content):
    temporary = path.with_suffix(path.suffix + '.next')
    temporary.write_text(content)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def file_manifest(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            result[path.relative_to(root).as_posix()] = 'link:' + os.readlink(path)
        elif path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def check_idle():
    conversations = json.loads(run('docker', 'exec', 'openhands', 'python', '-c', PROBE))
    active = [item['id'] for item in conversations if item['status'] == 'running']
    if active:
        raise RuntimeError(f'Conversations are running; retry when idle: {active}')
    return conversations


def wait_healthy(timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = run('docker', 'inspect', 'openhands', '--format', '{{.State.Health.Status}}').strip()
        if status == 'healthy':
            return
        time.sleep(2)
    raise RuntimeError('Container did not become healthy before the deadline')


def verify_restored(conversations, manifest):
    current = json.loads(run('docker', 'exec', 'openhands', 'python', '-c', PROBE))
    if not {item['id'] for item in conversations}.issubset({item['id'] for item in current}):
        raise RuntimeError('A previous conversation is missing')
    return json.loads(run('docker', 'exec', '-i', 'openhands', 'python', '-c', VERIFY_FILES, input=json.dumps(manifest)))


def deploy(root, image, commit):
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Provide a full 40-character source commit')
    info = json.loads(run('docker', 'image', 'inspect', image))[0]
    labels = info['Config']['Labels']
    if (labels.get('org.opencontainers.image.source') != SOURCE
            or labels.get('org.opencontainers.image.revision') != commit
            or labels.get('io.em-agent.upstream.revision') != UPSTREAM_REVISION):
        raise ValueError('Image provenance does not match this fork and commit')
    previous = json.loads(run('docker', 'inspect', 'openhands'))[0]
    # This deployer intentionally keeps the existing 1.27.1 backend and schema.
    old_labels = previous['Config']['Labels']
    if old_labels.get('io.em-agent.upstream.revision', old_labels.get('org.opencontainers.image.revision')) != UPSTREAM_REVISION:
        raise ValueError('Existing backend is not the supported 1.27.1 runtime')
    mounts = {m['Destination']: Path(m['Source']).resolve() for m in previous['Mounts']}
    for name, destination in STATE_DIRS.items():
        if destination in mounts and mounts[destination] != (root / name).resolve():
            raise ValueError(f'Another host directory owns {destination}')
        if destination not in mounts and (root / name).exists():
            raise ValueError(f'{root / name} exists without a matching mount')
    conversations = check_idle()
    release = root / 'image-releases' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + commit[:12])
    release.mkdir(parents=True, mode=0o700)
    compose = root / 'compose.yaml'
    original = compose.read_text()
    (release / 'compose-original.yaml').write_text(original)
    candidate = render_compose(original, info['Id'])
    fallback = render_compose(original, previous['Image'], remove_frontend=False)
    atomic_write(release / 'compose-candidate.yaml', candidate)
    atomic_write(release / 'compose-rollback.yaml', fallback)

    def compose_run(*args, file=compose):
        return run('docker', 'compose', '--project-directory', str(root), '-f', str(file), *args)

    compose_run('config', '--quiet', file=release / 'compose-candidate.yaml')
    compose_run('config', '--quiet', file=release / 'compose-rollback.yaml')
    print(f'Validated image {info["Id"]}; preserving {len(conversations)} conversations', flush=True)
    stopped, switched = False, False
    manifest = {}
    try:
        # Recheck immediately before stopping, including any task started during validation.
        conversations = check_idle()
        compose_run('stop', '--timeout', '30', 'canvas')
        stopped = True
        for name, destination in STATE_DIRS.items():
            if destination not in mounts:
                run('docker', 'cp', '-a', f'openhands:{destination}', str(root / name))
        manifest = file_manifest(root / 'workspace')
        (release / 'workspace-sha256.json').write_text(json.dumps(manifest, sort_keys=True))
        shutil.copytree(root / 'data', release / 'data-backup', symlinks=True)
        atomic_write(compose, candidate)
        switched = True
        compose_run('up', '-d', '--no-deps', '--force-recreate', '--pull', 'never', 'canvas')
        wait_healthy()
        restored = verify_restored(conversations, manifest)
        record = {
            'source': SOURCE, 'revision': commit, 'image_tag': image, 'image_id': info['Id'],
            'previous_image_id': previous['Image'], 'conversations': len(conversations),
            'workspace_verification': restored, 'rollback_compose': str(release / 'compose-rollback.yaml'),
        }
        atomic_write(release / 'release.json', json.dumps(record, indent=2) + '\n')
        atomic_write(root / 'current-image.json', json.dumps(record, indent=2) + '\n')
        print(json.dumps({'deployed': commit, 'image_id': info['Id'], 'release_dir': str(release), 'verification': restored}), flush=True)
    except Exception:
        if switched:
            atomic_write(compose, fallback)
            compose_run('up', '-d', '--no-deps', '--force-recreate', '--pull', 'never', 'canvas')
            wait_healthy()
            verify_restored(conversations, manifest)
            print('Deployment failed; previous image and persistent workspaces restored', flush=True)
        elif stopped:
            compose_run('start', 'canvas')
        raise


def rollback(root, release):
    release = release.resolve()
    if not release.is_relative_to(root / 'image-releases'):
        raise ValueError('Rollback must use an image release under the deployment root')
    conversations = check_idle()
    manifest = file_manifest(root / 'workspace')
    content = (release / 'compose-rollback.yaml').read_text()
    atomic_write(root / 'compose.yaml', content)
    run('docker', 'compose', '--project-directory', str(root), '-f', str(root / 'compose.yaml'),
        'up', '-d', '--no-deps', '--force-recreate', '--pull', 'never', 'canvas')
    wait_healthy()
    verify_restored(conversations, manifest)
    image = json.loads(run('docker', 'inspect', 'openhands'))[0]
    atomic_write(root / 'current-image.json', json.dumps({'rolled_back_from': str(release), 'image_id': image['Image'], 'revision': image['Config']['Labels'].get('org.opencontainers.image.revision')}, indent=2) + '\n')
    print('Previous image restored; workspaces and conversation data retained')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/opt/openhands'))
    commands = parser.add_subparsers(dest='command', required=True)
    start = commands.add_parser('deploy')
    start.add_argument('--image', required=True)
    start.add_argument('--commit', required=True)
    back = commands.add_parser('rollback')
    back.add_argument('release', type=Path)
    args = parser.parse_args()
    if args.command == 'deploy':
        deploy(args.root.resolve(), args.image, args.commit)
    else:
        rollback(args.root.resolve(), args.release)


if __name__ == '__main__':
    main()
