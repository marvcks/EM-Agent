#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
runtime=${1:-/opt/em-agent-tools/cnt2d}
interpreter=${2:-/opt/em-agent-tools/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3}
uv_bin=${UV_BIN:-uv}
test -x "$interpreter"
mkdir -p "$runtime"
cp "$repo_root/tools/science_apps/runtime/cnt2d/pyproject.toml" "$runtime/pyproject.toml"
cp "$repo_root/tools/science_apps/runtime/cnt2d/uv.lock" "$runtime/uv.lock"
if [ -n "${CNT2D_INDEX_URL:-}" ]; then
  # Alternate transport for exactly the locked versions/artifact hashes.
  if [ ! -x "$runtime/.venv/bin/python" ]; then
    "$uv_bin" venv --python "$interpreter" "$runtime/.venv"
  fi
  "$uv_bin" export --frozen --no-dev --no-emit-project --project "$runtime" \
    --format requirements-txt --output-file "$runtime/requirements-locked.txt" > /dev/null
  "$uv_bin" pip sync --require-hashes --python "$runtime/.venv/bin/python" \
    --index-url "$CNT2D_INDEX_URL" "$runtime/requirements-locked.txt"
else
  "$uv_bin" sync --frozen --no-dev --project "$runtime" --python "$interpreter"
fi
"$uv_bin" pip check --python "$runtime/.venv/bin/python"
"$runtime/.venv/bin/python" - "$runtime" <<'PY'
from importlib.metadata import version
import hashlib, json, platform, sys
from pathlib import Path
import gmsh, numpy, scipy, skfem, meshio, matplotlib
root = Path(sys.argv[1])
manifest = {'python': platform.python_version(),
            'lock_sha256': hashlib.sha256((root / 'uv.lock').read_bytes()).hexdigest(),
            'packages': {name: version(name) for name in
                         ('gmsh','numpy','scipy','scikit-fem','meshio','matplotlib')}}
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest))
PY
