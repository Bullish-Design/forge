# ARCHITECTURE_REFACTOR_PLAN

## Confirmed Inputs

- Switch immediately to `current_file` (no compatibility bridge for `current_url_path`).
- One cutover is acceptable across frontend/backend contracts.
- Commit/undo responsibility should be pushed to `obsidian-ops` APIs.
- Multi-phase delivery is acceptable.

## Final Decisions Applied In This Plan

1. URL-to-file ownership: Forge (build/render layer).
2. Deployment topology for v1: two processes (`forge` + `obsidian-agent`), with `obsidian-ops` as library dependency; standalone `obsidian-ops` server remains optional.

## Target Architecture

### Forge (Go)

Owns:
- Vault rendering/build/watch.
- Overlay injection and `/ops/*` static assets.
- Reverse proxy for `/api/*` to backend.
- Emitting page context metadata (`current_file`) into rendered HTML.

Does not own:
- LLM orchestration.
- Vault mutation logic.
- JJ lifecycle logic.
- URL-path resolution inside agent request handling.

### obsidian-agent (Python)

Owns:
- `/api/apply`, `/api/undo`, `/api/health`.
- Tool-calling orchestration and response shaping.
- Interface dispatch (`interface_id`) at API layer.

Does not own:
- Raw file sandbox logic.
- Raw JJ subprocess handling.
- Forge routing/path index logic.

### obsidian-ops (Python)

Owns:
- Sandboxed file operations.
- Frontmatter/content patch primitives.
- VCS primitives (commit/undo/status) and related typed errors.
- Optional standalone HTTP server for non-agent consumers.

## Contract Plan

### Phase 1 Contract (Cutover Contract)

`POST /api/apply` request:
- `instruction` (required string)
- `current_file` (optional vault-relative path)
- `interface_id` (optional, default `"command"`)

`POST /api/undo` request:
- no body

`GET /api/health` response:
- `{ "ok": true, "status": "healthy" }`

`current_url_path` is removed from accepted request schema.

### Current File Source Of Truth

- Forge injects note-level metadata with vault-relative path (e.g. meta tag or hidden data node).
- `static/ops.js` reads this metadata and sends `current_file`.
- Folder/tag/graph pages can send `null`; backend treats missing `current_file` as valid.

## Workstreams

### W1: obsidian-ops hardening (dependency first)

1. Ensure commit/undo API is the sole VCS interface consumed by agent.
2. Add/confirm typed result contracts for commit/undo flows where warning states are possible.
3. Keep server endpoints aligned with library behavior and error mapping.
4. Add tests for any new commit/undo API entrypoints and warning semantics.

Exit criteria:
- `devenv shell -- pytest -q` passes in `obsidian-ops`.
- Agent can consume VCS purely through `obsidian-ops` APIs.

### W2: obsidian-agent contract + orchestration

1. Update request model to accept `instruction`, optional `current_file`, optional `interface_id`.
2. Add interface dispatch registry internally, with `command` handler wired first.
3. Remove any expectation of `current_url_path`.
4. Keep VCS behavior delegated to `obsidian-ops` API methods only.
5. Update tests for schema, behavior, and busy/timeout/error paths.

Exit criteria:
- `devenv shell -- pytest -q` passes in `obsidian-agent`.
- `current_url_path` payloads are rejected.
- `current_file` cutover contract validated.

### W3: Forge thin-host cutover

1. Remove in-process Go ops wiring from `internal/cli/dev.go`.
2. Default `/api/*` to proxy path (`APIHandler=nil` behavior).
3. Remove ops-specific Go flags and dependencies from Forge runtime path.
4. Inject `current_file` metadata into rendered note pages.
5. Update `static/ops.js` to send new payload shape in one cutover:
   - `{ instruction, current_file, interface_id }`
6. Keep overlay UX flow unchanged otherwise.

Exit criteria:
- Forge no longer depends on `internal/ops` for runtime behavior.
- `/api/*` traffic reaches Python backend through proxy.
- Frontend sends `current_file` and never sends `current_url_path`.

### W4: Integration/deploy

1. Run two-process local stack:
   - Forge dev server
   - obsidian-agent API server
2. Set proxy timeout > agent timeout.
3. Validate end-to-end apply + undo + rebuild/watch behavior.
4. Add deployment notes for optional future standalone `obsidian-ops` server mode.

Exit criteria:
- End-to-end mutation loop works through proxy.
- Undo works and rebuilds are reflected.
- Health checks pass for both components.

## Cutover Sequence

1. Land `obsidian-ops` updates and release/tag.
2. Land `obsidian-agent` cutover contract and release/tag.
3. Land Forge cutover (UI payload + proxy-only API path + metadata emission).
4. Deploy both services together in one release window.
5. Remove or archive obsolete Go `internal/ops` runtime path.

## Validation Gates

### Dependency gates

- `obsidian-ops`: full test suite green.
- `obsidian-agent`: full test suite green.

### Forge gates

- Existing Go test suites green.
- Manual/e2e check:
  1. Open note page.
  2. Trigger apply from overlay.
  3. Backend receives `current_file`.
  4. Mutation committed via `obsidian-ops`.
  5. Page refresh shows rebuilt output.
  6. Undo restores previous state.

## Risks And Mitigations

1. Missing `current_file` metadata on some page types.
   - Mitigation: treat `current_file` as optional; add frontend guard and backend safe fallback.
2. Proxy timeout shorter than agent timeout.
   - Mitigation: explicit config check and docs; startup warning if misconfigured.
3. One-cutover coordination across repos.
   - Mitigation: release branch checklist and lock-step deploy steps.
4. Rebuild timing race via watcher.
   - Mitigation: keep UX messaging (`Refresh page`) and optionally add a short post-apply poll/retry in UI.

## Post-Cutover Phase (Optional)

After stable cutover:
1. Expand `interface_id` registry beyond `command` (chat/review/etc.).
2. Add SSE progress streaming.
3. Optionally run `obsidian-ops` as standalone network service for external consumers.
