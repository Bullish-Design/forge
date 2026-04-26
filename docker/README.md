# Docker + Tailscale + Agent-Native Sync

This setup runs Forge in Docker with a Tailscale sidecar. Sync is owned by
`obsidian-agent` (backed by `obsidian-ops` and jj git bridge). There is no
separate git-sync container.

## Services

- `tailscale`: network namespace + tunnel.
- `forge`: runs `forge dev` (`forge-overlay`, `obsidian-agent`, `kiln`).

## Key Files

- `docker/docker-compose.yml`
- `docker/forge.Dockerfile`
- `docker/entrypoint.py`
- `docker/up.py`
- `docker/down.py`
- `docker/.env.example`

## Required Environment

- `TS_AUTHKEY`
- `AGENT_LLM_BASE_URL`
- `OPENAI_API_KEY` (or provider equivalent)
- `FORGE_SYNC_REMOTE_URL` to enable remote sync
- `FORGE_SYNC_REMOTE_TOKEN` for private remotes

## Sync Configuration

- `FORGE_SYNC_REMOTE_URL`: remote URL; if empty, Forge runs local-only.
- `FORGE_SYNC_REMOTE_TOKEN`: optional PAT/token sent to agent remote config API.
- `FORGE_SYNC_AFTER_COMMIT`: auto-sync after each successful agent commit.
- `FORGE_SYNC_REMOTE`: remote name (default `origin`).

## Startup Sequence

1. `forge-overlay` starts and passes health check.
2. `obsidian-agent` starts and passes health check.
3. Forge runs sync bootstrap if `FORGE_SYNC_REMOTE_URL` is set:
   - `POST /api/vault/vcs/sync/ensure`
   - `PUT /api/vault/vcs/sync/remote`
   - `POST /api/vault/vcs/sync`
4. `kiln` starts watcher mode.

Bootstrap warnings do not crash startup; Forge remains usable in local mode.

## Conflicts and Migration

- If sync reports conflict, agent returns `sync_ok=false` with `conflict=true`
  and a conflict bookmark name.
- If a vault is git-only and cannot be safely colocated (for example dirty
  working tree), ensure returns `migration_needed`; Forge logs a warning.

## Quick Start

```bash
cp docker/.env.example .env
uv run docker/up.py
curl -fsS http://127.0.0.1:${FORGE_PORT:-8080}/api/health
uv run docker/down.py
```
