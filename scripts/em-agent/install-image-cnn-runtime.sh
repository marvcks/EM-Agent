#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
runtime=${1:-/opt/em-agent-tools/image-cnn}
interpreter=${2:-/opt/em-agent-tools/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3}
uv_bin=${UV_BIN:-uv}
test -x "$interpreter"
test -s "$runtime/model.pth"
test -s "$runtime/example.png"
cp "$repo_root/tools/science_apps/runtime/image-cnn/pyproject.toml" "$runtime/pyproject.toml"
cp "$repo_root/tools/science_apps/runtime/image-cnn/uv.lock" "$runtime/uv.lock"
if [ -n "${IMAGE_CNN_INDEX_URL:-}" ]; then
  if [ ! -x "$runtime/.venv/bin/python" ]; then
    "$uv_bin" venv --python "$interpreter" "$runtime/.venv"
  fi
  "$uv_bin" export --frozen --no-dev --no-emit-project --project "$runtime" --format requirements-txt --output-file "$runtime/requirements-locked.txt" > /dev/null
  "$uv_bin" pip sync --require-hashes --python "$runtime/.venv/bin/python" --index-url "$IMAGE_CNN_INDEX_URL" --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match "$runtime/requirements-locked.txt"
else
  "$uv_bin" sync --frozen --no-dev --project "$runtime" --python "$interpreter"
fi
"$uv_bin" pip check --python "$runtime/.venv/bin/python"
"$runtime/.venv/bin/python" - "$runtime" <<'PY'
import hashlib, json, sys
from pathlib import Path
from importlib.metadata import version
import torch, torchvision
root = Path(sys.argv[1])
def digest(name): return hashlib.sha256((root / name).read_bytes()).hexdigest()
assert digest('model.pth') == 'fe02a72c0013edfa32b6075884b1486753fcf56dd1d9fd6cd8c94dcc74085299'
model = torchvision.models.resnet18(weights=None)
model.fc = torch.nn.Linear(model.fc.in_features, 1)
state = torch.load(root/'model.pth', map_location='cpu', weights_only=True)
model.load_state_dict({k.removeprefix('module.'):v for k,v in state.items()}, strict=True)
manifest = {'model_sha256': digest('model.pth'), 'example_sha256': digest('example.png'),
            'lock_sha256': digest('uv.lock'), 'source': 'user image_CN_1030/image_CNN/data/models/cla_5/resnet18_opt1.pth',
            'packages': {n:version(n) for n in ['torch','torchvision','numpy','pillow']}}
(root/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(json.dumps(manifest))
PY
