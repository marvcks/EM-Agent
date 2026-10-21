# @spec AR-001 — Only task shells activate analysis; service PATH stays unchanged.
if [ -z "${VIRTUAL_ENV:-}" ] && [ -x "${EM_AGENT_ANALYSIS_ENV:-/opt/em-agent-tools/analysis/.venv}/bin/python" ]; then
  export VIRTUAL_ENV="${EM_AGENT_ANALYSIS_ENV:-/opt/em-agent-tools/analysis/.venv}"
  export PATH="$VIRTUAL_ENV/bin:$PATH"
fi
