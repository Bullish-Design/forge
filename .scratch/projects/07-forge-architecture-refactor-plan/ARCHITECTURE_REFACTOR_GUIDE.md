# ARCHITECTURE_REFACTOR_GUIDE

## Table Of Contents

1. **Guide Purpose And Success Criteria**
   Defines what this refactor must accomplish and what “done” means for a first-time contributor.
2. **Non-Negotiable Working Rules**
   Operational rules that must be followed every step (TDD, no shortcuts, no silent contract changes).
3. **Architecture Primer (Before vs After)**
   Explains the current architecture and target architecture with explicit ownership boundaries.
4. **Repository Map And Ownership Boundaries**
   Introduces key files in `forge`, `obsidian-agent`, and `obsidian-ops`, and what each repo is allowed to own.
5. **Environment Setup And Tooling Bootstrap**
   Provides exact environment setup commands and validation checks before any edits.
6. **Branching, Commit, And PR Strategy**
   Defines implementation sequencing and commit slicing so work is reviewable and reversible.
7. **Verification Strategy Overview**
   Defines test levels (unit, integration, contract, manual) and how to decide when a phase is complete.
8. **Phase 0 — Baseline And Safety Net**
   Captures baseline behavior/tests and creates a rollback-safe starting point.
9. **Phase 1 — obsidian-ops Boundary Hardening**
   Ensures all commit/undo behavior is cleanly expressed via `obsidian-ops` APIs and fully tested.
10. **Phase 2 — obsidian-agent Contract Cutover**
    Switches API contract to `current_file` + `interface_id`, removes `current_url_path`, and verifies behavior.
11. **Phase 3 — Forge Backend Cutover (Proxy-Only API Path)**
    Removes in-process Go ops backend wiring and makes Forge a true thin host/proxy.
12. **Phase 4 — Forge Frontend Cutover (`ops.js` + Page Context Metadata)**
    Updates overlay payload shape and adds robust page context extraction for `current_file`.
13. **Phase 5 — End-To-End Integration Validation**
    Validates full two-process workflow across all repos with explicit pass/fail criteria.
14. **Phase 6 — Cleanup, Documentation, And Release Readiness**
    Cleans legacy paths, updates docs, and prepares merge/release artifacts.
15. **Detailed Test Matrix By Step**
    Consolidated matrix mapping each step to exact commands and expected outcomes.
16. **Troubleshooting Playbook**
    Common failure cases and exact recovery actions.
17. **Rollback And Recovery Plan**
    Safe rollback approach if a cutover fails in development or staging.
18. **Checklist**
    Reusable daily execution checklist to avoid missed validations.
19. **Final Sign-Off Checklist**
    Final checklist a reviewer can run to confirm the refactor is complete and safe.

## 1) Guide Purpose And Success Criteria

This guide is written for someone with no prior knowledge of `forge`, `obsidian-agent`, or `obsidian-ops`.

Your job is to implement the architecture refactor end-to-end with no hidden regressions, and no fuzzy boundaries.

### Primary Objective

Refactor the system so responsibilities are cleanly split:

- `forge` (Go): static site host, overlay injection, `/ops/*` static assets, `/api/*` reverse proxy.
- `obsidian-agent` (Python): request handling and LLM orchestration.
- `obsidian-ops` (Python): vault mutation/search/frontmatter/content patching + version-control operations.

### Hard Decisions Already Made

These are not open questions anymore:

1. **Immediate contract cutover**: use `current_file` now; do not keep `current_url_path` compatibility.
2. **Single cutover is allowed**: frontend and backend contract can change together.
3. **VCS ownership**: commit/undo behavior must be owned by `obsidian-ops` APIs.
4. **URL-to-file ownership**: Forge owns route/page resolution and emits `current_file` context.
5. **v1 runtime shape**: two-process topology (`forge` + `obsidian-agent`), with `obsidian-ops` consumed as a library.

### Definition Of Done

The refactor is done only when all are true:

1. Forge no longer runs in-process Go ops backend for runtime API handling.
2. Overlay requests send `current_file` and optional `interface_id`; no `current_url_path` in contract.
3. `obsidian-agent` accepts new request contract and routes by interface handler (at least `command`).
4. `obsidian-agent` does not perform raw JJ subprocess management.
5. `obsidian-ops` is the sole owner of commit/undo mechanics exposed via its API surface.
6. End-to-end apply + undo works through Forge proxy into Python backend.
7. All test gates in this guide pass.

---

## 2) Non-Negotiable Working Rules

Follow these every step:

1. **TDD discipline**. Add/adjust tests with each behavior change.
2. **No silent contract drift**. If payloads/response shapes change, update tests and docs in the same step.
3. **Small commits**. One logical change per commit.
4. **Run tests continuously**. Do not defer testing to the end.
5. **Do not bypass dependency boundaries**. No quick hacks around `obsidian-ops`.

---

## 3) Architecture Primer (Before vs After)

### Before (Current Problem)

- Forge dev command wires `internal/ops` Go backend in-process.
- Frontend sends `{ instruction, current_url_path }`.
- Backend path resolution and LLM flow partially live inside Forge runtime.
- This violates target boundary (Forge is not thin).

### After (Target)

```text
Browser Overlay (ops.js)
    |
    | POST /api/apply {instruction, current_file, interface_id}
    v
Forge (Go thin host)
- serves HTML/static
- injects overlay
- proxies /api/*
    |
    v
obsidian-agent (Python)
- validates request model
- dispatches interface handler
- orchestrates tool calls
    |
    v
obsidian-ops (Python library)
- file/frontmatter/content ops
- search/list
- commit/undo/status
```

### Why This Is Better

- Clear ownership boundaries.
- Easier testing (unit and contract tests are local to owner repo).
- Easier future evolution (`interface_id`, SSE, additional modes).

---

## 4) Repository Map And Ownership Boundaries

### A) Forge

Path: `/home/andrew/Documents/Projects/forge`

Key files for this refactor:

- `internal/cli/dev.go`
- `internal/server/mux.go`
- `internal/proxy/reverse.go`
- `static/ops.js`
- `static/ops.css`
- `internal/templates/*.templ` (for page context metadata)
- `internal/templates/*_templ.go` (generated files; regenerate after template edits)

Owns:

- serving/rendering/injection/proxy and page context emission.

Must not own:

- LLM orchestration, vault mutation, JJ logic.

### B) obsidian-agent

Path: `/home/andrew/Documents/Projects/obsidian-agent`

Key files:

- `src/obsidian_agent/app.py`
- `src/obsidian_agent/models.py`
- `src/obsidian_agent/agent.py`
- `src/obsidian_agent/tools.py`
- `src/obsidian_agent/prompt.py`
- `tests/test_app.py`
- `tests/test_models.py`
- `tests/test_agent.py`
- `tests/test_integration.py`

Owns:

- API request/response contract.
- interface dispatch and agent orchestration.

Must not own:

- raw JJ subprocess behavior.
- Forge URL/path resolution rules.

### C) obsidian-ops

Path: `/home/andrew/Documents/Projects/obsidian-ops`

Key files:

- `src/obsidian_ops/vault.py`
- `src/obsidian_ops/vcs.py`
- `src/obsidian_ops/server.py`
- `src/obsidian_ops/frontmatter.py`
- `src/obsidian_ops/content.py`
- `tests/test_vcs.py`
- `tests/test_server.py`
- `tests/test_integration.py`

Owns:

- all vault/VCS primitives used by upstream agent flows.

Must not own:

- Forge routing semantics, LLM behavior, or UI-mode orchestration.

---

## 5) Environment Setup And Tooling Bootstrap

Run these before changing code.

### Forge repo setup

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- uv sync --extra dev
```

### obsidian-agent repo setup

```bash
cd /home/andrew/Documents/Projects/obsidian-agent
devenv shell -- uv sync --extra dev
```

### obsidian-ops repo setup

```bash
cd /home/andrew/Documents/Projects/obsidian-ops
devenv shell -- uv sync --extra dev
```

### Verify working toolchains

```bash
cd /home/andrew/Documents/Projects/obsidian-agent
devenv shell -- pytest -q

cd /home/andrew/Documents/Projects/obsidian-ops
devenv shell -- pytest -q

cd /home/andrew/Documents/Projects/forge
devenv shell -- go test ./...
```

Expected outcomes:

- Python repos should be green.
- Forge should compile/test clean before refactor edits.

If any baseline fails, stop and fix baseline first.

---

## 6) Branching, Commit, And PR Strategy

Use stacked branches to keep risk low.

Suggested branch order:

1. `refactor/obsidian-ops-boundary-lock`
2. `refactor/obsidian-agent-contract-cutover`
3. `refactor/forge-thin-host-cutover`
4. `refactor/integration-and-docs`

Commit style:

- one behavior per commit
- tests in same commit as code change
- commit message format:
  - `ops: ...`
  - `agent: ...`
  - `forge: ...`
  - `docs: ...`

PR style:

- each PR includes scope, contract changes, test evidence, rollback plan.

---

## 7) Verification Strategy Overview

Every phase has four verification layers.

### Layer 1: Unit/Module tests

Validate direct behavior in owning repo.

### Layer 2: Contract tests

Validate payload and response shapes at API boundary.

### Layer 3: Integration tests

Validate multi-module behavior within repo.

### Layer 4: Manual end-to-end checks

Validate real user flow across processes (`forge` + `obsidian-agent`).

### Required Evidence Format Per Step

Record for each step:

1. commands run
2. pass/fail outcome
3. unexpected warnings/errors
4. follow-up fix (if needed)

Do not mark a step complete without this evidence.

## 8) Phase 0 — Baseline And Safety Net

### Step 0.1 — Create Working Branches

**Objective**: prevent mixed changes and enable clean rollback.

**Tasks**:

1. Create branch in each repo using agreed sequence.
2. Verify clean working trees before edits.

**Commands**:

```bash
cd /home/andrew/Documents/Projects/obsidian-ops
git checkout -b refactor/obsidian-ops-boundary-lock
git status --short

cd /home/andrew/Documents/Projects/obsidian-agent
git checkout -b refactor/obsidian-agent-contract-cutover
git status --short

cd /home/andrew/Documents/Projects/forge
git checkout -b refactor/forge-thin-host-cutover
git status --short
```

**Test/Verification**:

- Verification is repo-state based.
- Each repo should show only intended baseline modifications (or clean if no prior local changes).

**Done criteria**:

- all 3 branches created and isolated.

---

### Step 0.2 — Capture Baseline Test State

**Objective**: know what “green” looked like before any changes.

**Commands**:

```bash
cd /home/andrew/Documents/Projects/obsidian-ops
devenv shell -- pytest -q

cd /home/andrew/Documents/Projects/obsidian-agent
devenv shell -- pytest -q

cd /home/andrew/Documents/Projects/forge
devenv shell -- go test ./...
```

**What to record**:

- pass/fail status
- total tests run
- total runtime

**Done criteria**:

- baseline captured in notes or PR description.

---

### Step 0.3 — Capture Current Contract Snapshots

**Objective**: preserve old contract behavior for regression comparison.

**Tasks**:

1. Record current `ops.js` payload shape.
2. Record current `obsidian-agent` request model behavior.
3. Record current Forge dev wiring behavior (proxy vs in-process handler).

**Verification**:

- code inspection evidence in notes with exact file references.

**Done criteria**:

- old-state contract summary exists.

---

## 9) Phase 1 — obsidian-ops Boundary Hardening

### Step 1.1 — Audit And Lock VCS API Surface

**Objective**: ensure VCS responsibilities are centralized and explicit.

**Primary files**:

- `src/obsidian_ops/vault.py`
- `src/obsidian_ops/vcs.py`
- `src/obsidian_ops/errors.py`
- `src/obsidian_ops/__init__.py`

**Implementation tasks**:

1. Confirm `Vault.commit(...)` and `Vault.undo_last_change()` are the intended high-level APIs.
2. If needed, add typed result objects for commit/undo outcomes.
3. Ensure error semantics are explicit (`VCSError` for JJ failures, warning for partial undo restore failures).

**Testing**:

```bash
cd /home/andrew/Documents/Projects/obsidian-ops
devenv shell -- pytest -q tests/test_vcs.py tests/test_vault.py tests/test_integration.py
```

**What to verify**:

- commit path invokes `jj describe` then `jj new`
- undo lifecycle behavior matches expected warning/restore semantics
- no direct JJ access required by callers beyond Vault APIs

**Done criteria**:

- API boundary is explicit and tested.

---

### Step 1.2 — Validate Server Mapping To Library APIs

**Objective**: optional server remains consistent with library semantics.

**Primary file**:

- `src/obsidian_ops/server.py`

**Implementation tasks**:

1. Ensure `/vcs/commit` and `/vcs/undo` delegate to `Vault` APIs.
2. Confirm status/error mapping is deterministic.
3. Ensure health and status responses are contract-stable.

**Testing**:

```bash
cd /home/andrew/Documents/Projects/obsidian-ops
devenv shell -- pytest -q tests/test_server.py
```

**What to verify**:

- 424 vs 500 mapping for VCS precondition vs execution failures
- undo returns warning field when restore fails

**Done criteria**:

- server contract mirrors library behavior.

---

### Step 1.3 — Document The Boundary For Upstream Users

**Objective**: prevent future leakage of VCS logic into agent/service layers.

**Primary file**:

- `README.md`

**Implementation tasks**:

1. Explicitly document `Vault` VCS usage contract.
2. State that upstream consumers should not shell out to JJ directly.

**Testing**:

- doc validation is review-based.
- run smoke tests to ensure no accidental code breakage:

```bash
cd /home/andrew/Documents/Projects/obsidian-ops
devenv shell -- pytest -q tests/test_smoke.py
```

**Done criteria**:

- docs and tests both confirm boundary.

---

## 10) Phase 2 — obsidian-agent Contract Cutover

### Step 2.1 — Update Request Model To New Contract

**Objective**: accept only new cutover contract.

**Primary file**:

- `src/obsidian_agent/models.py`

**Required request contract**:

- `instruction: str` (required semantics)
- `current_file: str | None` (vault-relative path)
- `interface_id: str | None` (default behavior resolves to `command`)

**Implementation tasks**:

1. Add `interface_id` field with strict validation (non-empty when provided).
2. Keep `extra='forbid'` behavior.
3. Keep `current_file` path validation strict.

**Tests to add/update**:

- `tests/test_models.py`

**Testing**:

```bash
cd /home/andrew/Documents/Projects/obsidian-agent
devenv shell -- pytest -q tests/test_models.py
```

**What to verify**:

- payload containing `current_url_path` fails (422)
- payload containing valid `current_file` passes
- payload with malformed `interface_id` fails validation

**Done criteria**:

- request model is cutover-ready.

---

### Step 2.2 — Add Interface Dispatch Registry

**Objective**: avoid endpoint sprawl and prepare for future UI modes.

**Primary files**:

- `src/obsidian_agent/app.py`
- optionally new module: `src/obsidian_agent/interfaces.py`

**Implementation tasks**:

1. Introduce registry map for interface handlers.
2. Register default `command` handler.
3. Route `/api/apply` through registry based on `interface_id`.
4. If `interface_id` missing, default to `command`.
5. Return deterministic error for unknown interface IDs.

**Tests to add/update**:

- `tests/test_app.py`

**Testing**:

```bash
cd /home/andrew/Documents/Projects/obsidian-agent
devenv shell -- pytest -q tests/test_app.py
```

**What to verify**:

- default dispatch when `interface_id` omitted
- correct handler when `interface_id='command'`
- clear error path for unsupported interface id

**Done criteria**:

- interface dispatch is pluggable and tested.

---

### Step 2.3 — Keep VCS Delegation Fully In obsidian-ops

**Objective**: enforce dependency boundary.

**Primary file**:

- `src/obsidian_agent/agent.py`

**Implementation tasks**:

1. Confirm apply flow uses `vault.commit(...)` only.
2. Confirm undo flow uses `vault.undo_last_change()` only.
3. Remove any raw JJ subprocess usage if discovered.

**Tests to update**:

- `tests/test_agent.py`

**Testing**:

```bash
cd /home/andrew/Documents/Projects/obsidian-agent
devenv shell -- pytest -q tests/test_agent.py tests/test_integration.py
```

**What to verify**:

- commit warning behavior still surfaced to API response
- undo warning behavior propagated cleanly
- busy/timeouts still mapped correctly

**Done criteria**:

- no direct JJ orchestration in agent.

---

### Step 2.4 — Full Agent Repo Validation

**Objective**: prove no regressions before touching Forge.

**Testing**:

```bash
cd /home/andrew/Documents/Projects/obsidian-agent
devenv shell -- pytest -q
```

**Done criteria**:

- full suite green.

---

## 11) Phase 3 — Forge Backend Cutover (Proxy-Only API Path)

### Step 3.1 — Remove In-Process Go Ops Runtime Wiring

**Objective**: Forge must stop serving `/api/*` via `internal/ops` in-process runtime.

**Primary file**:

- `internal/cli/dev.go`

**Implementation tasks**:

1. Remove `internal/ops` runtime handler construction in `runDev`.
2. Remove ops-specific dev flags used only by in-process agent wiring.
3. Keep proxy creation and mux wiring.
4. Ensure `ForgeConfig.APIHandler` is `nil` so `/api/*` uses proxy fallback.

**Testing**:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- go test ./internal/server ./internal/cli ./internal/proxy
```

**What to verify**:

- build compiles without ops runtime dependencies in dev path
- `NewForgeHandler` fallback behavior still intact

**Done criteria**:

- runtime API path is proxy-first and in-process ops is not wired.

---

### Step 3.2 — Preserve Watch/Build Behavior After Agent Mutations

**Objective**: ensure file changes from Python backend still trigger rebuild.

**Primary files**:

- `internal/watch/watcher.go`
- `internal/watch/changeset.go`

**Implementation tasks**:

1. Confirm no hidden coupling to in-process ops rebuild callback remains.
2. Keep watcher-driven rebuild flow as source of truth.

**Testing**:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- go test ./internal/watch ./internal/builder
```

**Done criteria**:

- watcher and incremental build tests remain green.

---

### Step 3.3 — Update Dev Command Documentation

**Objective**: avoid stale docs/flags confusing future developers.

**Primary files**:

- docs command docs for `dev`
- README sections describing ops backend behavior

**Implementation tasks**:

1. Remove references to in-process ops flags if removed.
2. Document proxy backend requirement for `/api/*` functionality.

**Testing**:

- docs review + compile check:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- go test ./...
```

**Done criteria**:

- docs match runtime behavior.

---

## 12) Phase 4 — Forge Frontend Cutover (`ops.js` + Page Context Metadata)

### Step 4.1 — Emit `current_file` Metadata In Rendered Pages

**Objective**: frontend must have canonical vault-relative file context on note pages.

**Primary files**:

- `internal/templates/*.templ` (likely shared or page-level template)
- generated `internal/templates/*_templ.go`

**Implementation tasks**:

1. Add hidden metadata element or meta tag containing `current_file` for note pages (`data.File.RelPath`).
2. Emit empty/absent metadata for non-note pages.
3. Regenerate templ-generated Go files.

**Template generation command** (example; use repo-standard if different):

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- templ generate ./internal/templates
```

**Testing**:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- go test ./internal/templates ./internal/builder
```

**What to verify**:

- template render compiles
- note pages include `current_file` metadata
- non-note pages do not inject fake paths

**Done criteria**:

- frontend can read canonical `current_file` context.

---

### Step 4.2 — Update `ops.js` Payload Contract

**Objective**: browser sends new backend contract.

**Primary file**:

- `static/ops.js`

**Implementation tasks**:

1. Replace payload field `current_url_path` with `current_file`.
2. Add `interface_id: "command"` to payload.
3. Add safe fallback when `current_file` metadata is missing (`null`).
4. Keep existing run/undo UX behavior.

**Testing**:

- static smoke: ensure syntax validity and no obvious runtime errors
- integration validation in Phase 5

Quick sanity checks:

```bash
cd /home/andrew/Documents/Projects/forge
rg -n "current_url_path" static/ops.js
rg -n "current_file|interface_id" static/ops.js
```

Expected:

- no `current_url_path` references remain in `ops.js`
- payload includes `current_file` and `interface_id`

**Done criteria**:

- payload shape is cutover-complete.

---

### Step 4.3 — Full Forge Repo Validation

**Objective**: verify Forge still builds/serves correctly after template + JS + dev wiring changes.

**Testing**:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- go test ./...
```

**Done criteria**:

- all Forge tests pass.

---

## 13) Phase 5 — End-To-End Integration Validation

### Step 5.1 — Run Two-Process Local Stack

**Objective**: validate real architecture, not just repo-local tests.

**Terminal A (obsidian-agent)**:

```bash
cd /home/andrew/Documents/Projects/obsidian-agent
export AGENT_VAULT_DIR=/absolute/path/to/test-vault
export AGENT_HOST=127.0.0.1
export AGENT_PORT=8081
devenv shell -- obsidian-agent
```

**Terminal B (forge)**:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- go run ./cmd/forge dev --proxy-backend http://127.0.0.1:8081 --inject-overlay
```

### Step 5.2 — Contract-Level HTTP Checks

**Commands**:

```bash
curl -sS http://127.0.0.1:8081/api/health
curl -sS -X POST http://127.0.0.1:8081/api/apply -H 'content-type: application/json' -d '{"instruction":"no-op check","current_file":"index.md","interface_id":"command"}'
```

**Expected**:

- health returns `{ok:true,status:"healthy"}`
- apply returns valid `OperationResult` shape

### Step 5.3 — Browser Overlay Flow Checks

Manual checks:

1. Open a note page in Forge output.
2. Open overlay.
3. Submit a simple instruction.
4. Confirm backend executes without schema error.
5. Refresh page and verify content changed.
6. Click undo; verify state restored.

### Step 5.4 — Negative Case Checks

Run at least these negative tests:

1. Send payload with `current_url_path` and confirm validation failure.
2. Send unknown `interface_id` and confirm deterministic error.
3. Submit concurrent requests and verify busy behavior (409).

**Done criteria**:

- end-to-end positive + negative flows pass.

---

## 14) Phase 6 — Cleanup, Documentation, And Release Readiness

### Step 6.1 — Remove/Archive Obsolete Runtime Paths

**Objective**: prevent accidental fallback to old architecture.

**Tasks**:

1. Ensure no runtime wiring paths reference in-process Go ops backend.
2. If keeping `internal/ops` source temporarily, mark clearly as deprecated/non-runtime.
3. Prefer removing dead runtime references from docs and code comments.

**Testing**:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- go test ./...
```

### Step 6.2 — Update All Refactor Docs

Update:

- architecture plan docs in `.scratch/projects/07-forge-architecture-refactor-plan/`
- repo READMEs where runtime behavior changed

### Step 6.3 — Release Readiness Checklist

Before merge:

1. all test gates green in all repos
2. no TODO markers left in changed files
3. API contract docs match implementation
4. reviewer checklist (Section 19) passes

---

## 15) Detailed Test Matrix By Step

Use this as an execution log template.

| Step | Repository | Command(s) | Expected Result | Failure Means |
|---|---|---|---|---|
| 0.2 | obsidian-ops | `devenv shell -- pytest -q` | full suite passes | baseline instability in ops repo |
| 0.2 | obsidian-agent | `devenv shell -- pytest -q` | full suite passes | baseline instability in agent repo |
| 0.2 | forge | `devenv shell -- go test ./...` | full suite passes | baseline instability in forge repo |
| 1.1 | obsidian-ops | `devenv shell -- pytest -q tests/test_vcs.py tests/test_vault.py tests/test_integration.py` | VCS behavior and integration green | boundary/API behavior changed unexpectedly |
| 1.2 | obsidian-ops | `devenv shell -- pytest -q tests/test_server.py` | server contract and error mapping green | server/library contract mismatch |
| 1.3 | obsidian-ops | `devenv shell -- pytest -q tests/test_smoke.py` | package surface still valid | accidental import/API break |
| 2.1 | obsidian-agent | `devenv shell -- pytest -q tests/test_models.py` | request model validation green | model contract is wrong |
| 2.2 | obsidian-agent | `devenv shell -- pytest -q tests/test_app.py` | route + dispatch behavior green | runtime API contract drift |
| 2.3 | obsidian-agent | `devenv shell -- pytest -q tests/test_agent.py tests/test_integration.py` | orchestration + VCS delegation green | agent boundary violation or logic regression |
| 2.4 | obsidian-agent | `devenv shell -- pytest -q` | full suite green | unresolved regressions |
| 3.1 | forge | `devenv shell -- go test ./internal/server ./internal/cli ./internal/proxy` | proxy-only API path compiles/tests green | dev wiring broken |
| 3.2 | forge | `devenv shell -- go test ./internal/watch ./internal/builder` | watcher/build behavior green | rebuild flow regression |
| 3.3 | forge | `devenv shell -- go test ./...` | docs-related edits did not break code | hidden compile or test failures |
| 4.1 | forge | `devenv shell -- templ generate ./internal/templates` then `devenv shell -- go test ./internal/templates ./internal/builder` | templates compile and render cleanly | metadata/template integration is broken |
| 4.2 | forge | `rg -n "current_url_path" static/ops.js` | no matches | old contract still present |
| 4.2 | forge | `rg -n "current_file|interface_id" static/ops.js` | expected matches | cutover payload incomplete |
| 4.3 | forge | `devenv shell -- go test ./...` | full suite green | unresolved forge regression |
| 5.2 | integrated | `curl /api/health`, `curl POST /api/apply` | valid health + result JSON | runtime stack/config mismatch |
| 5.3 | integrated | manual overlay apply/undo flow | visible successful mutation + undo | end-to-end contract or rebuild issues |
| 5.4 | integrated | negative payload checks | expected validation and busy errors | weak validation or error mapping drift |

---

## 16) Troubleshooting Playbook

### Problem A: `obsidian-agent` rejects apply requests with 422

Likely causes:

1. Frontend still sends `current_url_path`.
2. Missing required JSON keys.
3. `current_file` is invalid path format.

Fix path:

1. inspect browser network payload in devtools.
2. confirm payload contains only allowed fields.
3. run:

```bash
cd /home/andrew/Documents/Projects/forge
rg -n "current_url_path|current_file|interface_id" static/ops.js
```

4. rerun `tests/test_models.py` + `tests/test_app.py` in agent repo.

### Problem B: Apply works but refresh does not show updated content

Likely causes:

1. watcher did not detect file change.
2. user refreshed too early after mutation.
3. file changed outside watched vault path.

Fix path:

1. confirm Forge watcher logs show rebuild after file mutation.
2. verify `AGENT_VAULT_DIR` points at same vault Forge uses as input.
3. run watch tests:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- go test ./internal/watch ./internal/builder
```

### Problem C: Undo returns warning or fails

Likely causes:

1. JJ workspace state invalid.
2. `jj undo` succeeded but restore failed.
3. environment missing JJ binary.

Fix path:

1. inspect warning text returned in API response.
2. verify JJ installed and workspace valid.
3. rerun VCS tests in ops repo:

```bash
cd /home/andrew/Documents/Projects/obsidian-ops
devenv shell -- pytest -q tests/test_vcs.py tests/test_server.py
```

### Problem D: Forge dev fails after removing in-process ops wiring

Likely causes:

1. stale imports/flags in `dev.go`.
2. missing proxy backend configuration.
3. dead references to removed ops config variables.

Fix path:

1. run targeted compile tests:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- go test ./internal/cli ./internal/server ./internal/proxy
```

2. confirm runtime command includes `--proxy-backend`.

### Problem E: Template changes compile locally but fail in CI

Likely causes:

1. generated templ files not updated.
2. generator version mismatch.

Fix path:

1. regenerate templates in Forge repo.
2. rerun full Go test suite.
3. ensure generated files are committed.

---

## 17) Rollback And Recovery Plan

### Rollback Triggers

Rollback if any of these happens in staging/dev:

1. overlay cannot apply/undo consistently.
2. mutation path causes frequent 5xx errors.
3. rebuild loop becomes unstable.

### Rollback Strategy

1. Revert Forge cutover commit(s) first (restores old runtime behavior).
2. Keep `obsidian-agent`/`obsidian-ops` changes if they are independently safe.
3. If needed, roll back agent contract changes to last known green tag.

### Recovery Strategy

1. Reproduce failure using matrix step that failed.
2. Write minimal failing test first.
3. fix and rerun targeted + full suites.
4. re-run Phase 5 end-to-end validation.

---

## 18) Checklist

### During implementation

1. make one logical change.
2. run smallest relevant tests.
3. fix failures before moving on.
4. commit with clear scope.

---

## 19) Final Sign-Off Checklist

Refactor should not be approved until all are true.

1. Forge runtime no longer wires in-process Go ops backend in `dev` path.
2. `ops.js` payload is `instruction + current_file + interface_id`; `current_url_path` removed.
3. `obsidian-agent` model rejects unknown fields and validates `current_file` strictly.
4. Interface dispatch exists and defaults to `command` cleanly.
5. `obsidian-agent` contains no direct JJ subprocess orchestration.
6. `obsidian-ops` is the source of truth for commit/undo behavior.
7. All matrix test commands were executed and evidence provided.
8. End-to-end manual validation (apply + undo) passed on two-process runtime.
9. Docs in all three repos reflect the new architecture and contract.
10. Rollback steps are documented and practical.
