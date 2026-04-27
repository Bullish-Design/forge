# Forge Post-Refactor Code Review

Date: 2026-04-26
Scope: Full repository review after sync integration refactoring (Phase 1+2 of REFACTORED_DEPENDENCIES_REFACTORING.md)

---

## Executive Summary

The sync refactoring is cleanly implemented. Config, process manager, bootstrap, and tests
all follow the phased plan correctly. The core CLI is well-structured and test coverage is
solid for the orchestrator's size.

Two **critical bugs** in the demo harness explain the reported failures:

1. **Orphaned child processes on cleanup** — `cleanup_runtime()` sends SIGTERM only to the
   forge parent PID. Because Python's default SIGTERM handler terminates the process
   without running `finally` blocks, the overlay/agent/kiln children become orphans that
   hold ports indefinitely. This causes "port already in use" on subsequent runs.

2. **No SIGTERM propagation in forge dev** — The `dev` command's `finally: manager.stop_all()`
   only runs on normal exceptions and KeyboardInterrupt. SIGTERM bypasses it entirely.
   Combined with `start_new_session=True` in the demo, this guarantees leaked children.

These two bugs are the root cause of both reported issues: the stale listener problem
and the unreliable rebuild detection (which fails because a previous run's orphaned
kiln/overlay is still occupying ports or state, causing the new run to malfunction).

---

## 1. Critical Issues

### 1.1 Demo: Orphaned child processes on SIGTERM (stale listeners)

**Files:** `demo/scripts/lib.py`, `src/forge_cli/commands.py`

**Root cause chain:**

1. `lib.start_stack()` launches forge with `start_new_session=True` (line 216), putting
   forge in its own process group.
2. `forge dev` starts overlay, agent, and kiln as child processes via `ProcessManager.start()`.
   These children inherit the process group.
3. `lib.stop_pid()` sends `os.kill(pid, signal.SIGTERM)` to the forge PID only (line 128).
4. Python's default SIGTERM handler terminates the process immediately — **the `finally:
   manager.stop_all()` block in `commands.dev()` never executes**.
5. Overlay (port 18080), agent (port 18081), and kiln continue running as orphans.
6. `shutil.rmtree(RUNTIME_DIR)` deletes the PID file, so the next cleanup can't find them.
7. Next run's `ensure_port_free()` either fails (if it detects the stale listener) or
   the new stack competes with the orphaned processes.

**Fix (two-part, defense in depth):**

**Part A — Add SIGTERM handler to `forge dev`:**

`src/forge_cli/commands.py`, in the `dev()` function:
```python
import signal

def dev(config: Path = ...) -> None:
    cfg = ForgeConfig.load(config)
    manager = ProcessManager()

    def _handle_sigterm(signum, frame):
        raise SystemExit(0)

    previous_handler = signal.signal(signal.SIGTERM, _handle_sigterm)
    try:
        # ... existing startup code ...
    except SystemExit:
        typer.echo("shutting down forge dev (SIGTERM)")
    except KeyboardInterrupt:
        typer.echo("shutting down forge dev")
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        manager.stop_all()
```

This ensures `stop_all()` runs when forge receives SIGTERM, cleaning up children.

**Part B — Kill process group in demo cleanup:**

`demo/scripts/lib.py`, modify `stop_pid()`:
```python
def stop_pid(pid: int) -> None:
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
    except OSError:
        return

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not process_alive(pid):
            return
        time.sleep(0.2)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except OSError:
        return
```

Since `start_new_session=True` makes forge the process group leader, `os.killpg()` kills
forge AND all its children (overlay, agent, kiln) in one shot.

**Part C — Add port-based cleanup as last resort:**

`demo/scripts/lib.py`, add to `cleanup_runtime()`:
```python
def _kill_port_holders(*ports: int) -> None:
    """Best-effort kill of any process listening on demo ports."""
    for port in ports:
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, check=False,
            )
            for pid_str in result.stdout.strip().splitlines():
                try:
                    os.kill(int(pid_str), signal.SIGKILL)
                except (OSError, ValueError):
                    pass
        except FileNotFoundError:
            pass  # lsof not available

def cleanup_runtime() -> int:
    pids = parse_pid_file()
    forge_pid = pids.get("FORGE_PID")
    if forge_pid is not None:
        log("stopping forge process group")
        stop_pid(forge_pid)

    # Belt-and-suspenders: kill anything still on demo ports
    _kill_port_holders(DEMO_OVERLAY_PORT, DEMO_API_PORT)

    log("removing runtime")
    shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
    log("cleanup complete")
    return 0
```

### 1.2 Demo: Kiln rebuild not observed in rendered page

**File:** `demo/scripts/validate_full_stack.py`

This failure is most likely a **secondary effect of Issue 1.1**: orphaned processes from a
previous failed run cause the new stack to malfunction. The scenarios are:

- **Scenario A:** Orphaned kiln from previous run is still watching the old (deleted)
  vault directory. The new kiln starts and watches the new vault directory, but an
  orphaned overlay on port 18080 intercepts HTTP requests and serves stale content.
  The validate script's HTTP checks pass (stale overlay responds) but the rebuild check
  fails (stale overlay never receives the webhook from the new kiln).

- **Scenario B:** Port check catches the orphan and fails with "port already in use",
  but the user re-runs without manual cleanup, or the error message is unclear.

- **Scenario C (independent of stale processes):** stdout buffering. When forge is
  launched with `stdout=handle` (file redirect), Python uses block buffering. The
  `_stream_prefixed_logs()` daemon threads write to `sys.stdout` without explicit
  `flush()`. Log entries from kiln may not appear in `forge.log` until the buffer fills.
  The validate script's secondary check (`"POST /internal/rebuild" not in forge_log`)
  could fail due to buffered but unwritten log lines.

**Fix for Scenario C — flush after each log line:**

`src/forge_cli/processes.py`:
```python
def _stream_prefixed_logs(name: str, stream: TextIO) -> None:
    for line in stream:
        sys.stdout.write(f"[{name}] {line}")
        sys.stdout.flush()
```

The primary fix is Issue 1.1. With proper cleanup, the stale process scenarios are
eliminated. The flush fix addresses the independent buffering edge case.

---

## 2. High Priority Issues

### 2.1 Documentation version drift

**File:** `docs/ARCHITECTURE.md`

The dependency version table is stale after the sync refactoring upgraded upstream pins:

| Component | Documented | Actual (pyproject.toml) |
|-----------|-----------|------------------------|
| obsidian-agent | 0.2.0 (line 248) | v0.3.1 |
| obsidian-ops | 0.5.0 (line 383) | v0.7.1 |

The docs were written before the sync refactoring bumped these dependencies. They should
be updated to reflect the current pins and document the new sync API surface.

**Fix:** Update version numbers in ARCHITECTURE.md. Add a "Sync Lifecycle" section
documenting the bootstrap flow, sync endpoints, and conflict bookmark workflow.

### 2.2 `_stream_prefixed_logs` missing flush

**File:** `src/forge_cli/processes.py:262-264`

```python
def _stream_prefixed_logs(name: str, stream: TextIO) -> None:
    for line in stream:
        sys.stdout.write(f"[{name}] {line}")
```

When forge's stdout is redirected to a file (as in the demo and Docker), Python switches
to block buffering. Without `sys.stdout.flush()`, log lines accumulate in the buffer and
may never reach the file if the process is killed. This makes log-based debugging unreliable
and causes the demo's log pattern checks to be flaky.

**Fix:** Add `sys.stdout.flush()` after the write.

### 2.3 Duplicate entry point: `demo_script` and `demo_run`

**File:** `src/forge_cli/demo_entrypoints.py:41-46`

```python
def demo_run() -> int:
    return _run("run_demo.py")

def demo_script() -> int:
    return _run("run_demo.py")
```

These are identical. `pyproject.toml` registers both as separate entry points:
- `forge-demo-run = "forge_cli.demo_entrypoints:demo_run"`
- `forge-demo-script = "forge_cli.demo_entrypoints:demo_script"`

**Fix:** Remove `demo_script()` and the `forge-demo-script` entry point, or make
`demo_script` a documented alias if there's a reason for both.

### 2.4 `init()` ignores env vars for directory creation

**File:** `src/forge_cli/commands.py:100-116`

```python
def init(...) -> None:
    cfg = ForgeConfig()  # ← bare constructor, no .load()
    cfg.vault_dir.mkdir(parents=True, exist_ok=True)
    ...
```

`ForgeConfig()` constructs with defaults, not with env var overrides. If a user sets
`FORGE_VAULT_DIR=./data`, `init` still creates `./vault`. The rendered config file uses
the default path, not the env var.

However: the test `test_init_scaffolds_directories_and_config` sets env vars and they DO
appear in the output because pydantic-settings reads env vars in the bare constructor too.
So this actually works — the `FORGE_` env vars are read by the bare `ForgeConfig()` call.
The test confirms this at line 327: `parsed["vault_dir"] == str(vault_dir)`.

**Status:** Not a bug. The code is correct but confusing — the bare constructor picks up
env vars via pydantic-settings. A comment would help clarify intent.

---

## 3. Medium Priority Issues

### 3.1 `bootstrap_sync` raise_for_status can propagate uncaught

**File:** `src/forge_cli/processes.py:190-191, 217-218, 224-225`

```python
ensure_resp = httpx.post(...)
ensure_resp.raise_for_status()  # ← can raise httpx.HTTPStatusError
```

The `dev` command catches `httpx.HTTPError` from bootstrap, so this IS caught. However,
the bootstrap method has three separate `raise_for_status()` calls (ensure, remote, sync).
If the remote or sync call gets an HTTP 4xx/5xx, the error propagates as an
`httpx.HTTPStatusError` (subclass of `httpx.HTTPError`) and is caught correctly.

**Status:** Not a bug. The exception flow is correct. But the error message in `dev()` is
generic ("sync bootstrap error: {exc}"). Consider catching each call separately in
`bootstrap_sync` to provide more specific error context.

### 3.2 Demo config missing sync section

**File:** `demo/scripts/lib.py:144-170`

`write_demo_config()` generates the demo's `forge.demo.yaml` but omits the `sync` section.
This is correct behavior (demo doesn't use remote sync), but it means `bootstrap_sync()`
is silently skipped. The validate script then exercises sync endpoints directly by calling
the agent/dummy API, which works.

However, the validate script calls sync endpoints via HTTP to the **overlay proxy**, not
directly to the agent. This tests the full proxy path, which is good. But if the overlay
doesn't proxy `/api/vault/vcs/sync/*`, the validate will fail.

**Status:** Correct design. No change needed.

### 3.3 `wait_for_http` accepts 404 for overlay

**File:** `src/forge_cli/processes.py:128-131`

```python
wait_for_http(
    f"{config.overlay_url}/",
    expected_statuses={200, 301, 302, 404},
)
```

Accepting 404 means "the overlay is responding but has no content yet" — this is valid
because kiln hasn't built the HTML yet when the overlay starts. The overlay is healthy
even without content. This is intentional and correct.

### 3.4 Test coverage gaps

**Missing test coverage (not blocking, but worth adding):**

- `test_bootstrap.py`: No test for `sync_remote_token=None` (token omitted from PUT body)
- `test_bootstrap.py`: No test for HTTP connection errors (httpx.ConnectError)
- `test_commands.py`: No test for `--force` flag on `init` (only negative case tested)
- `test_config.py`: No test for malformed YAML (non-mapping root, parse errors)
- `test_config.py`: No test for `effective_agent_vault_dir` fallback to `vault_dir`
- No test for `_stream_prefixed_logs` behavior
- No test for `stop_all` timeout → kill escalation

### 3.5 `_wait_for_processes` exits on ANY process exit

**File:** `src/forge_cli/commands.py:126-132`

```python
def _wait_for_processes(processes: list[ManagedProcess]) -> None:
    while True:
        for managed in processes:
            return_code = managed.process.poll()
            if return_code is not None:
                raise typer.Exit(code=return_code)
        time.sleep(0.2)
```

If ANY child exits (even with code 0), forge exits immediately. This is aggressive —
if kiln exits with 0 after a build, forge shuts down. In practice this works because
kiln in `dev --no-serve` mode runs indefinitely, but the behavior is surprising.

**Status:** Acceptable for current design. Document the assumption that all children
run indefinitely in dev mode.

---

## 4. Low Priority / Informational

### 4.1 Config field naming

`agent_vault_dir` vs `effective_agent_vault_dir` is confusing. The first is the raw
config field (can be None), the second is the computed fallback. This pattern is
correct but benefits from a docstring.

### 4.2 Hardcoded kiln path in demo lib

**File:** `demo/scripts/lib.py:37-40`

```python
if Path("/home/andrew/Documents/Projects/kiln-fork/kiln").exists():
    DEFAULT_KILN_BIN = "/home/andrew/Documents/Projects/kiln-fork/kiln"
```

Hardcoded absolute path to a developer's local build. Works for the developer but
fails silently for others (falls back to `kiln` on PATH). This is fine for a
development demo but should be noted.

### 4.3 `demo_entrypoints.py` repo root assumption

`_repo_root()` uses `Path(__file__).resolve().parents[2]` which assumes the file lives
at `src/forge_cli/demo_entrypoints.py`. If the package is installed as a wheel (not
editable), this path won't point to the demo scripts. The demo entry points only work
in editable installs or direct repo checkouts.

**Status:** Acceptable — demos are development-time tools, not production entry points.

### 4.4 Docker: vault_git_sync.py correctly removed

Confirmed: `docker/vault_git_sync.py` and `docker/vault-sync.Dockerfile` are not present.
The docker-compose.yml has only two services (tailscale, forge). The sidecar removal from
Phase 3 of the refactoring plan is complete.

### 4.5 Docker entrypoint sync section

**File:** `docker/entrypoint.py`

The entrypoint correctly generates the optional `sync:` section only when
`FORGE_SYNC_REMOTE_URL` is set. Token is read from env at runtime by pydantic-settings,
never written to the YAML file on disk. This follows the security design from the
refactoring plan.

---

## 5. Sync Refactoring Assessment

### What was implemented correctly

- **Config fields** (`config.py`): `sync_after_commit`, `sync_remote`, `sync_remote_url`,
  `sync_remote_token` all present with correct defaults and YAML/env support.
- **Agent env pass-through** (`processes.py`): `AGENT_SYNC_AFTER_COMMIT` and
  `AGENT_SYNC_REMOTE` passed to agent. Token NOT passed in env (correct — sent via API).
- **Bootstrap sequence** (`processes.py`): ensure → remote config → initial sync. Error
  handling matches the plan: error status = fatal, migration_needed = warning + skip,
  sync conflict = warning + continue.
- **Dev command wiring** (`commands.py`): Bootstrap called after agent, before kiln.
  Both ProcessLaunchError and httpx.HTTPError caught and logged as warnings.
- **Init config rendering** (`commands.py`): `sync` block included in generated YAML.
- **Tests** (`test_bootstrap.py`): Happy path, error, migration, conflict, and skip-when-
  no-url all covered.
- **Docker** (`docker-compose.yml`, `entrypoint.py`, `.env.example`): Sync env vars wired
  through compose, entrypoint generates conditional sync config, env template documents
  all sync vars.
- **Dummy API** (`dummy_api_server.py`): All sync endpoints implemented (ensure, remote,
  sync, status) with correct response shapes.

### What's missing from the plan

- **Phase 3 partial:** Sidecar removal is complete (files deleted, compose updated), but
  `docker/README.md` could be more detailed about the migration path from old GIT_* vars.
- **Phase 4 partial:** ARCHITECTURE.md needs version updates and sync lifecycle section.
  DEV_GUIDE.md and SETUP_GUIDE.md were pre-updated (they already reference sync), but
  ARCHITECTURE.md still shows old dependency versions.
- **Phase 5 not started:** `test_sync_integration.py` exists but is gated by
  `FORGE_RUN_SYNC_TESTS=1`. This is correct for CI, but no instructions exist for
  running it locally.

---

## 6. Test Suite Summary

| File | Tests | Coverage Focus | Quality |
|------|-------|---------------|---------|
| `test_config.py` | 3 | Defaults, YAML blocks, env overrides | Good |
| `test_commands.py` | 9 | Process ordering, bootstrap wiring, all 4 commands | Good |
| `test_bootstrap.py` | 5 | Bootstrap state machine (happy/error/migration/conflict/skip) | Good |
| `test_sync_integration.py` | 1 | Full-stack sync with real jj/git (gated) | Good |
| `test_demo_harness.py` | 1 | End-to-end demo validation (gated) | Adequate |

Overall test quality is good for an orchestrator of this size. The mocking approach is
clean (monkeypatch + fake classes), assertions are specific, and edge cases are covered.

---

## 7. Recommended Fix Priority

### Must fix (blocking demo reliability)

1. **Add SIGTERM handler to `dev` command** — ensures `stop_all()` runs on termination.
2. **Kill process group in demo `stop_pid()`** — ensures all children die with parent.
3. **Add port-based cleanup fallback** — catches orphans even when PID file is lost.
4. **Add `sys.stdout.flush()` to `_stream_prefixed_logs`** — makes log checks reliable.

### Should fix (correctness/quality)

5. Update ARCHITECTURE.md dependency versions (agent 0.3.1, ops 0.7.1).
6. Remove duplicate `demo_script` entry point.

### Nice to have

7. Add missing test cases (token=None bootstrap, malformed YAML, --force init).
8. Add sync lifecycle section to ARCHITECTURE.md.
9. Document `_wait_for_processes` assumption that children run indefinitely.

---

## 8. Concrete Change Checklist

- [ ] `src/forge_cli/commands.py`: Add `signal.SIGTERM` handler in `dev()` that raises `SystemExit`
- [ ] `src/forge_cli/processes.py`: Add `sys.stdout.flush()` in `_stream_prefixed_logs()`
- [ ] `demo/scripts/lib.py`: Change `stop_pid()` to use `os.killpg()` instead of `os.kill()`
- [ ] `demo/scripts/lib.py`: Add `_kill_port_holders()` fallback in `cleanup_runtime()`
- [ ] `docs/ARCHITECTURE.md`: Update obsidian-agent version 0.2.0 → 0.3.1
- [ ] `docs/ARCHITECTURE.md`: Update obsidian-ops version 0.5.0 → 0.7.1
- [ ] `src/forge_cli/demo_entrypoints.py`: Remove `demo_script()` duplicate
- [ ] `pyproject.toml`: Remove `forge-demo-script` entry point
