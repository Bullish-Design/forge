# CONTEXT

Current state:
- Docker assets now live under `docker/`:
  - `docker/docker-compose.yml`
  - `docker/forge.Dockerfile`
  - `docker/agent.Dockerfile`
  - `docker/entrypoint.sh`
  - `docker/.env.example`
  - `docker/README.md`
- Compose file was updated to keep repo-root semantics while living in `docker/`:
  - build `context: ..`
  - forge dockerfile path `docker/forge.Dockerfile`
  - default vault bind path `../vault`
  - static bind path `../static`
- User guide now uses:
  - `cp docker/.env.example .env`
  - `docker compose -f docker/docker-compose.yml ...`

Validation performed:
- `docker compose -f docker/docker-compose.yml config` succeeds.
- With `VAULT_PATH` unset, resolved mount points map to repo-root `vault` and `static`.

Outstanding known caveat:
- `.dockerignore` remains at repo root because Docker build context is repo root (`..`), and Docker only applies `.dockerignore` from context root.
