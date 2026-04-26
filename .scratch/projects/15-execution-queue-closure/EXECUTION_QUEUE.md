# EXECUTION_QUEUE

## Priority Queue

### P0 — Demo Restoration (M1)

- **Goal:** Restore a working demo path aligned to two-process proxy architecture.
- **Owner:** Forge core / onboarding.
- **Effort:** 0.5–1 day.
- **Primary Work:**
  - Update `demo/run_demo.sh` to remove obsolete `--ops-*` flags and use `--proxy-backend`.
  - Update `devenv.nix` demo helpers for two-process orchestration.
  - Update `demo/README.md` with accurate startup + health/negative checks.
  - Add preflight checks: backend health, env readiness, `jj` availability.
- **Dependencies:** None.

### P1 — Architecture-Critical Refactor Completion (M2)

- **Goal:** Close highest-risk technical debt from review tracker.
- **Owner:** Forge architecture.
- **Effort:** 2–4 days.
- **Primary Work:**
  - `3.4` Thread `BuildContext` into `buildDefault` and `buildCustom`.
  - `3.5` Remove global variables.
  - `5.13` Fix global CLI flag variables.
- **Dependencies:** M1 complete.

### P2 — Theme/Config Cleanup (M3)

- **Goal:** Reduce hardcoded behavior in theme definitions.
- **Owner:** Builder/config.
- **Effort:** 1–2 days.
- **Primary Work:**
  - `5.6` Move theme definitions to embedded YAML.
- **Dependencies:** M2 complete.

### P3 — Frontend Consolidation (M4)

- **Goal:** Remove duplication and improve maintainability in UI code.
- **Owner:** Frontend/UX.
- **Effort:** 1–2 days.
- **Primary Work:**
  - `7.1` Extract shared JS functions.
  - `7.8` Consolidate duplicate CSS.
- **Dependencies:** M2 complete.

### P4 — Formal Review Closure (M5)

- **Goal:** Finish and close `13-code-review` workflow and evidence trail.
- **Owner:** Reviewer/maintainer.
- **Effort:** ~1 day.
- **Primary Work:**
  - Complete `13-code-review` checklist end-to-end.
  - Ensure findings, open questions, and final review delivery are documented.
- **Dependencies:** M3 + M4 complete.

## Recommended Sequence

1. M1 (P0)
2. M2 (P1)
3. M3 (P2) and M4 (P3) in parallel
4. M5 (P4)
