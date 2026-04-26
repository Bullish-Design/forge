# DECISIONS

## D-001: Use `forge dev` as the container command

- Rationale: `forge dev` already combines initial build, file watching, local serving, and Ops API integration.
- Consequence: no need for a separate app stack just to handle rebuilds and API mutations.

## D-002: Use a Tailscale sidecar with shared network namespace

- Rationale: keeps Forge image focused on app concerns while Tailscale handles tailnet identity and routing.
- Consequence: set Forge service `network_mode: service:tailscale` in compose.

## D-003: Treat `jj` as required in runtime image

- Rationale: `/api/apply` attempts `jj describe` + `jj new`; on failure it returns early and skips rebuild.
- Consequence: install `jj` in image and initialize vault as `jj` workspace (`jj git init`) at startup if missing.

## D-004: Persist vault, output, and tailscale state on volumes

- Rationale: maintain markdown source, generated site, `.jj` history, and tailnet identity across restarts.
- Consequence: mount host paths for vault/output; named volume for tailscale state dir.

## D-005: Add local `.dockerignore` and `docker/README.md`

- Rationale: reduce Docker build context size and provide a single operational entrypoint for users.
- Consequence: faster build context transfer and clearer startup instructions.
