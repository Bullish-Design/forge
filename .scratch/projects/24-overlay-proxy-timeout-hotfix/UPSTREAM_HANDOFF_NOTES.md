# Upstream Handoff Notes

Intended upstream changes:
- Add `api_proxy_timeout_s` in forge-overlay config model.
- Add `--api-proxy-timeout-s` and `FORGE_API_PROXY_TIMEOUT_S` in CLI.
- Use configured timeout in `httpx.AsyncClient(timeout=...)`.
- Return a specific error payload for timeout conditions.

Follow-up from forge repo:
- [x] Add forge config field for overlay proxy timeout (`overlay_api_proxy_timeout_s`, default `600.0`).
- [x] Pass through to forge-overlay invocation (`--api-proxy-timeout-s`).
