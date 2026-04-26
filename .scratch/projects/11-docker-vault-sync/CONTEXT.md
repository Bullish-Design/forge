# CONTEXT

Implemented:
- `docker/docker-compose.yml` mounts `forge-vault:/data/vault` for `obsidian-agent` and `forge`.
- `forge-vault` is explicitly named (`name: forge-vault`) to align with script defaults.
- Added UV scripts:
  - `docker/import_vault.py` host -> volume mirror
  - `docker/export_vault.py` volume -> host mirror
- Added UV wrapper scripts:
  - `docker/up.py` import + compose up
  - `docker/down.py` compose down + export
- Updated docs:
  - `docker/README.md`
  - `USER_GUIDE.md`
  - `DOCKER_READINESS.md`
- Updated `docker/.env.example` comments for script-driven `VAULT_PATH`.

Validation:
- `docker compose -f docker/docker-compose.yml config` passes.
- `devenv shell -- uv run docker/import_vault.py --help` passes.
- `devenv shell -- uv run docker/export_vault.py --help` passes.
- `devenv shell -- uv run docker/up.py -h` passes.
- `devenv shell -- uv run docker/down.py --help` passes.

Operational model:
- Runtime data lives in Docker volume for performance.
- Host sync is explicit via import/export scripts.
- Recommended day-to-day wrappers are `uv run docker/up.py` and `uv run docker/down.py`.
