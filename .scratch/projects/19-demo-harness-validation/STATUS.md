# Status

## 2026-04-26

- Project scaffold created.
- Demo harness assets and scripts implemented:
  - `demo/vault-template/*`
  - `demo/overlay/ops.js`, `demo/overlay/ops.css`
  - `demo/tools/dummy_api_server.py`
  - `demo/scripts/setup.sh`, `start_stack.sh`, `validate_full_stack.sh`, `cleanup.sh`
- Optional pytest integration added in `tests/test_demo_harness.py` (gated by `FORGE_RUN_DEMO_VALIDATION=1`).
- Validation evidence:
  - `devenv shell -- pytest -q` passed (demo integration test skipped by default)
  - `devenv shell -- demo/scripts/validate_full_stack.sh` passed end-to-end in escalated mode.
- Notable hardening included:
  - startup port-collision checks
  - log-based kiln initial-build readiness gate
  - rebuild webhook verification via overlay logs
  - deterministic apply/undo mutation assertions
- Next: implement the interactive step-by-step walkthrough script on top of this validated harness.
