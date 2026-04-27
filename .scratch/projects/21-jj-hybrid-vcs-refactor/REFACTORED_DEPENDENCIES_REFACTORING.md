# Forge Sync Integration Refactoring Plan

Date: 2026-04-26
Project: Forge v2 jj hybrid VCS integration
Scope: Replace forge-owned git sync sidecar with agent-native jj sync orchestration

---

## Objective

Eliminate the `vault-sync` sidecar and its duplicate git logic. Forge becomes
a thin orchestrator that delegates all VCS and sync operations to
obsidian-agent (which delegates to obsidian-ops). The result is a single sync
authority, cleaner Docker topology, and full access to jj features (conflict
bookmarks, bidirectional sync, hybrid VCS migration).

---

## Current State

```
┌─────────────┐     ┌──────────────────┐     ┌────────────┐
│  tailscale   │────▷│   vault-sync     │────▷│  GitHub     │
│  (network)   │     │  (git sidecar)   │     │  (remote)   │
└─────────────┘     │  polling loop    │     └────────────┘
                    │  raw git commands │
                    └────────┬─────────┘
                             │ shared volume
                    ┌────────▼─────────┐
                    │     forge        │
                    │  overlay+agent   │
                    │  +kiln           │
                    └──────────────────┘
```

Problems:
- Two sync authorities (sidecar uses raw git; agent uses jj)
- Sidecar polls on a timer regardless of agent activity
- No conflict detection or bookmark workflow
- No migration path from git-only to jj+git colocated
- Token handling duplicated between sidecar and agent
- Agent can't report sync state to callers

## Target State

```
┌─────────────┐     ┌──────────────────┐     ┌────────────┐
│  tailscale   │────▷│     forge        │────▷│  GitHub     │
│  (network)   │     │  overlay+agent   │     │  (remote)   │
└─────────────┘     │  +kiln           │     └────────────┘
                    │                  │
                    │  agent owns sync │
                    │  via obsidian-ops│
                    └──────────────────┘
```

One container (plus tailscale). Agent owns all VCS. Forge orchestrates startup
sync bootstrap and passes config. No sidecar.

---

## Phase 1: Config and Process Manager (safe, additive)

No behavior change. Existing sidecar continues to work alongside.

### 1.1 Add sync config fields to `ForgeConfig`

File: `src/forge_cli/config.py`

Add to `ForgeConfig`:

```python
# Sync configuration
sync_after_commit: bool = False
sync_remote: str = "origin"
sync_remote_url: str | None = None
sync_remote_token: str | None = None
```

Add to `_load_yaml_config()` a new nested `sync` block:

```python
sync = raw.get("sync")
if isinstance(sync, Mapping):
    if "after_commit" in sync:
        data["sync_after_commit"] = sync["after_commit"]
    if "remote" in sync:
        data["sync_remote"] = sync["remote"]
    if "remote_url" in sync:
        data["sync_remote_url"] = sync["remote_url"]
    if "remote_token" in sync:
        data["sync_remote_token"] = sync["remote_token"]
```

Add to `_render_default_config()`:

```python
"sync": {
    "after_commit": cfg.sync_after_commit,
    "remote": cfg.sync_remote,
    # remote_url and remote_token intentionally omitted from defaults
},
```

Env var names (automatic via pydantic-settings):
- `FORGE_SYNC_AFTER_COMMIT`
- `FORGE_SYNC_REMOTE`
- `FORGE_SYNC_REMOTE_URL`
- `FORGE_SYNC_REMOTE_TOKEN`

### 1.2 Pass sync env vars to agent process

File: `src/forge_cli/processes.py`

In `start_agent()`, add sync env vars to the explicit env dict:

```python
env={
    # ... existing vars ...
    "AGENT_SYNC_AFTER_COMMIT": str(config.sync_after_commit).lower(),
    "AGENT_SYNC_REMOTE": config.sync_remote,
}
```

These are always set. `sync_after_commit=false` (the default) means the agent
will not auto-sync, preserving current behavior.

Do NOT pass `sync_remote_url` or `sync_remote_token` as env vars. These are
sensitive and should only be sent via the bootstrap API call (phase 2). This
avoids tokens appearing in process environment listings.

### 1.3 Update forge.yaml.example

File: `forge.yaml.example`

Add sync section:

```yaml
sync:
  after_commit: false          # Auto-sync after each agent commit
  remote: origin               # Git remote name
  # remote_url: https://github.com/your-org/your-vault.git
  # remote_token: ghp_...      # GitHub PAT (prefer env var FORGE_SYNC_REMOTE_TOKEN)
```

### 1.4 Add tests

File: `tests/test_config.py`

- Test sync defaults (after_commit=false, remote="origin", url/token=None)
- Test nested YAML `sync:` block parsing
- Test env override (`FORGE_SYNC_AFTER_COMMIT=true`)

File: `tests/test_commands.py`

- Verify `start_agent()` passes `AGENT_SYNC_AFTER_COMMIT` and `AGENT_SYNC_REMOTE`
- Verify `start_agent()` does NOT pass `sync_remote_url` or `sync_remote_token`
- Verify `forge init` output includes sync section

### 1.5 Commit

```
feat: add sync config fields and agent env pass-through

Adds FORGE_SYNC_* config fields (after_commit, remote, remote_url,
remote_token) with YAML and env var support. Passes AGENT_SYNC_AFTER_COMMIT
and AGENT_SYNC_REMOTE to agent process. Token is not passed via env (sent
via API in phase 2).
```

---

## Phase 2: Startup Sync Bootstrap

Add a post-startup bootstrap sequence that calls agent sync endpoints to
initialize VCS state and configure the remote. This runs after the agent is
health-gated and before the user interacts with the system.

### 2.1 Add sync bootstrap to ProcessManager

File: `src/forge_cli/processes.py`

Add a new method:

```python
def bootstrap_sync(self, config: ForgeConfig) -> None:
    """Bootstrap VCS sync state via agent API after startup."""
    if not config.sync_remote_url:
        return  # No remote configured, skip bootstrap

    agent_base = config.agent_url

    # Step 1: Ensure jj workspace is initialized (colocates if needed)
    resp = httpx.post(f"{agent_base}/api/vault/vcs/sync/ensure", timeout=30.0)
    resp.raise_for_status()
    result = resp.json()

    if result["status"] == "error":
        raise ProcessLaunchError(
            f"Sync bootstrap failed: {result.get('detail', 'unknown error')}"
        )

    if result["status"] == "migration_needed":
        # Log warning but continue -- operator may need manual intervention
        import sys
        print(
            f"[forge] WARNING: vault sync migration needed: {result.get('detail')}",
            file=sys.stderr,
        )
        return

    # Step 2: Configure remote with URL and optional token
    remote_payload: dict[str, str] = {
        "url": config.sync_remote_url,
        "remote": config.sync_remote,
    }
    if config.sync_remote_token:
        remote_payload["token"] = config.sync_remote_token

    resp = httpx.put(
        f"{agent_base}/api/vault/vcs/sync/remote",
        json=remote_payload,
        timeout=30.0,
    )
    resp.raise_for_status()

    # Step 3: Initial sync (fetch + rebase + push)
    resp = httpx.post(
        f"{agent_base}/api/vault/vcs/sync",
        json={"remote": config.sync_remote},
        timeout=120.0,
    )
    resp.raise_for_status()
    sync_result = resp.json()

    if not sync_result.get("sync_ok", False):
        if sync_result.get("conflict"):
            bookmark = sync_result.get("conflict_bookmark", "?")
            print(
                f"[forge] WARNING: initial sync conflict, bookmark: {bookmark}",
                file=sys.stderr,
            )
        elif sync_result.get("error"):
            print(
                f"[forge] WARNING: initial sync error: {sync_result['error']}",
                file=sys.stderr,
            )
```

Design decisions:
- `ensure` failures with status `error` are fatal (raise `ProcessLaunchError`)
- `migration_needed` is a warning, not fatal (operator can resolve later)
- Sync conflicts on initial sync are warnings (system is still usable)
- Token is sent only in the PUT body, never stored in process env
- Timeout for sync is 120s (same as agent operation timeout)

### 2.2 Wire bootstrap into `forge dev`

File: `src/forge_cli/commands.py`

In the `dev` command, after starting the agent and before starting kiln:

```python
overlay = manager.start_overlay(cfg)
agent = manager.start_agent(cfg)

# Bootstrap sync after agent is healthy, before kiln starts building
try:
    manager.bootstrap_sync(cfg)
except ProcessLaunchError as exc:
    typer.echo(f"sync bootstrap failed: {exc}", err=True)
    # Non-fatal: continue without sync
except httpx.HTTPError as exc:
    typer.echo(f"sync bootstrap error: {exc}", err=True)

kiln = manager.start_kiln(cfg)
```

Bootstrap errors are logged but do not prevent startup. The system works
without sync (local-only mode).

### 2.3 Wire bootstrap into Docker entrypoint

File: `docker/entrypoint.py`

Add sync config to the generated `forge.yaml`:

```python
sync_section = ""
sync_remote_url = os.environ.get("FORGE_SYNC_REMOTE_URL", "")
if sync_remote_url:
    sync_after_commit = os.environ.get("FORGE_SYNC_AFTER_COMMIT", "true")
    sync_remote = os.environ.get("FORGE_SYNC_REMOTE", "origin")
    sync_section = f"""
sync:
  after_commit: {sync_after_commit}
  remote: {sync_remote}
  remote_url: {sync_remote_url}
"""

# Token is passed via env var only, not written to yaml on disk
```

The token is read from `FORGE_SYNC_REMOTE_TOKEN` env var by pydantic-settings
at config load time. It is never written to the generated yaml file.

### 2.4 Add tests

File: `tests/test_commands.py`

- Test bootstrap is called in `forge dev` after agent start, before kiln
- Test bootstrap skips when `sync_remote_url` is None
- Test bootstrap logs warning on migration_needed
- Test bootstrap logs warning on sync conflict
- Test bootstrap continues on httpx errors

File: `tests/test_bootstrap.py` (new)

- Test ensure → configure remote → sync happy path (mock httpx)
- Test ensure returns error → raises ProcessLaunchError
- Test ensure returns migration_needed → logs warning, skips remote config
- Test token is sent in PUT body, not in process env
- Test sync conflict result → logs bookmark warning

### 2.5 Commit

```
feat: add sync bootstrap sequence to forge dev startup

After agent health gate, forge calls /api/vault/vcs/sync/ensure,
configures the remote via PUT, and runs an initial sync. Errors are
warnings (system remains usable in local-only mode). Token is sent
only via API body, never in process environment.
```

---

## Phase 3: Remove Sidecar (breaking, requires phase 2 verified)

### 3.1 Remove vault-sync service from docker-compose

File: `docker/docker-compose.yml`

- Delete the `vault-sync` service block entirely
- Remove `vault-sync: service_started` from forge's `depends_on`
- Keep `tailscale: service_started`

### 3.2 Delete sidecar code

Delete:
- `docker/vault_git_sync.py`
- `docker/vault-sync.Dockerfile`

### 3.3 Update .env.example

File: `docker/.env.example`

Remove sidecar-specific vars:

```diff
-GIT_REPO_URL=https://github.com/your-org/your-vault-repo.git
-GIT_BRANCH=main
-GITHUB_TOKEN=
-GIT_AUTO_PUSH=true
-GIT_SYNC_INTERVAL_SEC=30
-GIT_COMMIT_AUTHOR=forge-bot
-GIT_COMMIT_EMAIL=forge-bot@users.noreply.github.com
```

Add agent-native sync vars:

```ini
# Vault sync (via obsidian-agent jj git bridge)
FORGE_SYNC_REMOTE_URL=https://github.com/your-org/your-vault.git
FORGE_SYNC_REMOTE_TOKEN=                     # GitHub PAT for private repos
FORGE_SYNC_AFTER_COMMIT=true                 # Auto-sync after each agent edit
FORGE_SYNC_REMOTE=origin                     # Remote name (default: origin)
```

### 3.4 Update Docker README

File: `docker/README.md`

Rewrite to document:
- Agent-native sync architecture (no sidecar)
- Env var reference (FORGE_SYNC_* vars)
- Startup sequence (agent → bootstrap → kiln)
- Conflict handling (bookmarks pushed to remote, logged as warnings)
- Migration from git-only vaults (automatic colocate on safe states)
- Manual resolution for dirty git-only vaults

### 3.5 Commit

```
feat!: remove vault-sync sidecar, use agent-native jj sync

BREAKING: The vault-sync container and GIT_* env vars are removed.
Sync is now handled by obsidian-agent via jj git bridge. Configure
with FORGE_SYNC_REMOTE_URL and FORGE_SYNC_REMOTE_TOKEN.
```

---

## Phase 4: Forge Documentation and Demo Updates

### 4.1 Update ARCHITECTURE.md

File: `docs/ARCHITECTURE.md`

Add sync architecture section:

- Describe the sync data flow: forge bootstrap → agent ensure → remote config → sync
- Document the sync lifecycle: fetch → rebase → conflict check → push
- Document the post-commit auto-sync trigger
- Document conflict bookmark workflow
- Update the system diagram to remove sidecar

### 4.2 Update DEV_GUIDE.md

File: `docs/DEV_GUIDE.md`

- Document sync config fields and env vars
- Document bootstrap_sync implementation
- Document how to test sync locally (requires jj + git repo)
- Add troubleshooting for sync errors

### 4.3 Update SETUP_GUIDE.md

File: `docs/SETUP_GUIDE.md`

Add "Step: Configure Remote Sync" section:

- How to enable GitHub sync with a PAT
- How to set up a private repo
- What happens on first sync (migration, colocate)
- How to handle conflicts (check bookmarks, resolve, re-sync)
- How to disable sync (just don't set FORGE_SYNC_REMOTE_URL)

### 4.4 Update demo

The demo does not use real sync (no remote). No demo changes needed unless
we want to add a sync step that exercises the readiness/status endpoints
against a local bare repo. This is optional and low priority.

### 4.5 Commit

```
docs: update architecture, dev guide, and setup guide for agent-native sync
```

---

## Phase 5: Hardening and Integration Tests

### 5.1 Integration test for sync bootstrap

File: `tests/test_sync_integration.py` (new, gated by marker)

Test against a real jj+git repo (requires jj binary):
- Create a temp bare git repo
- Initialize vault with `jj git init --colocate`
- Start agent pointed at vault
- Call bootstrap_sync with remote_url pointing to bare repo
- Verify sync state file exists and shows success
- Verify content is pushed to bare repo

Gate with `@pytest.mark.integration` and env var `FORGE_RUN_SYNC_TESTS=1`.

### 5.2 Test migration-needed path

- Create a temp vault with git-only (dirty working tree)
- Verify bootstrap logs warning and continues
- Verify system is usable without sync

### 5.3 Test conflict path

- Create divergent history between vault and remote
- Run sync
- Verify conflict bookmark is created and pushed
- Verify warning is logged with bookmark name

### 5.4 Commit

```
test: add integration tests for sync bootstrap and conflict handling
```

---

## File Change Summary

| File | Phase | Change |
|------|-------|--------|
| `src/forge_cli/config.py` | 1 | Add sync_* fields, YAML block, render |
| `src/forge_cli/processes.py` | 1+2 | Add sync env pass-through, bootstrap_sync() |
| `src/forge_cli/commands.py` | 2 | Wire bootstrap into dev command |
| `forge.yaml.example` | 1 | Add sync section |
| `tests/test_config.py` | 1 | Test sync config loading |
| `tests/test_commands.py` | 1+2 | Test env pass-through, bootstrap wiring |
| `tests/test_bootstrap.py` | 2 | New: bootstrap unit tests |
| `docker/entrypoint.py` | 2+3 | Add sync config generation |
| `docker/docker-compose.yml` | 3 | Remove vault-sync service |
| `docker/vault_git_sync.py` | 3 | Delete |
| `docker/vault-sync.Dockerfile` | 3 | Delete |
| `docker/.env.example` | 3 | Replace GIT_* with FORGE_SYNC_* |
| `docker/README.md` | 3+4 | Rewrite for agent-native sync |
| `docs/ARCHITECTURE.md` | 4 | Add sync architecture section |
| `docs/DEV_GUIDE.md` | 4 | Add sync dev documentation |
| `docs/SETUP_GUIDE.md` | 4 | Add remote sync setup section |
| `tests/test_sync_integration.py` | 5 | New: integration tests |

---

## Config Field Reference (Final State)

| Config Key | Env Var | Default | Description |
|------------|---------|---------|-------------|
| `sync.after_commit` | `FORGE_SYNC_AFTER_COMMIT` | `false` | Auto-sync after each agent commit |
| `sync.remote` | `FORGE_SYNC_REMOTE` | `"origin"` | Git remote name |
| `sync.remote_url` | `FORGE_SYNC_REMOTE_URL` | `None` | Remote URL (enables sync bootstrap) |
| `sync.remote_token` | `FORGE_SYNC_REMOTE_TOKEN` | `None` | GitHub PAT / access token |

When `sync_remote_url` is None, the entire sync bootstrap is skipped and the
system operates in local-only mode. This is the default.

When `sync_after_commit` is true, the agent automatically runs a full sync
cycle after each successful `/api/agent/apply` commit. Sync failures become
warnings in the operation result, not errors.

---

## Startup Sequence (Final State)

```
forge dev
  │
  ├─ 1. start_overlay(cfg)           # HTTP edge server
  │     └─ health gate: GET / → 200/301/302/404
  │
  ├─ 2. start_agent(cfg)             # LLM agent + vault ops
  │     ├─ env: AGENT_SYNC_AFTER_COMMIT, AGENT_SYNC_REMOTE
  │     └─ health gate: GET /api/health → 200
  │
  ├─ 3. bootstrap_sync(cfg)          # VCS initialization (if remote configured)
  │     ├─ POST /api/vault/vcs/sync/ensure
  │     │   ├─ ready → continue
  │     │   ├─ migration_needed → warn, skip remote config
  │     │   └─ error → warn, skip
  │     ├─ PUT /api/vault/vcs/sync/remote  (url + token)
  │     └─ POST /api/vault/vcs/sync        (initial fetch/rebase/push)
  │         ├─ sync_ok=true → continue
  │         └─ conflict → warn (bookmark pushed)
  │
  ├─ 4. start_kiln(cfg)              # Static site generator
  │     └─ watch mode: --no-serve --on-rebuild
  │
  └─ 5. wait for processes / Ctrl+C
        └─ stop_all() in reverse order
```

---

## Docker Topology (Final State)

```yaml
services:
  tailscale:          # Network namespace
  forge:              # Overlay + agent + kiln (single container)
    depends_on:
      tailscale: service_started
    environment:
      FORGE_SYNC_REMOTE_URL: ${FORGE_SYNC_REMOTE_URL:-}
      FORGE_SYNC_REMOTE_TOKEN: ${FORGE_SYNC_REMOTE_TOKEN:-}
      FORGE_SYNC_AFTER_COMMIT: ${FORGE_SYNC_AFTER_COMMIT:-true}
      FORGE_SYNC_REMOTE: ${FORGE_SYNC_REMOTE:-origin}
      # ... existing FORGE_* and AGENT_* vars ...
```

Two services instead of three. One shared vault volume instead of two
containers contending on the same mount.

---

## Risk Mitigation

### Risk: Existing deployments using sidecar env vars

Mitigation: Phase 3 is a breaking change. Document migration path clearly:
- `GIT_REPO_URL` → `FORGE_SYNC_REMOTE_URL`
- `GITHUB_TOKEN` → `FORGE_SYNC_REMOTE_TOKEN`
- `GIT_AUTO_PUSH=true` → `FORGE_SYNC_AFTER_COMMIT=true`
- `GIT_SYNC_INTERVAL_SEC` → removed (event-driven, not polling)
- `GIT_COMMIT_AUTHOR/EMAIL` → removed (jj uses its own identity)

### Risk: Dirty git-only vaults can't auto-colocate

Mitigation: `ensure_sync_ready()` detects this case and returns
`migration_needed` with detail `"git-only with uncommitted changes"`. Forge
logs a clear warning. Operator must commit or stash manually, then restart.

### Risk: Token exposure

Mitigation: Token is sent only via HTTPS PUT body to localhost agent API.
It is not written to forge.yaml on disk, not passed as a process env var to
the agent, and not logged by the agent's request logger (which skips bodies).
obsidian-ops stores it in `.forge/git-credential.sh` with mode 0700.

### Risk: Sync conflicts block the system

Mitigation: Conflicts are modeled as warnings, not errors. The system remains
fully usable in local mode when a conflict exists. A conflict bookmark is
pushed to the remote so the operator can inspect and resolve at their
convenience.

### Risk: Non-agent writes (kiln, manual edits) don't trigger sync

Mitigation: `sync_after_commit` only fires on agent commits. For manual vault
edits, the operator can call `POST /api/vault/vcs/sync` manually or via a
cron-style trigger. This is a known limitation and matches the current design
intent (agent is the primary writer). If periodic background sync is needed
in the future, it can be added as a lightweight timer in the agent or forge
process without a separate sidecar.
