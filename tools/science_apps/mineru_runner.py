"""Bounded MinerU cloud adapter. Credentials and signed URLs never enter results."""
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

API_BASE = 'https://mineru.net/api/v4'
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_RESULT_BYTES = 200 * 1024 * 1024
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
TOKEN_NAMES = ('MINERU_API_TOKEN', 'MINERU_TOKEN', 'mineru_key_api')


def token():
    for name in TOKEN_NAMES:
        if os.environ.get(name, '').strip():
            return os.environ[name].strip()
    path = Path(os.environ.get('MINERU_TOKEN_FILE', str(Path.home() / '.openhands/mineru/api-token')))
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def mineru_available():
    return bool(token())


# @spec MINERU-001 — Typed document input, separate from molecular XYZ
def validate_document(name, data):
    if (not name or len(name) > 128 or name in {'.', '..'} or
            any(c in name for c in '/\\\x00\r\n') or any(ord(c) < 32 for c in name)):
        raise ValueError('invalid_document')
    suffix = Path(name).suffix.lower()
    if not 0 < len(data) <= MAX_DOCUMENT_BYTES:
        raise ValueError('invalid_document')
    if suffix == '.pdf' and data.startswith(b'%PDF-'):
        return suffix
    if suffix == '.doc' and data.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
        return suffix
    if suffix == '.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if {'[Content_Types].xml', 'word/document.xml'} <= set(archive.namelist()):
                    return suffix
        except zipfile.BadZipFile:
            pass
    raise ValueError('invalid_document')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # In particular, never forward the API Authorization header elsewhere.
        return None


def open_request(request):
    opener = urllib.request.build_opener(NoRedirect)
    for attempt in range(4):
        try:
            return opener.open(request, timeout=60)
        except urllib.error.HTTPError as exc:
            code = exc.code
            retry = code == 429 or 500 <= code < 600
            after = exc.headers.get('Retry-After', '')
            exc.close()
            if not retry or attempt == 3:
                raise RuntimeError(f'MinerU HTTP {code}; check server credential, quota and network') from None
            delay = min(float(after), 30) if after.isdigit() else min(2 ** attempt, 10)
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 3:
                raise RuntimeError('MinerU network request failed') from None
            delay = min(2 ** attempt, 10)
        time.sleep(delay)
    raise RuntimeError('MinerU request failed')


def api(method, path, payload=None):
    credential = token()
    if not credential:
        raise RuntimeError('MinerU API credential is unavailable')
    request = urllib.request.Request(API_BASE + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer ' + credential, 'Content-Type': 'application/json'})
    with open_request(request) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise RuntimeError('MinerU API response exceeds limit')
    result = json.loads(raw)
    if result.get('code') != 0:
        # Raw upstream messages may contain signed URLs; report only the code.
        raise RuntimeError(f'MinerU API error code {result.get("code")}; check credential, quota or document limits')
    if not isinstance(result.get('data'), dict):
        raise RuntimeError('MinerU API response is incomplete')
    return result['data']


def transfer(method, url, destination=None, source=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid MinerU asset URL')
    request = urllib.request.Request(url, method=method,
        data=source.read_bytes() if source else None,
        headers={'Content-Type': ''} if source else {})
    with open_request(request) as response:
        if destination:
            total = 0
            with destination.open('wb') as stream:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_RESULT_BYTES:
                        raise ValueError('MinerU result exceeds download limit')
                    stream.write(chunk)


# @spec MINERU-003 — Validate before extracting cloud archives
def extract_result(archive_path, root):
    extracted = root / 'extracted'
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 5000 or sum(item.file_size for item in entries) > MAX_EXTRACTED_BYTES:
            raise ValueError('MinerU archive exceeds extraction limits')
        for item in entries:
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename or
                    ':' in item.filename or '\x00' in item.filename or stat.S_ISLNK(mode) or item.flag_bits & 1):
                raise ValueError('Unsafe MinerU archive')
        markdown = [item for item in entries if not item.is_dir() and PurePosixPath(item.filename).name == 'full.md']
        if len(markdown) != 1 or not markdown[0].file_size or markdown[0].file_size > MAX_DOCUMENT_BYTES:
            raise ValueError('MinerU archive lacks a unique nonempty full.md')
        content = archive.read(markdown[0]).decode('utf-8')
        if not content.strip():
            raise ValueError('MinerU Markdown is empty')
        archive.extractall(extracted)
    source = extracted / markdown[0].filename
    shutil.copyfile(source, root / 'document.md')
    return content


# @spec MINERU-002 — Official PDF/Word submission and complete Markdown bundle
def convert(request_path):
    root = request_path.resolve().parent
    config = json.loads(request_path.read_text())
    source = root / ('document' + Path(config['document_name']).suffix.lower())
    validate_document(config['document_name'], source.read_bytes())
    data = api('POST', '/file-urls/batch', {
        'files': [{'name': config['document_name'], 'data_id': 'em-agent'}],
        'model_version': config['method'] or 'vlm', 'language': config['language'],
        'enable_formula': config['enable_formula'], 'enable_table': config['enable_table'],
    })
    batch_id = data['batch_id']
    if not isinstance(batch_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{1,100}', batch_id):
        raise ValueError('MinerU returned an invalid batch ID')
    # The only metadata stored is non-secret task ID/state.
    metadata_path = root / 'mineru-task.json'
    def save(state):
        metadata_path.write_text(json.dumps({'batch_id': batch_id, 'state': state}))
        print('MinerU: ' + state, flush=True)
    save('uploading')
    transfer('PUT', data['file_urls'][0], source=source)
    deadline = time.monotonic() + 840
    previous = None
    while time.monotonic() < deadline:
        data = api('GET', '/extract-results/batch/' + batch_id)
        matches = [item for item in data.get('extract_result', [])
                   if item.get('data_id') == 'em-agent' or item.get('file_name') == config['document_name']]
        if not matches:
            raise RuntimeError('MinerU response does not identify the submitted document')
        result = matches[0]
        state = result.get('state')
        if state not in {'waiting-file', 'pending', 'running', 'converting', 'done', 'failed'}:
            raise RuntimeError('MinerU returned an unknown task state')
        if state != previous:
            save(state)
            previous = state
        if state == 'failed':
            raise RuntimeError('MinerU parsing failed; check document format, page limit and encryption')
        if state == 'done':
            transfer('GET', result['full_zip_url'], destination=root / 'results.zip')
            content = extract_result(root / 'results.zip', root)
            verified = {'verified': True, 'provider': 'MinerU', 'model': config['method'] or 'vlm',
                        'markdown_file': 'document.md', 'markdown_characters': len(content),
                        'bundle_file': 'results.zip', 'source_name': config['document_name']}
            (root / 'result.json').write_text(json.dumps(verified, ensure_ascii=False, indent=2))
            print('EM_AGENT_MINERU_COMPLETE', flush=True)
            return
        time.sleep(5)
    raise RuntimeError('MinerU conversion timed out')


def verified_mineru(result, directory):
    markdown = directory / 'document.md'
    archive = directory / 'results.zip'
    return (result.get('verified') is True and result.get('provider') == 'MinerU' and
            result.get('markdown_file') == 'document.md' and result.get('bundle_file') == 'results.zip' and
            markdown.is_file() and markdown.stat().st_size > 0 and archive.is_file() and
            result.get('markdown_characters') == len(markdown.read_text()) and zipfile.is_zipfile(archive))


if __name__ == '__main__':
    try:
        convert(Path(sys.argv[1]))
    except Exception as exc:
        # Never print arbitrary exception text (network URLs, credentials).
        print(str(exc) if type(exc) is RuntimeError else 'MinerU input or result validation failed', file=sys.stderr)
        sys.exit(1)
