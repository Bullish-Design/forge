# PROGRESS

## Status

- [x] Created new numbered project template directory.
- [x] Reviewed outstanding items from `.scratch/projects/08`, `13`, and `14` artifacts.
- [x] Built prioritized execution queue with owners, effort, and dependency order.
- [x] Produced milestone checklist for immediate execution.
- [x] Populated all standard project template files.

## Current State

- Planning/tracking deliverable remains complete.
- Milestone M1 (Demo Restoration) is now completed and validated.
- Milestone M2 (Architecture-Critical Refactor) is now completed and validated.
- Milestone M3 (Theme/Config Cleanup) is now completed and validated.
- Milestone M4 (Frontend Consolidation) is now completed and validated.
- Milestone M5 (Formal Review Closure) is now completed and validated.

## Next Action (Operational)

- Milestone closure complete; maintainers can treat this project as closed.

## Execution Update — 2026-04-23 (M1 Complete)

### Implemented

- `demo/run_demo.sh`
  - Added explicit preflight checks for required tools, paths, env sanity, and stale agent port conflicts.
  - Added robust two-process lifecycle management so `Ctrl-C` shuts down both Forge and `obsidian-agent`.
  - Added first-init `jj` baseline snapshot creation to ensure `/api/undo` restores demo baseline instead of removing seeded content.
  - Confirmed no legacy `--ops-*` Forge flags are used.
- `devenv.nix`
  - Added explicit demo helpers for two-process mode: `demo-agent` and `demo-forge`.
  - Retained `demo` as orchestrated path (`demo-clean` + `run_demo.sh`).
- `demo/README.md`
  - Updated commands and architecture description to match current behavior.
  - Added deterministic preflight, health checks, negative check, and apply/undo validation sequence.

### Validation Evidence

- Stack startup:
  - Command: `devenv shell -- demo`
  - Result: preflight passed, `obsidian-agent` healthy on `127.0.0.1:8081`, Forge served on `127.0.0.1:8080`.
- Health + proxy:
  - `GET http://127.0.0.1:8081/api/health` -> `{"ok":true,"status":"healthy"}`
  - `GET http://127.0.0.1:8080/api/health` -> `{"ok":true,"status":"healthy"}`
- Negative contract check:
  - `GET http://127.0.0.1:8080/api/not-a-route` -> HTTP `404`, body `{"detail":"Not Found"}`
- Apply + undo:
  - `POST /api/apply` via Forge proxy returned `ok:true` and wrote `guides/demo-agent-check.md`.
  - `POST /api/undo` via Forge proxy returned `ok:true`; `guides/demo-agent-check.md` removed.
  - Baseline files (`CNAME`, `favicon.ico`, `_redirects`) remained present after undo.
  - `jj status` reported: `The working copy has no changes.`
- Shutdown:
  - `Ctrl-C` stopped Forge and agent.
  - Follow-up health probes to both ports returned connection failure (`000`), confirming clean teardown.

### Caveats

- In this execution environment, `remora-server` host resolution required running validation commands with elevated permissions. Demo behavior itself validated successfully once local service access was allowed.

## Execution Update — 2026-04-23 (M2 Step 3.4 Complete)

### Implemented

- `internal/builder/builder.go`
  - Updated `Build` and `IncrementalBuild` to pass `BuildContext` directly into `buildDefault` and `buildCustom`.
  - Removed global rebuild-filter usage in favor of a local incremental rebuild filter map.
- `internal/builder/builder_default.go`
  - Updated `buildDefault` to accept `BuildContext` and an optional rebuild filter.
  - Replaced global builder setting reads with `ctx`/`DefaultSite` fields.
  - Threaded rebuild filter through static/page render paths and updated `shouldRebuild` callers.
  - Added explicit `InputDir`/`OutputDir` to `DefaultSite` and removed global path usage in graph/404/canvas/asset/search writers.
- `internal/builder/builder_custom.go`
  - Updated `buildCustom` to accept `BuildContext`.
  - Replaced global input/base/flat usage with `ctx` and `CustomSite` fields.
  - Added `obsidian.WithOutputDir(ctx.OutputDir)` to keep custom mode aligned with resolved build context.
- `internal/builder/utils.go`, `internal/builder/builder_test.go`
  - Changed `shouldRebuild` to accept explicit filter map parameter.
  - Updated unit tests accordingly.

### Validation Evidence

- `devenv shell -- go test ./internal/builder/...` -> `ok`
- `devenv shell -- go test ./internal/cli/...` -> `ok`
- `devenv shell -- go build ./...` -> success (exit code 0)

### Regressions / Notes

- No regressions observed in targeted builder/CLI compile/test paths for this step.

## Execution Update — 2026-04-23 (M2 Step 3.5 Complete)

### Implemented

- `internal/builder/builder.go`
  - Removed the remaining package-level builder globals (`OutputDir`, `InputDir`, `ThemeName`, etc.) now that `BuildContext` is threaded end-to-end.
- `internal/cli/doctor.go`, `internal/cli/serve.go`
  - Removed legacy dependence on deleted builder globals (`builder.InputDir`, `builder.OutputDir`).
  - Switched to command-resolved paths (`inputDir`/`outputDir`) directly.

### Validation Evidence

- `devenv shell -- go test ./internal/builder/... -count=1` -> `ok`
- `devenv shell -- go test ./internal/cli/... -count=1` -> `ok`
- `devenv shell -- go build ./...` -> success (exit code 0)

### Regressions / Notes

- During validation, compile failures in `doctor`/`serve` surfaced hidden usage of removed builder globals.
- These references were fixed in the same step; subsequent `devenv` tests/build passed cleanly.

## Execution Update — 2026-04-23 (M2 Step 5.13 Complete)

### Implemented

- `internal/cli/commands.go`
  - Removed package-level CLI flag state.
  - Added local flag resolvers (`resolveStringFlag`, `resolveBoolFlag`) and updated logger creation to `getLogger(logLevel string)`.
- `internal/cli/generate.go`, `internal/cli/dev.go`
  - Replaced bound package-global flag vars with command-local flag definitions (`StringP`/`Bool`/`Int`) and per-run local resolution.
  - `runGenerate` and `runDev` now construct `BuildContext` from local resolved values only.
- `internal/cli/serve.go`, `internal/cli/clean.go`, `internal/cli/init.go`, `internal/cli/stats.go`, `internal/cli/doctor.go`
  - Converted remaining commands to local flag resolution and removed dependency on shared mutable CLI variables.

### Validation Evidence

- `devenv shell -- go test ./internal/cli/... -count=1` -> `ok`
- `devenv shell -- go test ./internal/builder/... -count=1` -> `ok`
- `devenv shell -- go build ./...` -> success (exit code 0)

### Regressions / Notes

- No behavioral regressions observed in targeted CLI/builder compile+test paths after localizing flag state.
- Milestone M2 is now complete in the execution tracker.

## Execution Update — 2026-04-23 (M3 Step 5.6 Complete)

### Implemented

- `internal/builder/themes.go`
  - Replaced hardcoded `themes` map with embedded YAML-backed theme registry (`//go:embed themes.yaml`).
  - Added YAML parse/validation path (`parseThemeCatalog`) with required-default guard and normalized theme keys.
  - Added runtime fallback to an in-code default theme when embedded YAML parsing fails.
  - Updated `ResolveTheme` to instantiate a fresh `Theme` from registry data (avoids mutation bleed across calls).
- `internal/builder/themes.yaml`
  - Added the full built-in theme catalog as embedded YAML data.
- `internal/builder/themes_test.go`
  - Added tests for invalid YAML handling and missing-default error path.
  - Added runtime test covering unknown-theme fallback and accent override isolation behavior.

### Validation Evidence

- `devenv shell -- go test ./internal/builder/... -count=1` -> `ok`
- `devenv shell -- go test ./internal/cli/... -count=1` -> `ok`
- `devenv shell -- go build ./...` -> success (exit code 0)

### Regressions / Notes

- Initial YAML mapping attempt produced empty color fields; corrected by normalizing YAML keys and adding explicit `yaml` tags on `ThemeColors`.
- No remaining regressions observed after the fix.

## Execution Update — 2026-04-24 (M4 Step 7.1 Complete)

### Implemented

- `assets/shared_app.js`
  - Added a shared JS utility bundle (`window.SharedApp`) for common layout behavior:
    - script loader, MathJax init, Mermaid init, Giscus theme sync, theme toggle handling
    - copy buttons, canvas mode init, folder animation, lightbox, back-to-top
    - global search shortcut binder and Giscus postMessage listener binder
- `assets/default_app.js`, `assets/simple_app.js`
  - Reduced each layout file to layout-specific behavior plus wrappers that call shared utilities.
  - Kept layout-specific logic in place (default sidebar/graph overlay; simple panel system).
- `internal/builder/layouts.go`, `internal/builder/builder_default.go`, `assets/assets.go`
  - Embedded and loaded `shared_app.js` as a template asset.
  - Updated asset writing so output `app.js` is built by concatenating shared template + layout template, preserving existing HTML script includes and avoiding runtime order drift.
  - Added `writeTemplates(...)` helper for multi-template JS output.

### Validation Evidence

- `devenv shell -- go build ./...` -> success (exit code 0)
- `devenv shell -- go test -count=1 ./internal/builder/...` -> `ok`
- `devenv shell -- go test -count=1 ./internal/cli/...` -> `ok`
- `devenv shell -- go run ./cmd/forge generate --input demo/vault --output /tmp/forge_m4_default --layout default` -> success
- `devenv shell -- go run ./cmd/forge generate --input demo/vault --output /tmp/forge_m4_simple --layout simple` -> success
- `devenv shell -- node --check /tmp/forge_m4_default/app.js` -> success
- `devenv shell -- node --check /tmp/forge_m4_simple/app.js` -> success
- `devenv shell -- node --test static/src/__tests__/*.test.js` -> 13 passed, 0 failed

### Regressions / Notes

- Verified generated `app.js` in both layouts contains shared bundle + layout wrapper content with expected symbols present.
- Size reduction evidence in source assets:
  - `assets/default_app.js`: 544 -> 214 lines
  - `assets/simple_app.js`: 436 -> 133 lines

## Execution Update — 2026-04-24 (M4 Step 7.8 Complete)

### Implemented

- `assets/default_style.css`
  - Removed duplicated `body` typography/color rule that was already defined in `assets/shared.css`.
- CSS audit scope:
  - Compared `assets/shared.css` against `assets/default_style.css` and `assets/simple_style.css` custom sections.
  - Verified shared/common rule now lives only in shared stylesheet.

### Validation Evidence

- `devenv shell -- go build ./...` -> success (exit code 0)
- `devenv shell -- go test -count=1 ./internal/builder/...` -> `ok`
- `devenv shell -- go test -count=1 ./internal/cli/...` -> `ok`
- `devenv shell -- node --test static/src/__tests__/*.test.js` -> 13 passed, 0 failed
- `devenv shell -- go run ./cmd/forge generate --input demo/vault --output /tmp/forge_m4_default --layout default` -> success
- `devenv shell -- go run ./cmd/forge generate --input demo/vault --output /tmp/forge_m4_simple --layout simple` -> success
- Post-build CSS check:
  - `rg '^body\\s*\\{' /tmp/forge_m4_default/shared.css /tmp/forge_m4_default/style.css /tmp/forge_m4_simple/shared.css /tmp/forge_m4_simple/style.css`
  - Result: `body` rule appears in `shared.css` only (no duplicate in layout `style.css`).

### Regressions / Notes

- No behavioral drift observed in build/test/smoke checks for either active layout.

## Execution Update — 2026-04-24 (M5 Step 1 Complete)

### Implemented

- `.scratch/projects/13-code-review/PROGRESS.md`
  - Completed all review checklist items.
  - Added closure-evidence notes linking scope, findings, test/check evidence, open-question disposition, and final review artifacts.
- `.scratch/projects/15-execution-queue-closure/MILESTONE_CHECKLIST.md`
  - Marked M5 checklist item 1 complete (`13-code-review/PROGRESS.md` fully completed).

### Validation Evidence

- `devenv shell -- cat .scratch/projects/13-code-review/PROGRESS.md`
  - Result: all six checklist entries marked complete and closure evidence documented.
- `devenv shell -- rg -n '^- \\[ \\]' .scratch/projects/13-code-review/PROGRESS.md`
  - Result: no unchecked checklist entries in that tracker.

### Regressions / Notes

- This step is documentation/tracker closure only; no product code paths changed.

## Execution Update — 2026-04-24 (M5 Step 2 Complete)

### Implemented

- `.scratch/projects/13-code-review/REVIEW_REFACTORING_STATUS.md`
  - Updated assessment date/method to reflect current closure pass.
  - Reconciled stale items `3.4`, `3.5`, `5.6`, `5.13`, `7.1`, and `7.8` from `TODO` to `DONE` with concrete code evidence.
  - Updated summary counts from `DONE: 64 / TODO: 6` to `DONE: 70 / TODO: 0`.
  - Added explicit `Open Questions / Deferrals` closure section (no unresolved blockers).
- `.scratch/projects/15-execution-queue-closure/MILESTONE_CHECKLIST.md`
  - Marked M5 checklist item 2 complete.

### Validation Evidence

- `devenv shell -- rg -n '3\\.4|3\\.5|5\\.6|5\\.13|7\\.1|7\\.8' .scratch/projects/13-code-review/REVIEW_REFACTORING_STATUS.md`
  - Result: each formerly-open step is now marked `DONE` with evidence.
- `devenv shell -- rg -n 'DONE|TODO|Open Questions / Deferrals' .scratch/projects/13-code-review/REVIEW_REFACTORING_STATUS.md`
  - Result: summary reports `DONE: 70`, `TODO: 0`, and open-question closure section is present.

### Regressions / Notes

- This step is documentation/tracker reconciliation only; no runtime code was changed.

## Execution Update — 2026-04-24 (M5 Step 3 Complete)

### Implemented

- `.scratch/projects/13-code-review/FINAL_REVIEW.md`
  - Added formal final review output for the refactoring-guide closure.
  - Captured final disposition, open-question status, and validation-evidence linkage.
- `.scratch/projects/13-code-review/PROGRESS.md`
  - Updated final-review evidence bullet to point to `FINAL_REVIEW.md`.
- `.scratch/projects/15-execution-queue-closure/MILESTONE_CHECKLIST.md`
  - Marked M5 checklist item 3 complete.

### Validation Evidence

- `devenv shell -- test -f .scratch/projects/13-code-review/FINAL_REVIEW.md`
  - Result: final review output file exists.
- `devenv shell -- rg -n 'FINAL_REVIEW.md' .scratch/projects/13-code-review/PROGRESS.md .scratch/projects/15-execution-queue-closure/PROGRESS.md`
  - Result: final review output is linked from active tracker documentation.

### Regressions / Notes

- This step is documentation delivery only; no product runtime code changed.

## Execution Update — 2026-04-24 (M5 Step 4 Complete)

### Implemented

- `.scratch/projects/14-revised-code-review/PROGRESS.md`
  - Added closure-reconciliation note and updated previously deferred top-10 rows to done with references to project-15 milestones.
- `.scratch/projects/15-execution-queue-closure/CONTEXT.md`
  - Added explicit closure-state section with cross-tracker reconciliation snapshot.
- `.scratch/projects/15-execution-queue-closure/MILESTONE_CHECKLIST.md`
  - Marked M5 checklist item 4 complete.
  - Marked all exit criteria complete.

### Validation Evidence

- `devenv shell -- rg -n '^- \\[ \\]' .scratch/projects/13-code-review/PROGRESS.md`
  - Result: no unchecked checklist entries.
- `devenv shell -- rg -n '^- `TODO`:' .scratch/projects/13-code-review/REVIEW_REFACTORING_STATUS.md`
  - Result: reports `TODO: 0`.
- `devenv shell -- rg -n '\\| [0-9]+ \\|' .scratch/projects/14-revised-code-review/PROGRESS.md`
  - Result: no remaining non-struck top-10 rows.
- `devenv shell -- rg -n '^- \\[ \\]' .scratch/projects/15-execution-queue-closure/MILESTONE_CHECKLIST.md`
  - Result: no unchecked milestone or exit-criteria entries.

### Regressions / Notes

- This step is tracker reconciliation and sign-off documentation only.
