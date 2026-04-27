# Forge Integration Refactor Guide Plan

## Objective
Refactor Forge runtime/docker orchestration to consume the new `obsidian-agent` jj-sync functionality instead of maintaining parallel sync logic.

## Non-Goals
- Re-implementing sync logic in Forge once upstream is available
- Forking agent behavior in Forge runtime

## Desired End State
1. Forge relies on `obsidian-agent` as source of truth for:
- in-app jj VCS behavior
- migration handling status
- GitHub sync state/conflicts
2. Forge docker topology is simplified:
- remove duplicated jj/git sync sidecar if agent handles sync internally
- keep Tailscale sidecar networking
3. Forge config/CLI passes sync-related env/config through cleanly.
4. Demo/validation harness includes real jj-sync path checks.

## Target Architecture

### Current (interim)
- Forge container + Tailscale sidecar + external sync logic in Forge repo.

### Refactored
- Forge container (runs forge dev -> starts obsidian-agent) + Tailscale sidecar.
- Sync behavior configured via agent env vars only.
- Optional sidecar retained only for concerns not handled by agent (if any).

## Integration Contract to Consume
Assume `obsidian-agent` provides:
- sync config env vars
- startup migration decisioning
- status endpoint/health extension for sync state

Forge responsibilities:
- pass through env vars
- surface status in docs/demo
- avoid redundant mutation/sync workers

## Implementation Steps

### Phase A: Config Plumbing
1. Extend Forge config/docs with pass-through sync env variables:
- `AGENT_SYNC_*` set
- `GITHUB_TOKEN` pass-through
2. Ensure `ProcessManager.start_agent()` includes all required pass-through env.
3. Keep backward compatibility with previous env set.

### Phase B: Docker Topology Simplification
1. Update `docker/docker-compose.yml`:
- remove Forge-side sync sidecar (if fully replaced)
- pass `AGENT_SYNC_*` vars into `forge` service env
2. Update Docker docs and `.env.example` to agent-native sync knobs.
3. Preserve Tailscale state and service health gating.

### Phase C: Runtime Behavior + Status
1. Add Forge docs/runbook for migration states:
- `jj_ready`
- `migration_needed`
- `conflict_active`
2. If agent has sync status endpoint, add helper checks in docs/scripts.
3. Ensure Forge startup does not mask agent migration warnings.

### Phase D: Demo Harness Alignment
1. Update demo scripts to reflect agent-native sync flow.
2. Add a free-explore demo step showing sync status/health.
3. Add test hooks for:
- event-driven sync after apply
- conflict scenario visibility

### Phase E: Validation
1. Compose config validation (`docker compose config`).
2. End-to-end smoke:
- startup with valid sync vars
- apply/undo with sync enabled
- verify remote sync activity
3. Failure-path smoke:
- invalid token
- divergence/conflict
- migration-needed vault state

## Deliverables
- updated Forge docker files
- updated env template/docs
- updated process env pass-through
- demo/test updates proving integration

## Cutover Plan
1. Introduce feature flag in Forge docs: `AGENT_SYNC_ENABLED=true`.
2. Run dual-path staging (old vs agent-native).
3. Remove Forge-owned sync implementation after confidence window.

## Acceptance Criteria
- Forge no longer owns sync logic duplicating agent capabilities.
- With sync enabled, apply/undo triggers event-driven sync through agent stack.
- Conflict and migration states are visible and actionable from Forge operator perspective.

## Risks and Mitigations
- Risk: mismatch in expected agent env contract.
  Mitigation: pin tested obsidian-agent version/tag in compose and docs.
- Risk: hidden sync failures.
  Mitigation: mandatory status endpoint check + log assertions in validation scripts.
- Risk: migration edge cases.
  Mitigation: explicit fallback path documented; do not auto-mutate ambiguous states.
