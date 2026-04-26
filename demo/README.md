# Forge v2 Interactive Demo

This demo runs a live local stack that showcases:

- Kiln static-site capabilities from a realistic Obsidian-style vault
- `kiln-fork` watch mode with `--no-serve` and `--on-rebuild`
- `forge-overlay` HTML injection, `/ops/events` SSE updates, and `/api/*` proxying
- Deterministic dummy LLM-style API responses (no external model calls)

The site is served at `http://127.0.0.1:18080/index.html` during validation.

## Test-First Validation (Do This First)

Run from the `forge` repo root:

```bash
devenv shell -- uv run demo/scripts/validate_full_stack.py
# equivalent entrypoint:
devenv shell -- uv run forge-demo-validate
```

## Interactive Walkthrough

Run the keypress-driven walkthrough script:

```bash
devenv shell -- uv run demo/scripts/run_demo.py
# equivalent entrypoint:
devenv shell -- uv run forge-demo-run
```

The script keeps the site live during each step and pauses for operator progression.
Set `AUTO_ADVANCE=1` for non-interactive execution.

## Free-Explore Demo (Real vLLM Backend)

Runs the same UI stack, but API interactivity routes through a real vLLM endpoint.

```bash
devenv shell -- uv run demo/scripts/run_free_explore.py
# equivalent entrypoint:
devenv shell -- uv run forge-demo-run-free-explore
```

By default this targets `http://remora-server:8000/v1`.
Optional overrides:
- `DEMO_VLLM_BASE_URL` (default `http://remora-server:8000/v1`)
- `DEMO_VLLM_MODEL` (default: auto-detect first model from `/v1/models`)
- `DEMO_VLLM_TIMEOUT_S` (default `60`)

## Stable Setup/Cleanup Commands

```bash
devenv shell -- uv run demo/scripts/setup.py
devenv shell -- uv run demo/scripts/start_stack.py
devenv shell -- uv run demo/scripts/cleanup.py
# equivalent entrypoints:
devenv shell -- uv run forge-demo-setup
devenv shell -- uv run forge-demo-start
devenv shell -- uv run forge-demo-cleanup
devenv shell -- uv run forge-demo-start-free-explore
```

`setup.py` always resets the demo runtime to a known state.
`start_stack.py` boots real local processes against localhost.
`cleanup.py` stops all demo processes and removes runtime artifacts.
Each wrapper calls a same-named `.sh` file that stays intentionally small and easy to inspect.

To inspect live output manually after `start_stack.py`, open:

```text
http://127.0.0.1:18080/index.html
```

## Optional Environment Overrides

- `DEMO_OVERLAY_PORT` (default `18080`)
- `DEMO_API_PORT` (default `18081`)
- `KILN_BIN` (default: `/home/andrew/Documents/Projects/kiln-fork/kiln` if present, else `kiln`)
- `FORGE_OVERLAY_PROJECT_DIR` (default `/home/andrew/Documents/Projects/forge-overlay`)
## What `validate_full_stack.py` Asserts

1. Real stack boot order and health: dummy API -> overlay -> kiln watcher.
2. Kiln watcher process includes `--no-serve` and `--on-rebuild`.
3. Overlay injection is present (`/ops/ops.css`, `/ops/ops.js` in served HTML).
4. Rebuild webhook delivery is confirmed (`POST /internal/rebuild` -> `204`) after real vault mutation.
5. `/api/health`, `/api/agent/apply`, and `/api/undo` work through overlay proxy.
6. Sync endpoints (`ensure`, `remote`, `sync`, `status`) work through overlay proxy.
7. Apply/undo produce real vault and rendered HTML changes end-to-end.

## Troubleshooting

- `port already in use`: run `uv run demo/scripts/cleanup.py`, then retry.
- Validation needs unsandboxed localhost process interaction in this Codex environment. If sandboxed runs fail on socket operations, rerun with escalated permissions.
