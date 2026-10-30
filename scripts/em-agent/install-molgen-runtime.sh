#!/usr/bin/env bash
# Rebuild the isolated ChemTSv3 molecular-generation runtime from the committed lock.
# The migration package must already be extracted to $runtime/app (read-only source).
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
runtime=${1:-/opt/em-agent-tools/molgen}
interpreter=${2:-/opt/em-agent-tools/python/cpython-3.11.11-linux-x86_64-gnu/bin/python3}
uv_bin=${UV_BIN:-uv}
test -x "$interpreter"
test -f "$runtime/app/config/setting.yaml"
test -f "$runtime/app/engine/ChemTSv3/chemtsv3/cli/generation.py"
mkdir -p "$runtime"
cp "$repo_root/tools/science_apps/runtime/molgen/pyproject.toml" "$runtime/pyproject.toml"
cp "$repo_root/tools/science_apps/runtime/molgen/uv.lock" "$runtime/uv.lock"
"$uv_bin" sync --frozen --no-dev --project "$runtime" --python "$interpreter"
"$uv_bin" pip install --no-deps --python "$runtime/.venv/bin/python" -e "$runtime/app/engine/ChemTSv3"
"$uv_bin" pip check --python "$runtime/.venv/bin/python"
"$runtime/.venv/bin/python" - "$runtime" <<'PY'
import csv, hashlib, json, os, platform, sys
from importlib.metadata import version
from pathlib import Path
root = Path(sys.argv[1])
app = root / 'app'

def sha(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()

source_zip = os.environ.get('MOLGEN_SOURCE_ZIP', '')
if source_zip:
    package_sha = sha(Path(source_zip))
    package_name = Path(source_zip).name
else:
    sidecar = root / 'source-package.sha256'
    if not sidecar.is_file():
        raise SystemExit('Set MOLGEN_SOURCE_ZIP to the verified migration zip')
    package_sha, package_name = sidecar.read_text().split()
app_files = {path.relative_to(app).as_posix(): sha(path)
             for path in sorted(app.rglob('*'))
             if path.is_file() and '__pycache__' not in path.parts}
rollup = hashlib.sha256('\n'.join(f'{name}:{digest}' for name, digest in app_files.items()).encode()).hexdigest()
with (app / 'data_pool/reference_pool/initial_reference_pool.csv').open() as stream:
    pool_rows = sum(1 for _ in csv.DictReader(stream))
manifest = {
    'app_id': 'molgen',
    'python': platform.python_version(),
    'lock_sha256': hashlib.sha256((root / 'uv.lock').read_bytes()).hexdigest(),
    'versions': {name: version(name) for name in
                 ('chemprop', 'torch', 'lightning', 'rdkit', 'numpy', 'pandas', 'scipy',
                  'scikit-learn', 'matplotlib', 'transformers', 'selfies')},
    'app_sha256': rollup,
    'app_files': app_files,
    'models': {path.name: sha(path) for path in sorted((app / 'core/chemprop_model').iterdir())
               if path.is_file()},
    'rnn_files': {path.name: sha(path) for path in sorted((app / 'models/rnn/best').iterdir())
                  if path.is_file()},
    'initial_pool': {'rows': pool_rows,
                     'sha256': sha(app / 'data_pool/reference_pool/initial_reference_pool.csv')},
    'config_template_sha256': sha(app / 'config/setting.yaml'),
    'upstream': {'package_name': package_name, 'package_sha256': package_sha,
                 'engine': 'bundled chemtsv3 1.0.0',
                 'note': 'Pareto_Mul_2 migration package; models and reference pool are the user-supplied files.'},
}
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({key: manifest[key] for key in ('app_id', 'python', 'lock_sha256', 'app_sha256', 'initial_pool')}))
PY
