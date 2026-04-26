# PROGRESS

## Status

- [x] Created new numbered project template directory.
- [x] Reviewed architecture brief and existing review docs.
- [x] Analyzed Forge integration points and current API contract.
- [x] Analyzed `obsidian-agent` and `obsidian-ops` source/tests.
- [x] Validated dependency test baselines locally.
- [x] Collected user clarifications for cutover direction.
- [x] Wrote `ARCHITECTURE_REFACTOR_PLAN.md` with recommended defaults.
- [x] Confirmed final preference for URL-resolution ownership and process topology.
- [x] Wrote `ARCHITECTURE_REFACTOR_GUIDE.md` with step-by-step implementation and per-step test verification guidance for a new intern.
- [x] Phase 0.1 complete: created refactor working branches in all repos.
- [x] Phase 0.2 complete: captured baseline test state across all repos.
- [x] Phase 0.3 complete: captured contract snapshots for frontend payload, agent request model, and Forge API wiring.
- [x] Phase 1 complete (`obsidian-ops`): VCS boundary validated and documented.
- [x] Phase 2 complete (`obsidian-agent`): request contract cutover + interface dispatch registry.
- [x] Phase 3 complete (`forge`): proxy-only dev API path (no in-process ops wiring).
- [x] Phase 4 complete (`forge`): page context metadata + `ops.js` payload cutover.
- [x] Phase 5 complete (partial manual): two-process stack and contract checks executed via local HTTP.
- [x] Phase 6 complete: deprecated runtime path marked, docs/progress updated.

## Execution Evidence

### Step 0.2 baseline tests

- `obsidian-ops`: `devenv shell -- pytest -q` passed (all tests green; coverage reported 96%).
- `obsidian-agent`: `devenv shell -- pytest -q` passed (`122 passed in 26.34s`).
- `forge`: `devenv shell -- go test ./...` failed before refactor edits:
  - `internal/builder` `TestGeneratePageOGImages` failed with missing `og.png`.
  - `internal/templates` `TestHead_OGMetaTags` failed due expected `.../og.png` and `.../twitter.png` path format mismatch.

### Step 0.3 contract snapshot

- Frontend payload currently uses legacy field:
  - `static/ops.js`: payload contains `current_url_path: getCurrentUrlPath()`.
- Agent request model currently accepts:
  - `instruction: str | None`, `current_file: str | None`, with `extra="forbid"`.
  - no `interface_id` field yet in `src/obsidian_agent/models.py`.
- Forge dev runtime currently wires in-process ops API:
  - `internal/cli/dev.go` imports `internal/ops`, constructs `opsHandler`, assigns `APIHandler: opsHandler`.

### Phase 1 (`obsidian-ops`) execution summary

- Step 1.1 command: `devenv shell -- pytest -q tests/test_vcs.py tests/test_vault.py tests/test_integration.py` passed.
- Step 1.2 command: `devenv shell -- pytest -q tests/test_server.py` passed.
- Step 1.3 command: `devenv shell -- pytest -q tests/test_smoke.py` passed.
- Boundary note: README now explicitly calls direct upstream `jj` subprocess usage a boundary violation.

### Phase 2 (`obsidian-agent`) execution summary

- Step 2.1 command: `devenv shell -- pytest -q tests/test_models.py` passed.
- Step 2.2 command: `devenv shell -- pytest -q tests/test_app.py` passed.
- Step 2.3 command: `devenv shell -- pytest -q tests/test_agent.py tests/test_integration.py` passed.
- Step 2.4 command: `devenv shell -- pytest -q` passed (`130 passed`).
- Contract changes in place:
  - request supports `instruction`, `current_file`, optional `interface_id`
  - unknown fields rejected (`extra="forbid"`)
  - unknown `interface_id` returns deterministic 400.

### Phase 3 (`forge`) execution summary

- Step 3.1 command: `devenv shell -- go test ./internal/server ./internal/cli ./internal/proxy` passed.
- Step 3.2 command: `devenv shell -- go test ./internal/watch ./internal/builder`
  - `internal/watch` passed.
  - `internal/builder` preserved baseline failure (`TestGeneratePageOGImages` missing `og.png`).
- Step 3.3 command: `devenv shell -- go test ./...`
  - no new compile regressions from proxy-only cutover.
  - baseline failures persisted (`internal/builder`, `internal/templates` OG path expectation mismatch).

### Phase 4 (`forge`) execution summary

- Step 4.1 command: `devenv shell -- templ generate ./internal/templates` executed.
- Step 4.1 validation command: `devenv shell -- go test ./internal/templates ./internal/builder`
  - preserved baseline failures only.
- Step 4.2 checks:
  - `rg -n "current_url_path" static/ops.js` returned no matches.
  - `rg -n "current_file|interface_id" static/ops.js` confirmed payload fields present.
- Step 4.3 command: `devenv shell -- go test ./...`
  - same baseline failures persisted (`internal/builder`, `internal/templates`).

### Phase 5 integrated runtime checks

- Started `obsidian-agent` on `127.0.0.1:8081` with `AGENT_VAULT_DIR=/tmp/forge_refactor_vault`.
- Started `forge dev` on `127.0.0.1:8080` with `--proxy-backend http://127.0.0.1:8081 --inject-overlay --overlay-dir ./static`.
- Positive contract checks:
  - `GET http://127.0.0.1:8081/api/health` returned healthy.
  - `GET http://127.0.0.1:8080/api/health` returned healthy (proxy path confirmed).
  - `POST /api/apply` with whitespace instruction and `{current_file, interface_id}` returned valid `OperationResult`.
- Negative contract checks:
  - payload with `current_url_path` rejected with 422.
  - payload with unknown `interface_id` rejected with deterministic error.
- Note:
  - full browser-driven manual apply/undo was not executed in this CLI-only run.
  - busy (409) was validated by automated tests in `obsidian-agent/tests/test_app.py` and `tests/test_agent.py`.

### Phase 6 cleanup and docs

- Added `internal/ops/README.md` marking the package as deprecated for runtime wiring.
- Updated Forge README to state `/api/*` is proxy-only in `forge dev`.
