# Plan

1. Add `api_proxy_timeout_s` to forge-overlay runtime config.
2. Add CLI/env support in `forge_overlay.main`.
3. Apply timeout to shared `httpx.AsyncClient` in app startup.
4. Improve proxy error mapping to distinguish timeout from generic upstream failure.
5. Validate with `forge-overlay --help` and runtime checks.
6. Document handoff requirements for upstream repo developers.
