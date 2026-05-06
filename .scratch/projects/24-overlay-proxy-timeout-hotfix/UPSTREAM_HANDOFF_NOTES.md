# Upstream Handoff Notes (Draft)

This document will be finalized after implementation is validated.

Intended upstream changes:
- Add `api_proxy_timeout_s` in forge-overlay config model.
- Add `--api-proxy-timeout-s` and `FORGE_API_PROXY_TIMEOUT_S` in CLI.
- Use configured timeout in `httpx.AsyncClient(timeout=...)`.
- Return a specific error payload for timeout conditions.

Follow-up from forge repo:
- Add forge config field for overlay proxy timeout.
- Pass through to forge-overlay invocation.
