# PROGRESS

- [x] Audit existing docker setup and onboarding docs.
- [x] Move root `Dockerfile` to `docker/forge.Dockerfile`.
- [x] Move root `docker-compose.yml` to `docker/docker-compose.yml`.
- [x] Move `.env.example` to `docker/.env.example`.
- [x] Update compose paths (`context`, `dockerfile`, bind mounts) for new location.
- [x] Update `USER_GUIDE.md` and `docker/README.md` commands and paths.
- [x] Validate compose file with `docker compose -f docker/docker-compose.yml config`.
- [x] Produce `DOCKER_READINESS.md`.
