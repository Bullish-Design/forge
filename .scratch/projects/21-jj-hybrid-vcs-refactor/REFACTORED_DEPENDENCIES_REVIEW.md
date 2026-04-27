# Refactored Dependencies Review

Date: 2026-04-26  
Project: Forge v2 jj hybrid VCS integration  
Scope reviewed:
- `/home/andrew/Documents/Projects/obsidian-ops`
- `/home/andrew/Documents/Projects/obsidian-agent`
- current Forge integration points in this repo

## Executive Summary
The dependency refactor has substantially landed in `obsidian-ops` and `obsidian-agent`.

What is now available upstream:
- jj/git-bridge readiness and safe migration checks
- jj sync lifecycle (fetch/rebase/push)
- conflict bookmark creation + persisted sync state
- API endpoints in `obsidian-agent` for sync readiness/ensure/remote/fetch/push/sync/status
- optional post-commit sync in `obsidian-agent` (`AGENT_SYNC_AFTER_COMMIT=true`)

What Forge still needs to change to integrate correctly:
1. Stop owning duplicate git-sync logic in Forge (`docker/vault_git_sync.py` sidecar).
2. Pass through new agent sync env vars (`AGENT_SYNC_AFTER_COMMIT`, `AGENT_SYNC_REMOTE`) in process manager/runtime.
3. Add startup orchestration in Forge Docker entrypoint to call agent sync endpoints:
- `POST /api/vault/vcs/sync/ensure`
- `PUT /api/vault/vcs/sync/remote`
4. Update Docker env/docs to agent-native sync contract.
5. Treat migration/conflict state from agent endpoints as first-class operator signals.

Bottom line: Forge should now piggyback on agent/ops sync features instead of maintaining separate sync code.

---

## 1) Upstream Dependency State

## 1.1 `obsidian-ops` (reviewed repo)
- Version in repo: `0.7.1` (`pyproject.toml`)
- Changelog confirms jj sync capability rollout (`CHANGELOG.md`):
  - sync readiness and safe initialization
  - remote configuration with token helper
  - fetch/push/sync lifecycle
  - conflict bookmark workflow
  - sync state persistence

### Key capabilities found in `obsidian_ops.vault.Vault`
File: `src/obsidian_ops/vault.py`

- Hybrid readiness classification:
  - `check_sync_readiness()` -> `ready | migration_needed | error`
  - distinguishes git-only clean vs dirty and colocated states
- Safe migration hook:
  - `ensure_sync_ready()` auto-colocates in safe states (`no vcs`, `git-only safe`)
  - avoids auto-mutation on risky states (`git-only dirty`, ambiguous)
- Remote + auth:
  - `configure_sync_remote(url, token, remote)`
  - writes helper at `.forge/git-credential.sh` when token present
- Sync ops:
  - `sync_fetch()`, `sync_push()`, `sync()`
  - rebase + conflict detection
  - conflict bookmark creation (`sync-conflict/<timestamp>` by default)
- Sync status persistence:
  - `.forge/sync-state.json`
  - exposed by `sync_status()`

### VCS model types
File: `src/obsidian_ops/vcs.py`
- `VCSReadiness`: `READY`, `MIGRATION_NEEDED`, `ERROR`
- `ReadinessCheck`
- `SyncResult`: `ok`, `conflict`, `conflict_bookmark`, `error`

Assessment:
- This is the core jj/git-bridge functionality Forge previously had to emulate.
- It already includes the hybrid migration behavior requested.

## 1.2 `obsidian-agent` (reviewed repo)
- Version in repo: `0.2.0` (`pyproject.toml`)
- Pins `obsidian-ops` source tag `v0.7.1` in `tool.uv.sources`

### New sync API surface
Files:
- `README.md`
- `src/obsidian_agent/routes/vault_routes.py`
- `src/obsidian_agent/models.py`

Endpoints exposed under `/api/vault/vcs/sync/*`:
- `GET /readiness`
- `POST /ensure`
- `PUT /remote`
- `POST /fetch`
- `POST /push`
- `POST /` (full sync)
- `GET /status`

Notable behavior:
- Sync conflict is modeled in response body (HTTP 200 with `sync_ok=false`, `conflict=true`)
- Validation and 409/424 mapping for busy/VCS errors are implemented

### Agent runtime sync behavior
Files:
- `src/obsidian_agent/config.py`
- `src/obsidian_agent/agent.py`

Config fields currently available:
- `AGENT_SYNC_AFTER_COMMIT` (bool, default false)
- `AGENT_SYNC_REMOTE` (default `origin`)

Runtime behavior:
- After a successful local commit in `/api/apply`, if `sync_after_commit=true`, agent calls `vault.sync(...)`.
- Sync result is reported via operation warning if failure/conflict occurs.

Assessment:
- Agent now provides enough sync/migration API surface for Forge to orchestrate startup and status.
- The current built-in automatic trigger is post-commit on apply, not a general file-system watcher loop.

---

## 2) Current Forge State (as reviewed)

Relevant Forge files:
- `src/forge_cli/processes.py`
- `docker/docker-compose.yml`
- `docker/vault_git_sync.py`
- `docker/entrypoint.py`
- `docker/.env.example`

Current issues relative to new dependency capabilities:

1. Duplicate sync ownership in Forge
- Forge currently runs a separate `vault-sync` sidecar using raw `git` commands.
- This bypasses agent/ops jj sync contract and duplicates responsibilities.

2. Missing sync env pass-through to agent
- `ProcessManager.start_agent()` currently passes LLM/env auth keys but not:
  - `AGENT_SYNC_AFTER_COMMIT`
  - `AGENT_SYNC_REMOTE`

3. No startup sync orchestration against agent API
- Forge Docker entrypoint does not call:
  - sync ensure endpoint
  - remote configuration endpoint

4. Docker env model still Git-sidecar-centric
- `.env.example` and compose are centered on `GIT_REPO_URL` + sidecar polling.
- Desired architecture should center on agent sync config and endpoints.

---

## 3) What Forge Needs To Change

## 3.1 High Priority (required for clean integration)

1. Remove Forge-owned git sync sidecar path
- Remove service: `vault-sync` from compose (after migration path is ready).
- Remove `docker/vault_git_sync.py` as sync authority.
- Keep Tailscale + Forge services.

2. Expand agent env pass-through in Forge runtime
File: `src/forge_cli/processes.py`
- Add pass-through keys at minimum:
  - `AGENT_SYNC_AFTER_COMMIT`
  - `AGENT_SYNC_REMOTE`
- Keep existing LLM pass-through keys.

3. Add agent sync bootstrap in Docker entrypoint
File: `docker/entrypoint.py`
- After launching forge stack and agent health readiness, call:
  - `POST /api/vault/vcs/sync/ensure`
  - if configured repo URL/token present: `PUT /api/vault/vcs/sync/remote`
- Handle responses:
  - `ready`: continue
  - `migration_needed`: log clear actionable warning and continue (hybrid fallback)
  - `error` / HTTP 424: fail startup or enter degraded mode based on policy

4. Rework Docker env template around agent sync API
File: `docker/.env.example`
- Introduce/retain agent-native vars:
  - `AGENT_SYNC_AFTER_COMMIT=true`
  - `AGENT_SYNC_REMOTE=origin`
- Add Forge bootstrap vars (for remote config call), e.g.:
  - `FORGE_SYNC_REMOTE_URL=...`
  - `FORGE_SYNC_GITHUB_TOKEN=...`
  - `FORGE_SYNC_REMOTE_NAME=origin`
  - `FORGE_SYNC_CONFLICT_PREFIX=sync-conflict`
- De-emphasize/remove sidecar polling vars (`GIT_SYNC_INTERVAL_SEC`, etc.) once sidecar removed.

## 3.2 Medium Priority (operational quality)

5. Add sync status visibility in Forge diagnostics
- Add a health check helper to query `/api/vault/vcs/sync/status`.
- Surface conflict state and last sync result in logs/docs.

6. Align demos to agent-native sync model
- Demo should exercise agent sync endpoints, not independent git loop.
- Add a step showing readiness/state and conflict reporting.

7. Add integration tests in Forge for sync wiring
- Validate pass-through env is set.
- Validate bootstrap remote configure call behavior.
- Validate migration-needed state handling does not crash the stack.

---

## 4) Mapping to Desired Requirements

Requested requirement | Upstream status | Forge action
---|---|---
jj primary in-app VCS | Implemented in ops/agent | Use agent/ops path only
GitHub sync via jj git bridge | Implemented in ops + exposed in agent sync endpoints | Remove Forge git sidecar and call agent sync endpoints
Bidirectional sync | Implemented in `vault.sync()` | Enable via agent sync flow
Auto conflict bookmark + continue | Implemented in ops `sync()` | Surface warnings/status in Forge
GITHUB_TOKEN auth | Implemented via `configure_sync_remote(token=...)` + helper | Pass token to bootstrap remote config endpoint
Event-driven sync | Agent provides post-commit trigger (`AGENT_SYNC_AFTER_COMMIT`) | Enable flag; decide if extra watcher needed for non-agent writes
Hybrid migration | Implemented in readiness/ensure APIs | Call `/ensure` at startup and respect `migration_needed`

Note on “event-driven”:
- Current upstream agent behavior is event-driven for agent-initiated write commits (post-commit hook).
- It is not a generic external file watcher loop by default.
- If external writers mutate vault files outside agent operations, you may still need a light trigger mechanism (or explicit sync endpoint calls) depending on product expectations.

---

## 5) Recommended Forge Integration Plan

Phase 1 (safe cutover)
1. Keep existing stack running.
2. Add sync env pass-through.
3. Add startup bootstrap calls (`ensure` + optional `remote`).
4. Enable `AGENT_SYNC_AFTER_COMMIT=true` in compose env.
5. Add status logging endpoint checks.

Phase 2 (remove duplication)
1. Remove `vault-sync` sidecar from compose.
2. Remove sidecar docs/env/options.
3. Update runbooks and demos.

Phase 3 (hardening)
1. Add integration tests for migration/conflict paths.
2. Validate private repo token flows end-to-end.
3. Add operational dashboards/alerts around sync status fields.

---

## 6) Risks and Mitigations

1. Version drift between agent and ops
- Risk: sync endpoint behavior mismatches due to dependency pin variance.
- Mitigation: pin tested agent tag and ops tag in Forge Docker build args.

2. Migration-needed states on existing volumes
- Risk: stack starts but sync never configured.
- Mitigation: explicit startup warnings and operator runbook actions when status is `migration_needed`.

3. Token handling mistakes
- Risk: auth failures or accidental logging.
- Mitigation: pass token only in API bootstrap body, never log request bodies, rely on ops credential helper file behavior.

4. Non-agent writes not triggering sync
- Risk: stale remote in mixed-writer environments.
- Mitigation: add periodic fallback sync endpoint trigger in Forge (optional) if needed by deployment profile.

---

## 7) Concrete Forge Change Checklist

- [ ] `src/forge_cli/processes.py`: include `AGENT_SYNC_AFTER_COMMIT`, `AGENT_SYNC_REMOTE` in pass-through.
- [ ] `docker/entrypoint.py`: implement sync bootstrap sequence (ensure + remote config).
- [ ] `docker/docker-compose.yml`: remove `vault-sync` service after bootstrap path is verified.
- [ ] `docker/.env.example`: replace git-sidecar vars with agent-sync/bootstrap vars.
- [ ] `docker/README.md`: rewrite architecture and operations for agent-native sync.
- [ ] tests: add Forge integration tests for sync bootstrap and migration-needed behavior.

---

## Final Assessment
Dependency refactor is materially complete upstream for the jj hybrid VCS goals. Forge should now pivot from “owning sync” to “orchestrating sync through agent/ops APIs.” The major remaining work is integration cleanup in Forge runtime/docker and operationalization of migration/conflict status handling.
