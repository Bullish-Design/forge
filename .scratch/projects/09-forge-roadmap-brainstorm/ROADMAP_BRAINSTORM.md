# ROADMAP_BRAINSTORM

## Purpose

This document proposes the best next steps for improving, refactoring, and expanding Forge as a **local-first app** running on a user’s private Tailscale network.

Scope focus:
- Local development and runtime reliability
- Vault editing UX and safety
- Architecture quality and maintainability
- Better use of the Forge + `obsidian-agent` + `obsidian-ops` stack

Out of scope:
- Public hosting/CDN/deployment strategy
- Internet-facing hardening or multi-tenant cloud architecture

---

## Current State Snapshot (What We Have Today)

### Architecture

Forge is now correctly positioned as a thin host:
- Renders static site from local vault
- Injects overlay assets
- Serves overlay at `/ops/*`
- Proxies `/api/*` to backend (`--proxy-backend`)

Relevant files:
- `internal/cli/dev.go`
- `internal/server/mux.go`
- `internal/proxy/reverse.go`
- `static/ops.js`
- `docker-compose.yml`

### Containerized Runtime Topology

The Docker stack now runs:
1. `tailscale`
2. `obsidian-agent`
3. `forge`

It includes:
- `jj` bootstrap for vault history in the agent container
- model readiness wait before agent startup
- proxy-only API flow from Forge to agent

Relevant files:
- `docker-compose.yml`
- `docker/agent.Dockerfile`
- `docker/entrypoint.sh`
- `.env.example`

### Quality Baseline

`go test ./...` currently fails on two known areas:
1. `internal/builder` OG image filename expectation mismatch
2. `internal/templates` OG/Twitter URL expectation mismatch

This is a critical quality signal: the repo is not fully green at HEAD.

### Notable Technical Debt

1. Large global mutable state in builder/CLI flow.
- `internal/builder/builder.go` package-level vars (`InputDir`, `OutputDir`, etc.)

2. Deprecated runtime code still present and tested.
- `internal/ops/*` retained after architecture cutover

3. Release automation drift.
- `.github/workflows/release.yml` references old `cmd/kiln` targets, not current `forge` layout

4. CI gap.
- No normal CI workflow to gate PRs with tests/lint

5. Frontend debug mode always on.
- `static/ops.js` has `OPS_DEBUG = true`

---

## Product Direction (Local Tailscale App)

### North Star

Make Forge the easiest and safest way for a non-technical user to:
1. Run a private, local Obsidian-powered site
2. Edit content through natural language
3. Undo mistakes confidently
4. Keep everything inside their own machine/tailnet workflow

### Guiding Principles

1. Keep Forge thin; keep edit intelligence in `obsidian-agent`/`obsidian-ops`.
2. Prefer reliability and visibility over feature count.
3. Never hide state-changing operations; always expose clear outcomes.
4. Minimize setup friction for non-technical users.

---

## Recommended Roadmap

## Phase 0 (Immediate, 1-2 weeks): Stabilize The Baseline

### Goals

- Make main branch reliably green
- Remove known regressions
- Lock in confidence for future work

### Work Items

1. Fix OG image contract mismatch end-to-end.
- Align generator filenames and template URL helpers.
- Update tests in `internal/builder` and `internal/templates` to match the intended behavior.

2. Add CI workflow for PR gating.
- Run `go test ./...` and `go vet ./...` on each PR.
- Keep existing release workflow separate.

3. Fix release workflow drift.
- Update `.github/workflows/release.yml` to build correct current binaries.
- Validate artifact names and `ldflags` package path.

4. Reduce noisy debug defaults in overlay.
- Gate `OPS_DEBUG` behind build flag or runtime flag.
- Keep user-facing console output minimal in normal mode.

### Success Criteria

- `go test ./...` passes on clean checkout
- PR CI blocks merges on failing tests
- release workflow builds correct artifacts

---

## Phase 1 (Near-term, 2-5 weeks): Refactor Core Runtime Internals

### Goals

- Lower maintenance risk
- Make runtime behavior easier to reason about

### Work Items

1. Replace builder package globals with explicit config structs.
- Introduce `BuildConfig` and `DevRuntimeConfig`.
- Pass configuration as explicit dependencies instead of package vars.

2. Remove or archive deprecated `internal/ops` runtime path.
- Keep only what is required for historical reference, not active compile path.
- Ensure no runtime wiring can regress back to in-process ops.

3. Refactor HTTP serving to avoid global default mux side effects.
- `internal/server/server.go` currently uses `http.Handle` global registrations.
- Move to explicit `http.NewServeMux()` to prevent handler bleed in future tests/extensions.

4. Consolidate `generate` and `dev` build setup code.
- Extract shared setup function to reduce duplication and drift.

### Success Criteria

- No package-level mutable build config in runtime path
- No active dependency from Forge runtime into `internal/ops`
- Server tests and new mux behavior remain green

---

## Phase 2 (Near-term, 4-8 weeks): Improve Non-Technical User Experience

### Goals

- One clear path from install to first successful edit
- Better feedback during apply/undo flows

### Work Items

1. Add a first-run local setup command.
- Example: `forge local-init` for guided `.env`, vault path, and health preflight.
- Keep it strictly local/Tailscale-focused.

2. Add local diagnostics command for runtime stack.
- Example checks:
  - Forge health
  - Agent health
  - model backend reachability
  - vault writable + `jj` status

3. Improve overlay UX for operation visibility.
- Show changed files list from API response.
- Show “operation in progress” vs “busy” vs “failed” clearly.
- Keep undo feedback explicit.

4. Add post-apply refresh assist.
- After successful apply, poll lightweight readiness marker for rebuild completion.
- Reduce “I refreshed too early” confusion.

### Success Criteria

- New user can complete first run + first edit without reading code
- Overlay errors are actionable (not generic)
- Reduced support friction for “why didn’t page update yet?”

---

## Phase 3 (Mid-term, 6-12 weeks): Deepen Agent Integration Features

### Goals

- Make the editing interface feel robust, not experimental
- Fully leverage dependency libraries

### Work Items

1. Add interface mode registry in frontend to match backend `interface_id` model.
- Keep `command` as default
- Introduce architecture for future modes without endpoint proliferation

2. Add streaming progress (SSE) for long operations.
- Show tool execution and completion phases in UI.
- Avoid “frozen UI” perception.

3. Extend API contract with optional “warnings” and structured status detail.
- Distinguish hard errors from partial-success outcomes.

4. Implement operation history panel in UI.
- Last N actions, summaries, timestamps, and undo status.

### Success Criteria

- Long-running edits show live progress
- Users can inspect recent operations from UI
- Interface can grow without API churn

---

## Phase 4 (Mid-term, 8-14 weeks): Content and Build Performance Improvements

### Goals

- Faster feedback loops on larger vaults
- Better output quality and consistency

### Work Items

1. Profile incremental rebuild behavior on large vaults.
- Measure rebuild fan-out from `watch/depgraph` invalidation.
- Tighten dependency invalidation where over-rebuilding occurs.

2. Improve asset pipeline utilization.
- Extend minification strategy beyond current HTML focus where safe.
- Evaluate optional compression strategy for generated assets.

3. Strengthen metadata/OG consistency.
- One canonical rule for OG/Twitter paths and generation locations.
- Add integration tests that verify generated files and head tags together.

4. Add deterministic test vault fixtures for edge cases.
- duplicate names
- folder/file overrides
- large image + canvas combinations

### Success Criteria

- Faster average incremental rebuild time
- OG/Twitter generation fully deterministic and tested
- Fewer content-structure regressions

---

## Phase 5 (Longer Horizon): Plugin/Extension-Friendly Local App

### Goals

- Allow safe local extensibility without bloating core Forge

### Work Items

1. Define extension hooks for overlay actions.
- Local plugin scripts for custom commands
- Controlled input/output contracts

2. Define extension hooks for build pipeline.
- pre-build and post-build hooks for local transforms

3. Add permissions model for extensions.
- read-only vs write access
- explicit user opt-in

### Success Criteria

- Extensions can add value without destabilizing core app
- Safe defaults for non-technical users

---

## Best Next 10 Tasks (Priority Backlog)

1. Fix OG image filename/URL contract and failing tests.
2. Add PR CI workflow for tests and vet.
3. Repair release workflow binary targets and paths.
4. Replace builder globals with explicit config object.
5. Move server routing off global default mux.
6. Remove active runtime reliance on deprecated `internal/ops` package.
7. Add `forge local doctor` diagnostics command.
8. Upgrade `static/ops.js` status UX (busy/error/warning/changed files).
9. Add post-apply rebuild-ready polling in overlay.
10. Add an integration test lane for Docker two-process stack health/apply/undo.

---

## Dependency Library Utilization Plan

To fully utilize underlying dependencies (`obsidian-agent`, `obsidian-ops`) inside the Forge user experience:

1. Consume richer `obsidian-ops` operations through agent flows.
- frontmatter patch operations
- heading/block patch operations
- structured VCS status/warnings

2. Expose agent orchestration detail safely to UI.
- progress events (SSE)
- typed warning categories
- operation summary fidelity

3. Keep Forge focused on presentation + routing.
- no reintroduction of in-process mutation logic
- no duplication of vault/VCS semantics in Go runtime

---

## Risks And Mitigations

1. Risk: Refactor churn slows feature delivery.
- Mitigation: time-box Phase 1 and keep clear acceptance criteria.

2. Risk: UI and backend contract drift.
- Mitigation: contract tests for `/api/apply` and `/api/undo` payload/response schema.

3. Risk: Docker/local stack regressions.
- Mitigation: integration smoke tests in CI and pre-release checklist.

4. Risk: Non-technical users overwhelmed by setup.
- Mitigation: guided local-init and doctor commands with actionable output.

---

## Suggested Execution Order

1. Phase 0 stability work
2. Phase 1 core refactor work
3. Phase 2 UX upgrades
4. Phase 3 agent-integration depth
5. Phase 4 performance/content hardening
6. Phase 5 extension platform

This order keeps the local Tailscale app reliable first, then progressively more capable.
