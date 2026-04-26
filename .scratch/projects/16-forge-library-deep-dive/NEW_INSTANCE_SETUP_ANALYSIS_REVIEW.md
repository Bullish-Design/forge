# How to Set Up a New Forge Instance: Deep Analysis and Review

## Goal

This guide provides two setup patterns for a new Forge instance:

1. Minimal local instance (static generation + local serve)
2. Full interactive instance (Forge + external API backend via proxy, with Docker stack option)

Both patterns are valid. Choose based on whether you need edit workflows through `/api/*`.

## Setup Pattern A: Minimal Local Instance (Fastest Path)

Use this when you want a static site pipeline first.

### Prerequisites

- Go toolchain available
- Working shell in repository root

### Step A1: Build Forge

```bash
go build -o ./forge ./cmd/forge
```

### Step A2: Initialize a New Vault Structure

```bash
./forge init --input ./vault
```

What this does:

- creates vault directory if missing
- seeds a welcome markdown file
- creates `kiln.yaml` if missing in current directory

### Step A3: Add Content

Add markdown notes under `./vault`, for example:

```bash
cat > ./vault/index.md <<'EOF'
# My Site

Welcome to my Forge instance.
EOF
```

### Step A4: Generate Site Output

```bash
./forge generate --input ./vault --output ./public --name "My Site"
```

### Step A5: Serve Locally

```bash
./forge serve --output ./public --port 8080
```

Open: `http://127.0.0.1:8080`

### Step A6: Validate

- root page renders
- clean URLs work for note pages
- `404.html` appears on missing routes

## Setup Pattern B: Full Interactive Dev Instance (Proxy + Overlay)

Use this when you want overlay UI and `/api/*` edit workflows.

Important architecture fact:

- Forge does not run in-process ops runtime by default in `dev`.
- `/api/*` in Forge dev is proxy-based.
- You must provide a backend with `--proxy-backend` (for example `obsidian-agent`).

### Prerequisites

- Everything from Pattern A
- A running API backend compatible with your overlay/app workflow (e.g. `obsidian-agent`)

### Step B1: Start Backend

Example target endpoint:

`http://127.0.0.1:8081`

Verify:

```bash
curl -fsS http://127.0.0.1:8081/api/health
```

### Step B2: Start Forge Dev with Routing Extensions

```bash
./forge dev \
  --input ./vault \
  --output ./public \
  --port 8080 \
  --overlay-dir ./static \
  --inject-overlay \
  --proxy-backend http://127.0.0.1:8081
```

### Step B3: Validate Routing

```bash
curl -fsS http://127.0.0.1:8080/api/health
curl -I http://127.0.0.1:8080/ops/ops.js
```

Expected:

- `/api/health` responds through proxy
- `/ops/*` serves overlay assets

### Step B4: Validate Watch and Rebuild

1. edit a markdown file in vault
2. wait for rebuild
3. refresh page
4. confirm updated content

Optional SSE check:

```bash
curl -N http://127.0.0.1:8080/ops/events
```

## Setup Pattern C: Dockerized Full Stack Instance

Use this when you want a reproducible service composition with:

- tailscale
- obsidian-agent
- forge

### Prerequisites

- Docker and Compose
- valid Tailscale auth key
- optional `uv` for helper scripts

### Step C1: Configure Environment

```bash
cp docker/.env.example .env
```

Set at minimum:

- `TS_AUTHKEY`
- optional `VAULT_PATH`
- `FORGE_PORT` if non-default

LLM backend defaults are included in `.env.example`.

### Step C2: Start Stack

```bash
uv run docker/up.py
```

Alternative:

```bash
bash docker/up.sh
```

### Step C3: Check Services

```bash
docker compose -f docker/docker-compose.yml ps
curl -fsS http://127.0.0.1:${FORGE_PORT:-8080}/api/health
```

### Step C4: Use Site

Open:

`http://127.0.0.1:${FORGE_PORT:-8080}`

### Step C5: Shutdown and Export Vault

```bash
uv run docker/down.py
```

Alternative:

```bash
bash docker/down.sh
```

## Instance Hardening and Operational Checks

For any new instance:

1. Keep input and output paths explicit.
2. Verify health and negative routes:
   - `/api/health`
   - unknown `/api/*` route (expect controlled failure path)
3. Verify rebuild loop from actual file edits.
4. Confirm output cleanup safety is acceptable for your configured output directory.
5. Lock down secrets (`.env`, API keys).

## Recommended New-Instance Bootstrap Sequence

If you are starting fresh, this sequence is low-risk:

1. Pattern A (prove static build)
2. Pattern B (add proxy + overlay in local dev)
3. Pattern C (package into Docker/Tailscale workflow)

This sequence reduces debugging scope by isolating problems per layer.

## Analysis: Setup Design Quality

Strengths:

1. Forge supports progressive adoption from static-only to full stack.
2. CLI flags make integration points explicit.
3. Docker scripts support repeatable import/export lifecycle for vault data.

Risks:

1. Users may assume `/api/*` works without backend; in Forge dev it requires proxy target.
2. Multiple setup pathways can cause operator confusion if intent is not chosen first.
3. Full stack includes external dependencies (LLM endpoint, network, Tailscale auth).

## Review: Practical Setup Verdict

Forge setup is robust when treated as staged adoption:

- first validate SSG behavior alone
- then add runtime integration surfaces
- then operationalize with Docker/networking

That staged approach aligns with how Forge is engineered internally and gives the highest chance of first-pass success for a new instance.

