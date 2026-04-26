# CONTEXT

## What Was Done

- Reviewed Forge CLI/server/ops internals to anchor container guidance in actual code behavior:
  - `internal/cli/dev.go`
  - `internal/server/mux.go`
  - `internal/server/server.go`
  - `internal/ops/handler.go`
  - `internal/ops/agent.go`
  - `internal/ops/jj.go`
  - `internal/builder/utils.go`
  - `internal/overlay/inject.go`
- Confirmed that `forge dev` already includes:
  - build + watch + serve loop,
  - `/api/apply`, `/api/undo`, `/api/health` Ops endpoints,
  - overlay injection support (`/ops/ops.css`, `/ops/ops.js`).
- Confirmed `jj` is operationally important for Ops mutation lifecycle.
- Implemented container/runtime files in repo root:
  - `Dockerfile`
  - `docker/entrypoint.sh`
  - `docker-compose.yml`
  - `.env.example`
  - `.dockerignore`
  - `docker/README.md`
- Validation run:
  - `bash -n docker/entrypoint.sh` passed.
  - `docker compose config` passed (warned only that `TS_AUTHKEY` is unset in current shell).

## Why This Matters

- The container design must preserve writable vault/output volumes, include `jj`, and expose Forge via a Tailscale sidecar network namespace.
- Missing `jj` causes apply flow degradation (warning + no rebuild step after mutation commit failure).

## Next Action If Continued

- Optional polish: add a dedicated docs page linking container workflow from `README.md` and deployment docs.
