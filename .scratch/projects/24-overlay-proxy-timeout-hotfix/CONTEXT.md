# Context

Goal: remove 5s proxy timeout failures (`{"error":"upstream_unavailable"}`) for long-running `/api/agent/apply` operations.

Scope for this prototype:
- Implement directly in devenv-installed `forge-overlay` package under `.devenv/state/venv/...`.
- Add configurable API proxy timeout (CLI + env + config field).
- Raise default to a practical long-running value suitable for minute-scale LLM calls.
- Keep behavior backward-compatible for existing launch paths.

Out of scope for this prototype:
- Publishing a forge-overlay release.
- Wiring forge.yaml -> forge launcher -> forge-overlay timeout flag.
- Upstream PR in this step.
