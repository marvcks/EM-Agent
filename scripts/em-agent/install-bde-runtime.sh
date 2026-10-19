#!/usr/bin/env bash
# Run on huoshan as the tool administrator. Never changes Agent Server Python.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
runtime=/opt/em-agent-tools/bde
management=/root/EM-Agent-Tools/bde
if [ -e "$runtime/manifest.json" ]; then
  echo 'BDE is already installed; inspect its manifest and validation before changing it.' >&2
  exit 1
fi
mkdir -p "$runtime/models" "$management/installers" "$management/logs" "$management/validation"
cp "$repo_root/tools/science_apps/runtime/bde/"{pyproject.toml,uv.lock,psi4-linux-64.lock} "$runtime/"
uv_bin=${UV_BIN:-/root/.local/bin/uv}
UV_PYTHON_INSTALL_DIR=/opt/em-agent-tools/python "$uv_bin" python install 3.11.15
(cd "$runtime" && "$uv_bin" sync --frozen --python /opt/em-agent-tools/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3)
installer="$management/installers/micromamba-2.3.2.tar.bz2"
curl -fL --retry 3 'https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/linux-64/micromamba-2.3.2-0.tar.bz2' -o "$installer"
printf '%s  %s\n' '5512233cdd8564a671626081026dc861537a963baa06706baab08fac6f3bb9d2' "$installer" | sha256sum -c -
tar -xjf "$installer" -C "$management" bin/micromamba
"$management/bin/micromamba" create -y -r "$management/mamba" -p "$runtime/psi4" --file "$runtime/psi4-linux-64.lock"
git clone 'https://github.com/NREL/alfabet.git' "$runtime/source"
git -C "$runtime/source" checkout 991aaa2b35245d2f2a648cf63e5304cc661eb395
for model_file in model.tar.gz preprocessor.json; do
  curl -fL --retry 3 "https://github.com/pstjohn/alfabet-models/releases/download/v0.1.1/$model_file" -o "$runtime/models/$model_file"
done
(cd "$runtime/models" && printf '%s\n' \
 'f1c2b9436f2d18c76b45d95140e6a08c096250bd5f3e2b412492ca27ab38ad0c  model.tar.gz' \
 '412d15ca4d0e8b5030e9b497f566566922818ff355b8ee677a91dd23696878ac  preprocessor.json' | sha256sum -c -)
tar -xzf "$runtime/models/model.tar.gz" -C "$runtime/models" --no-same-owner
mv "$runtime/models/output_model" "$runtime/models/model"
chmod -R a+rX "$runtime/models/model"
"$uv_bin" pip check --python "$runtime/.venv/bin/python"
"$runtime/psi4/bin/python" -c 'import psi4; print(psi4.__version__)'
"$runtime/.venv/bin/python" - <<'PY'
import hashlib, json
from pathlib import Path
root = Path('/opt/em-agent-tools/bde')
manifest = {'tool': 'EM-Agent BDE', 'source': 'https://github.com/NREL/alfabet',
    'source_commit': '991aaa2b35245d2f2a648cf63e5304cc661eb395',
    'model_release': 'https://github.com/pstjohn/alfabet-models/releases/tag/v0.1.1',
    'psi4_version': '1.10.2', 'psi4_pins': {'einsums': '1.1.3', 'libxc-c': '7.0.0'},
    'reference': 'https://www.nature.com/articles/s41467-020-16201-z',
    'model_sha256': {name: hashlib.sha256((root / 'models' / name).read_bytes()).hexdigest()
                     for name in ('model.tar.gz', 'preprocessor.json')}}
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
printf '%s\n' 'Runtime installed. Complete host and target-image scientific validation before deploying.'
