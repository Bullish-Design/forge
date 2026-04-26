# CONTAINER_OVERVIEW

Date: 2026-04-06

## Objective

Package Forge so it can run in Docker with a Tailscale sidecar and continuously build/serve an Obsidian vault, including Ops-driven vault edits through `/api/apply`.

## Forge Behaviors That Drive The Container Design

From the codebase review:

- `forge dev` performs initial build, watches the vault, serves HTTP, and wires Ops API (`internal/cli/dev.go`).
- Ops API endpoints are in-process: `/api/apply`, `/api/undo`, `/api/health` (`internal/ops/handler.go`).
- Overlay injection adds `/ops/ops.css` and `/ops/ops.js` tags into HTML (`internal/overlay/inject.go`).
- Site rebuild is done through `builder.Build` and output is cleaned each build (`internal/builder/builder.go`, `internal/builder/utils.go`).
- Ops mutation lifecycle depends on `jj` commands (`internal/ops/jj.go`).

Important operational detail:

- If `/api/apply` changes files and `jj` commit fails, handler returns warning early and does not run rebuild. In practice, `jj` must be available and initialized for reliable “edit then rebuild” behavior.

## Recommended Runtime Topology

Use two containers in one shared network namespace:

1. `tailscale` sidecar: owns tailnet identity, routing, and control-plane auth.
2. `forge` app: runs `forge dev` and shares `tailscale` network namespace.

Compose pattern:

- `forge.network_mode: "service:tailscale"`
- Mount vault and output volumes into `forge`.
- Mount persistent tailscale state into `tailscale`.

## Volume Layout

- Vault source (read/write): `./vault:/data/vault`
- Generated site output (read/write): `./public:/data/public`
- Overlay assets (read-only): `./static:/app/static:ro`
- Tailscale daemon state (persistent): `tailscale-state:/var/lib/tailscale`

## Suggested Forge Startup Command

```bash
forge dev \
  --input-dir /data/vault \
  --output-dir /data/public \
  --overlay-dir /app/static \
  --inject-overlay \
  --port 8080 \
  --ops-llm-base-url "$OPS_LLM_BASE_URL" \
  --ops-llm-model "$OPS_LLM_MODEL"
```

Notes:

- If `OPS_LLM_BASE_URL` is omitted, Ops falls back to Anthropic API mode and requires `ANTHROPIC_API_KEY`.
- Keep `--ops-api-key` out of plain command lines when possible; prefer env/secret injection.

## Minimal Dockerfile Blueprint

```dockerfile
# syntax=docker/dockerfile:1.7
FROM golang:1.25 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/forge ./cmd/forge

FROM debian:bookworm-slim
WORKDIR /app

# Install runtime tools:
# - ca-certificates + curl: HTTPS for model backends and health checks
# - tini/bash: clean PID1 + shell entrypoint
# - git: required by jj
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates bash tini git curl \
  && rm -rf /var/lib/apt/lists/*

# Install jj (Jujutsu) from GitHub release — not in Debian repos.
# Pin version for reproducibility; bump as needed.
ARG JJ_VERSION=0.28.0
RUN curl -fsSL "https://github.com/jj-vcs/jj/releases/download/v${JJ_VERSION}/jj-v${JJ_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
  | tar -xz -C /usr/local/bin jj

COPY --from=build /out/forge /usr/local/bin/forge
COPY static /app/static
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini","--","/app/entrypoint.sh"]
```

## Entrypoint Blueprint

This ensures a `jj` workspace exists in the mounted vault before running Forge. Uses `--colocate` so a `.git` directory is also created alongside `.jj`, making it easier to inspect state from the host and keeping compatibility if jj is ever swapped out.

```bash
#!/usr/bin/env bash
set -euo pipefail

VAULT_DIR="${VAULT_DIR:-/data/vault}"
OUTPUT_DIR="${OUTPUT_DIR:-/data/public}"
PORT="${PORT:-8080}"
OVERLAY_DIR="${OVERLAY_DIR:-/app/static}"

mkdir -p "$VAULT_DIR" "$OUTPUT_DIR"

if [ ! -d "$VAULT_DIR/.jj" ]; then
  (cd "$VAULT_DIR" && jj git init --colocate)
fi

exec forge dev \
  --input-dir "$VAULT_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --overlay-dir "$OVERLAY_DIR" \
  --inject-overlay \
  --port "$PORT" \
  ${OPS_LLM_BASE_URL:+--ops-llm-base-url "$OPS_LLM_BASE_URL"} \
  ${OPS_LLM_MODEL:+--ops-llm-model "$OPS_LLM_MODEL"} \
  ${OPS_API_KEY:+--ops-api-key "$OPS_API_KEY"}
```

## docker-compose Blueprint (Tailscale Sidecar)

```yaml
services:
  tailscale:
    image: tailscale/tailscale:stable
    container_name: forge-tailscale
    hostname: forge
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY}
      - TS_EXTRA_ARGS=--hostname=forge
      - TS_STATE_DIR=/var/lib/tailscale
    volumes:
      - tailscale-state:/var/lib/tailscale
      - /dev/net/tun:/dev/net/tun
    cap_add:
      - NET_ADMIN
      - NET_RAW
    restart: unless-stopped
    ports:
      - "8080:8080"

  forge:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: forge-app
    depends_on:
      - tailscale
    network_mode: "service:tailscale"
    environment:
      - VAULT_DIR=/data/vault
      - OUTPUT_DIR=/data/public
      - PORT=8080
      - OVERLAY_DIR=/app/static
      - OPS_LLM_BASE_URL=${OPS_LLM_BASE_URL:-}
      - OPS_LLM_MODEL=${OPS_LLM_MODEL:-}
      - OPS_API_KEY=${OPS_API_KEY:-}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
    volumes:
      - ./vault:/data/vault
      - ./public:/data/public
      - ./static:/app/static:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://127.0.0.1:8080/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped

volumes:
  tailscale-state:
```

## Tailscale Address

The sidecar is configured so the device appears on the tailnet as `forge`. This is set via both `hostname: forge` (container hostname) and `TS_EXTRA_ARGS=--hostname=forge` (tailscale device name). Once connected, the app is reachable at `http://forge:8080` from any device on the tailnet, or via the MagicDNS FQDN `forge.<tailnet-name>.ts.net`.

## How Vault Building Happens In This Stack

1. Forge starts in `dev` mode and performs a full build from `/data/vault` to `/data/public`.
2. File watcher tracks vault changes and triggers incremental rebuilds.
3. Overlay UI calls `/api/apply`.
4. Agent reads/writes vault files.
5. `jj` snapshots change.
6. Forge rebuilds output.
7. Tailnet users access the site/API through the sidecar network namespace.

## Security And Reliability Notes

- Treat `TS_AUTHKEY`, `OPS_API_KEY`, and `ANTHROPIC_API_KEY` as secrets; inject via env file or secret manager.
- Restrict vault mount path to only the intended Obsidian directory.
- Keep tailscale state persistent; ephemeral state forces re-auth each restart.
- Add an app health check against `http://127.0.0.1:8080/api/health`.
- Pin image versions for reproducibility after initial validation.

## Validation Checklist

- `curl http://127.0.0.1:8080/api/health` returns `{"ok":true,...}`.
- Opening home page shows injected overlay assets (`/ops/ops.css`, `/ops/ops.js`).
- Posting `/api/apply` mutates files under `/data/vault` and regenerates `/data/public`.
- `/api/undo` succeeds and rebuilds.
- Container restart preserves `.jj` history and tailscale identity.

## `.env.example` Blueprint

```env
# --- Tailscale ---
# Auth key from https://login.tailscale.com/admin/settings/keys
# Use a reusable, ephemeral key for unattended deploys.
TS_AUTHKEY=tskey-auth-XXXXXXXXXXXX

# --- Ops LLM Backend ---
# Option A: OpenAI-compatible (e.g. local vLLM)
OPS_LLM_BASE_URL=http://remora-server:8000/v1
OPS_LLM_MODEL=
OPS_API_KEY=

# Option B: Anthropic API (leave OPS_LLM_BASE_URL empty)
ANTHROPIC_API_KEY=sk-ant-XXXXXXXXXXXX
```

## Optional Next Implementation Step

Turn this analysis into concrete repo artifacts:

- `Dockerfile`
- `docker/entrypoint.sh`
- `docker-compose.yml`
- `.env.example` (template above)
