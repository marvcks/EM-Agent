#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
runtime=${1:-/opt/em-agent-tools/editretro}
interpreter=${2:-/opt/em-agent-tools/python/cpython-3.10.19-linux-x86_64-gnu/bin/python3}
uv_bin=${UV_BIN:-uv}
upstream_commit=8e5848e899b4e8ec6be970b9be04881042ed7b55
test -x "$interpreter"
mkdir -p "$runtime"
if [ ! -d "$runtime/source" ]; then
  git clone https://github.com/yuqianghan/editretro.git "$runtime/source"
  git -C "$runtime/source" checkout --detach "$upstream_commit"
fi
test "$(git -C "$runtime/source" rev-parse HEAD)" = "$upstream_commit"
if [ ! -f "$runtime/checkpoint_best.pt" ] && [ -n "${EDITRETRO_CHECKPOINT:-}" ]; then
  cp "$EDITRETRO_CHECKPOINT" "$runtime/checkpoint_best.pt"
fi
test -f "$runtime/checkpoint_best.pt"
"$interpreter" "$repo_root/scripts/em-agent/patch-editretro-cpu.py" "$runtime/source"
cp "$repo_root/tools/science_apps/runtime/editretro/pyproject.toml" "$runtime/pyproject.toml"
cp "$repo_root/tools/science_apps/runtime/editretro/uv.lock" "$runtime/uv.lock"
"$uv_bin" sync --frozen --no-dev --project "$runtime" --python "$interpreter"
"$interpreter" "$repo_root/scripts/em-agent/patch-editretro-torch-stack.py" "$runtime"
(
  cd "$runtime/source/fairseq"
  # CPU C++ extensions only; preserve upstream build and model implementation.
  unset CUDA_HOME
  MAX_JOBS=4 "$uv_bin" pip install --python "$runtime/.venv/bin/python" \
    --no-deps --no-build-isolation -e .
)
"$uv_bin" pip check --python "$runtime/.venv/bin/python"
"$runtime/.venv/bin/python" "$repo_root/tools/science_apps/runtime/editretro/write_manifest.py" "$runtime"
