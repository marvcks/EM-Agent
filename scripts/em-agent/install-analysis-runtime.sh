#!/usr/bin/env bash
# Install once on huoshan at the final container-visible prefix.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
runtime=/opt/em-agent-tools/analysis
management=/root/EM-Agent-Tools/analysis
if [ -e "$runtime/manifest.json" ]; then
  echo 'Analysis runtime already exists; inspect its manifest before changing it.' >&2
  exit 1
fi
mkdir -p "$runtime" "$management/logs" "$management/validation"
cp "$repo_root/tools/em_agent_runtime/pyproject.toml" "$repo_root/tools/em_agent_runtime/uv.lock" "$runtime/"
uv_bin=${UV_BIN:-/root/.local/bin/uv}
analysis_python=/opt/em-agent-tools/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3
test -x "$analysis_python"
(cd "$runtime" && "$uv_bin" sync --frozen --python "$analysis_python" --no-dev)
"$uv_bin" pip check --python "$runtime/.venv/bin/python"
"$runtime/.venv/bin/python" "$repo_root/tools/em_agent_runtime/runtime.py" manifest
chmod -R a+rX "$runtime"
echo "Installed persistent analysis runtime: $runtime"
