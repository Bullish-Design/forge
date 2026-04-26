# MILESTONE_CHECKLIST

## M1 — Demo Restoration (P0)

- [x] `demo/run_demo.sh` migrated to proxy backend args (no legacy `--ops-*` flags).
- [x] `devenv.nix` demo command(s) updated for two-process startup/shutdown.
- [x] `demo/README.md` updated with exact current commands.
- [x] Preflight checks added (`agent` health, env vars, `jj`).
- [x] Validation: `devenv shell -- demo` (or documented equivalent) runs successfully.
- [x] Validation: apply + undo flow works end-to-end.
- [x] Evidence logged (commands + outputs + any caveats).

## M2 — Architecture-Critical Refactor (P1)

- [x] `3.4` complete: `BuildContext` threaded into `buildDefault` and `buildCustom`.
- [x] `3.5` complete: global variables removed/reduced as planned.
- [x] `5.13` complete: global CLI flag variable issue fixed.
- [x] Targeted tests for builder/CLI paths pass.
- [x] Regressions/baseline failures documented explicitly.
- [x] Evidence logged.

## M3 — Theme/Config Cleanup (P2)

- [x] `5.6` complete: theme definitions moved to embedded YAML.
- [x] Config load behavior verified in normal and error paths.
- [x] Relevant tests pass; docs updated if behavior changes.
- [x] Evidence logged.

## M4 — Frontend Consolidation (P3)

- [x] `7.1` complete: shared JS extraction done with no behavior drift.
- [x] `7.8` complete: duplicate CSS consolidated.
- [x] Frontend tests pass and manual smoke checks succeed.
- [x] Evidence logged.

## M5 — Formal Review Closure (P4)

- [x] `.scratch/projects/13-code-review/PROGRESS.md` checklist fully completed.
- [x] Findings documented and open questions resolved or explicitly deferred.
- [x] Final review output delivered and linked.
- [x] Remaining TODO count reconciled across trackers.

## Exit Criteria

- [x] M1, M2, M3, M4, M5 all complete.
- [x] No untracked critical blockers remain.
- [x] All changed docs/status files reflect final state.
