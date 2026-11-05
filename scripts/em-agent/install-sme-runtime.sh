#!/usr/bin/env bash
# Prepare the isolated SME inference runtime (PyTorch CPU + RDKit).
# Model checkpoints and manifest.json are produced by scripts/em-agent/sme_train.py.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
runtime=${1:-/opt/em-agent-tools/sme}
interpreter=${2:-/opt/em-agent-tools/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3}
uv_bin=${UV_BIN:-uv}
test -x "$interpreter"
mkdir -p "$runtime/models" "$runtime/data"
cp "$repo_root/tools/science_apps/runtime/sme/pyproject.toml" "$runtime/pyproject.toml"
cp "$repo_root/tools/science_apps/runtime/sme/uv.lock" "$runtime/uv.lock"
if [ ! -x "$runtime/.venv/bin/python" ]; then
  "$uv_bin" venv --python "$interpreter" "$runtime/.venv"
fi
if [ -n "${SME_MIRROR:-}" ]; then
  # Domestic transport for the same locked versions (torch 2.5.1+cpu, rdkit
  # 2024.9.6, numpy 1.26.4); the lock file still defines the expected versions.
  torch_wheel=${SME_TORCH_WHEEL:-https://mirrors.aliyun.com/pytorch-wheels/cpu/torch-2.5.1%2Bcpu-cp311-cp311-linux_x86_64.whl}
  "$uv_bin" pip install --python "$runtime/.venv/bin/python" \
    --index-url "${SME_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}" \
    "$torch_wheel" "rdkit==2024.9.6" "numpy==1.26.4"
else
  "$uv_bin" sync --frozen --no-dev --project "$runtime" --python "$interpreter"
fi
"$uv_bin" pip check --python "$runtime/.venv/bin/python"
"$runtime/.venv/bin/python" - "$runtime" <<'PY'
import hashlib, json, platform, sys
from pathlib import Path
import numpy, rdkit, torch
root = Path(sys.argv[1])
manifest = {'python': platform.python_version(),
            'lock_sha256': hashlib.sha256((root / 'uv.lock').read_bytes()).hexdigest(),
            'packages': {'torch': torch.__version__, 'rdkit': rdkit.__version__,
                         'numpy': numpy.__version__}}
(root / 'runtime.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest))
PY
