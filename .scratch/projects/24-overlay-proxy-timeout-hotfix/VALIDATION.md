# Validation Checklist

- [x] `forge-overlay --help` shows new timeout option.
- [x] Option default is visible and > 5s.
- [x] Env var override works.
- [x] App constructs HTTP client with configured timeout.
- [x] Timeout failures return explicit timeout-flavored error payload.
- [x] Existing non-timeout upstream failures still map to 502 JSON error.

Validated on 2026-05-06:
- `forge-overlay --help` includes `--api-proxy-timeout-s` and env `FORGE_API_PROXY_TIMEOUT_S` with default `600.0`.
- Runtime source inspection confirms timeout wiring in `forge_overlay.app` and error mapping in `forge_overlay.proxy`:
  - timeout -> `504` / `upstream_timeout`
  - generic upstream failure -> `502` / `upstream_unavailable`
