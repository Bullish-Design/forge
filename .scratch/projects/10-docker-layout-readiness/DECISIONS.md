# DECISIONS

## 1) Keep compose execution from repo root
- Decision: Use `docker compose -f docker/docker-compose.yml ...` in docs.
- Rationale: Keeps onboarding simple while allowing compose file relocation.

## 2) Keep build context at repo root
- Decision: Set compose build context to `..`.
- Rationale: Forge image build needs `cmd/`, `internal/`, `assets/`, and `static/`.

## 3) Keep `.env` at repo root
- Decision: Keep runtime `.env` destination in repo root, but move template to `docker/.env.example`.
- Rationale: Preserves standard compose env loading behavior for users.

## 4) Leave `.dockerignore` at repo root
- Decision: Do not move `.dockerignore` into `docker/`.
- Rationale: Docker uses `.dockerignore` at build context root; moving it would disable ignore filtering for current context.
