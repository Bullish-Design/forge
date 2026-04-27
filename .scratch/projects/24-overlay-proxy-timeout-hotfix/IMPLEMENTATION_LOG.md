# Implementation Log

Date: 2026-04-27

## Implemented (directly in devenv-installed forge-overlay)

Target package path:
`/home/andrew/Documents/Projects/forge/.devenv/state/venv/lib/python3.13/site-packages/forge_overlay`

Modified files:

1. `config.py`
- Added new config field:
  - `api_proxy_timeout_s: float = 600.0`

2. `main.py`
- Added new CLI/env option:
  - `--api-proxy-timeout-s`
  - env: `FORGE_API_PROXY_TIMEOUT_S`
  - default: `600.0`
- Wired option into `Config(...)`.

3. `app.py`
- Changed HTTP client construction from:
  - `httpx.AsyncClient()`
- To:
  - `httpx.AsyncClient(timeout=httpx.Timeout(config.api_proxy_timeout_s))`

4. `proxy.py`
- Added timeout-specific error mapping:
  - `httpx.TimeoutException` -> HTTP `504` with `{ "error": "upstream_timeout" }`
- Kept generic upstream failure mapping:
  - `httpx.HTTPError` -> HTTP `502` with `{ "error": "upstream_unavailable" }`

## Validation results

- `forge-overlay --help` now shows:
  - `--api-proxy-timeout-s`
  - env var `FORGE_API_PROXY_TIMEOUT_S`
  - default `600.0`

- Python import/config check passed:
  - `Config(api_proxy_timeout_s=777.0)` constructs correctly.
  - `create_app(Config(...))` builds successfully.

## Important finding during live check

`/api/agent/apply` through overlay still returned 502 in current stack, but logs show the immediate backend failure is now:

- `obsidian_ops.errors.VCSError: jj binary not found: jj`

So the current apply failure is currently dominated by missing `jj` in runtime PATH, not purely proxy timeout.

## Recommendation for upstream overlay developers

- Accept the timeout configurability patch as-is (or with naming adjustments).
- Keep timeout and generic upstream errors distinct (`upstream_timeout` vs `upstream_unavailable`) for better UX/diagnostics.
