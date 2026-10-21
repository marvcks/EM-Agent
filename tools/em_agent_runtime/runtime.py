"""EM-Agent deployment helpers; no Agent Server or tool contracts are patched."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

RUNTIME = Path('/opt/em-agent-tools/analysis')
PACKAGES = ('pip', 'numpy', 'scipy', 'pandas', 'matplotlib', 'scikit-learn', 'rdkit',
            'ase', 'spglib', 'pypdf', 'PyMuPDF', 'pdfplumber', 'openpyxl', 'python-docx')
COMMANDS = ('em-mineru', 'em-bde', 'em-magus', 'em-reaction', 'xtb', 'orca', 'g16',
            'pdftotext', 'pdftoppm', 'pdfinfo')


def atomic_json(path, value):
    temporary = path.with_suffix('.next')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def disabled_skills(home):
    path = home / '.openhands/settings.json'
    settings = json.loads(path.read_text()) if path.exists() else {}
    preferences = settings.get('misc_settings', {}).get('app_preferences', {})
    # Canvas preferences own enablement. Only fall back for older deployments.
    disabled = preferences.get('disabled_skills',
        settings.get('agent_settings', {}).get('agent_context', {}).get('disabled_skills', []))
    if not isinstance(disabled, list) or any(not isinstance(name, str) for name in disabled):
        raise ValueError('Invalid disabled_skills; refusing to expose user skills')
    return set(disabled)


# @spec AR-002 — Native ACP skill projection follows the existing preference owner
def sync_claude_skills(home):
    import yaml  # Already provided by the pinned Agent Server image.
    home = Path(home)
    state = home / '.openhands/runtime'
    state.mkdir(parents=True, exist_ok=True)
    native_root = Path(os.environ.get('CLAUDE_CONFIG_DIR') or home / '.claude')
    scope = hashlib.sha256(str(native_root.resolve()).encode()).hexdigest()[:12]
    with (state / 'claude-skills.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        disabled = disabled_skills(home)
        destination = native_root / 'skills'
        destination.mkdir(parents=True, exist_ok=True)
        ownership = state / f'claude-skills-{scope}.json'
        previous = json.loads(ownership.read_text()) if ownership.exists() else {}
        desired = {}
        sources = home / '.openhands/skills'
        for directory in sorted(sources.iterdir()) if sources.is_dir() else []:
            skill = directory / 'SKILL.md'
            if not skill.is_file():
                continue
            text = skill.read_text()
            match = re.match(r'\A---\s*\n(.*?)\n---(?:\s*\n|\Z)', text, re.S)
            if not match:
                continue
            metadata = yaml.safe_load(match.group(1))
            name = metadata.get('name') if isinstance(metadata, dict) else None
            if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name):
                continue
            if name not in disabled:
                desired[name] = str(directory.resolve())
        owned = {}
        for name, target in previous.items():
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name):
                raise ValueError('Invalid skill ownership record')
            link = destination / name
            if link.is_symlink() and os.readlink(link) == target:
                if desired.get(name) == target:
                    owned[name] = target
                else:
                    link.unlink()
        for name, target in desired.items():
            link = destination / name
            if name in owned:
                continue
            if link.exists() or link.is_symlink():
                print(f'Preserving native Claude skill: {name}', file=sys.stderr)
                continue
            link.symlink_to(target, target_is_directory=True)
            owned[name] = target
        atomic_json(ownership, owned)
        return sorted(owned)


def package_inventory():
    from importlib.metadata import version
    return {'python': sys.version.split()[0], 'executable': sys.executable,
            'packages': {name: version(name) for name in PACKAGES}}


# @spec AR-003 — Inventory is taken from the actual analysis interpreter
def inventory(root):
    python = root / '.venv/bin/python'
    result = subprocess.run([str(python), str(Path(__file__).resolve()), 'packages'],
                            check=True, capture_output=True, text=True, timeout=30)
    result = json.loads(result.stdout)
    result['runtime'] = str(root)
    result['commands'] = {name: path for name in COMMANDS if (path := shutil.which(name))}
    return result


def environment_description(root):
    info = inventory(root)
    packages = ', '.join(f'{name} {version}' for name, version in info['packages'].items())
    commands = ', '.join(f'{name}={path}' for name, path in info['commands'].items())
    return (
        f'Research task environment: Python {info["python"]} at {info["executable"]}. '
        f'Task shells select this persistent environment unless an explicit project venv is active. '
        f'Installed packages: {packages}. Available commands: {commands}. '
        'Run em-env --json to inspect the current inventory. Use existing packages before installing. '
        'This analysis environment and scientific runtimes are read-only; create a project .venv for extra dependencies. '
        'Use em-mineru for scientific PDF/Word extraction; pdftotext and pdftoppm provide local PDF text/rendering. '
        'Scientific em-* CLIs use the shared science queue; do not bypass it with direct runner execution. '
        'On Claude Code, enabled OpenHands user AgentSkills are registered in the native Skill tool at session startup; '
        'use Skill for those skills. On OpenHands use invoke_skill. '
        'Agent Server and other services retain their separate Python environment.'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', default='describe', choices=['describe', 'packages', 'manifest', 'sync-claude-skills'])
    parser.add_argument('--runtime', type=Path, default=RUNTIME)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.command == 'packages':
        print(json.dumps(package_inventory()))
    elif args.command == 'sync-claude-skills':
        sync_claude_skills(Path.home())
    elif args.command == 'manifest':
        data = inventory(args.runtime)
        data['lock_sha256'] = hashlib.sha256((args.runtime / 'uv.lock').read_bytes()).hexdigest()
        atomic_json(args.runtime / 'manifest.json', data)
    else:
        print(json.dumps(inventory(args.runtime), ensure_ascii=False, indent=2) if args.json else environment_description(args.runtime))


if __name__ == '__main__':
    main()
