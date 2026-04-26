# PLAN

## Mandatory Rule
NO SUBAGENTS. All work is performed directly in this session.

## Goal
Move Docker setup files into `docker/`, keep clone-and-run onboarding simple, and document readiness against desired state.

## Steps
1. Audit current Docker and onboarding docs (`USER_GUIDE.md`, compose, Dockerfiles, env template).
2. Relocate Docker artifacts under `docker/` and update build/volume paths.
3. Update docs/commands so users can run from repo root with minimal steps.
4. Validate compose resolution and document readiness in `DOCKER_READINESS.md`.

## Acceptance Criteria
- Docker runtime files are centralized under `docker/`.
- Fresh-clone flow remains: configure `.env`, run one compose command, service starts.
- `DOCKER_READINESS.md` clearly lists pass/fail and remaining work.

## Mandatory Rule
NO SUBAGENTS. Do not delegate any part of this project.
