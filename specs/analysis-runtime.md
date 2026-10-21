# Persistent research analysis runtime

- **AR-001 — Stable task Python.** EM-Agent task shells default to a locked,
  persistent analysis environment. Explicit project virtual environments win.
  Agent Server, automation and science services keep their original Python.
- **AR-002 — Real skill discovery.** At Claude ACP startup, project only the
  enabled OpenHands user AgentSkills into Claude's native user skill directory.
  Preserve native user skills and remove only links owned by this integration.
  Canvas skill preferences remain the owner of enablement; new sessions refresh.
- **AR-003 — Discoverable environment.** New conversations receive the verified
  analysis interpreter, installed package versions and scientific CLI locations
  through existing runtime-service metadata. The same inventory is available
  via `em-env`; PDF text extraction and page rendering work as the runtime user.
- **AR-004 — Reproducible deployment.** Pin and lock analysis dependencies in a
  separate runtime, validate it before image switching, mount it read-only, and
  preserve workspaces and Claude state across recreation and rollback.
