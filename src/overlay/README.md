# Production Overlay UI

This directory contains the production overlay assets injected by `forge-overlay`:

- `ops.js`
- `ops.css`

## Features

- Floating trigger button with unread API log badge.
- Modal UI for agent actions (`/api/agent/apply`, `/api/undo`, `/api/health`).
- Live API log capture via client-side `fetch` intercept for `/api/*`.
- Collapsible Global + This Page log groups.
- Per-request detail panels (request/response/error payloads).
- Model/token metadata badges when usage/model fields are present.
- SSE connection status (`/ops/events`).
- Reload button and modal-open persistence via `localStorage`.

## Local Dev

`forge dev` now auto-falls back to this directory when configured `overlay_dir`
does not contain `ops.js` + `ops.css`.

Recommended run:

```bash
devenv shell -- forge dev --config forge.yaml
```

For demo harness with production UI explicitly forced:

```bash
devenv shell -- uv run prod-demo
```

## Docker

Docker compose is wired to:

- `FORGE_OVERLAY_DIR=/app/src/overlay`

Validation includes explicit checks that production overlay assets are served:

```bash
uv run docker/validate.py
```
