# Forge Developer Guide

Technical reference for working on the forge orchestrator and its dependency
components. Read [ARCHITECTURE.md](ARCHITECTURE.md) first for the system
overview.

---

## Repository Layout

```
forge/                          # This repo -- orchestrator CLI
  src/forge_cli/
    __init__.py
    __main__.py                 # Entry: forge CLI via Typer
    config.py                   # ForgeConfig (pydantic-settings + YAML)
    processes.py                # ProcessManager, wait_for_http, ManagedProcess
    commands.py                 # dev, generate, serve, init commands
    demo_entrypoints.py         # forge-demo-* script wrappers
  tests/
    conftest.py                 # sys.path setup for src layout
    test_config.py              # Config loading: defaults, YAML, env overrides
    test_commands.py            # Command dispatch, process ordering, init
    test_demo_harness.py        # Opt-in integration test (FORGE_RUN_DEMO_VALIDATION=1)
  demo/                         # Interactive demo harness (see below)
  docs/                         # This documentation
  pyproject.toml                # Package metadata, entry points, tool config
  forge.yaml.example            # Example config file
```

Sibling repos (same parent directory):

```
kiln-fork/                      # Go static site generator
forge-overlay/                  # Python HTTP edge server
obsidian-ops/                   # Python vault operations library
obsidian-agent/                 # Python LLM agent service
```

---

## Forge CLI Implementation

### Config System (`config.py`)

`ForgeConfig` extends `pydantic_settings.BaseSettings` with `env_prefix="FORGE_"`.

Loading priority (highest wins):
1. Environment variables (`FORGE_PORT=9090`)
2. YAML file values (`forge.yaml`)
3. Built-in defaults

The `ForgeConfig.load(path)` method:
1. Reads YAML file via `_load_yaml_config()` (handles flat keys + nested `agent`/`kiln` blocks)
2. Creates a default `ForgeConfig()` to detect which env vars were set (via `model_fields_set`)
3. Merges: YAML values as base, env overrides on top
4. Returns fully-resolved config

Nested YAML blocks are flattened:

```yaml
agent:
  host: 0.0.0.0       # -> agent_host
  port: 9191           # -> agent_port
  vault_dir: ./notes   # -> agent_vault_dir
  llm_model: openai:x  # -> agent_llm_model

kiln:
  bin: /usr/bin/kiln   # -> kiln_bin
  theme: nord          # -> kiln_theme
```

Derived properties (`agent_url`, `overlay_url`, `on_rebuild_url`) are computed
from host/port fields.

`effective_agent_vault_dir` returns `agent_vault_dir` if set, otherwise falls
back to `vault_dir` (agent shares the same vault by default).

Sync config fields:

- `sync_after_commit` (`FORGE_SYNC_AFTER_COMMIT`, default `false`)
- `sync_remote` (`FORGE_SYNC_REMOTE`, default `origin`)
- `sync_remote_url` (`FORGE_SYNC_REMOTE_URL`, default unset)
- `sync_remote_token` (`FORGE_SYNC_REMOTE_TOKEN`, default unset)

`sync_remote_url` enables bootstrap sync at startup. If it is unset, Forge runs
in local-only mode.

### Process Manager (`processes.py`)

`ProcessManager` wraps `subprocess.Popen` with:
- Named process tracking (`ManagedProcess` dataclass)
- Log streaming on daemon threads (prefixed `[name] ...` to stdout)
- Ordered shutdown (`stop_all` terminates in reverse start order)
- Context manager support (`with ProcessManager() as pm:`)

Three high-level starters:

**`start_overlay(config)`** -- launches `forge-overlay` with CLI flags derived
from config. Health-gates by polling the overlay URL, accepting
200/301/302/404 (any response means it's up).

**`start_agent(config)`** -- launches `obsidian-agent` with environment
variables:

| Env Var | Source |
|---------|--------|
| `AGENT_VAULT_DIR` | `config.effective_agent_vault_dir` |
| `AGENT_LLM_MODEL` | `config.agent_llm_model` |
| `AGENT_HOST` | `config.agent_host` |
| `AGENT_PORT` | `config.agent_port` |
| `AGENT_SITE_BASE_URL` | `config.overlay_url` |
| `AGENT_SYNC_AFTER_COMMIT` | `str(config.sync_after_commit).lower()` |
| `AGENT_SYNC_REMOTE` | `config.sync_remote` |

Health-gates by polling `/api/health` for 200.

**`bootstrap_sync(config)`** -- if `sync_remote_url` is configured, performs:

1. `POST /api/vault/vcs/sync/ensure`
2. `PUT /api/vault/vcs/sync/remote` with URL and optional token
3. `POST /api/vault/vcs/sync` for initial fetch/rebase/push

`status=error` from ensure raises `ProcessLaunchError`. `migration_needed` and
sync conflict/error responses are logged as warnings.

**`start_kiln(config)`** -- launches kiln with `dev --no-serve --on-rebuild`
and all theme/font/lang/name flags. No health gate (kiln starts building
immediately).

The `wait_for_http()` helper uses httpx with streaming GET, 1-second per-request
timeout, 0.2-second polling interval, 60-second default deadline. It raises
`TimeoutError` on failure.

### Commands (`commands.py`)

All commands use Typer with a `--config` option (default: `forge.yaml`).

**`forge dev`**: Starts overlay, agent, bootstrap-sync, kiln in order. Prints startup status.
Blocks on `_wait_for_processes()` (polls all child processes, exits if any
die). Catches `KeyboardInterrupt` for clean shutdown. `finally` block calls
`manager.stop_all()`.

**`forge generate`**: Runs `kiln generate` as a checked subprocess with all
config flags. No long-running processes.

**`forge serve`**: Starts overlay only. Same blocking/shutdown pattern as `dev`
but without agent or kiln.

**`forge init`**: Creates vault/output/overlay directories. Writes a default
`forge.yaml` via `_render_default_config()` (uses `yaml.safe_dump`). Refuses
to overwrite without `--force`.

### Entry Points (`pyproject.toml`)

```ini
[project.scripts]
forge = "forge_cli.__main__:main"
forge-demo-setup = "forge_cli.demo_entrypoints:demo_setup"
forge-demo-start = "forge_cli.demo_entrypoints:demo_start"
forge-demo-validate = "forge_cli.demo_entrypoints:demo_validate"
forge-demo-run = "forge_cli.demo_entrypoints:demo_run"
forge-demo-cleanup = "forge_cli.demo_entrypoints:demo_cleanup"
forge-demo-start-free-explore = "forge_cli.demo_entrypoints:demo_start_free_explore"
forge-demo-run-free-explore = "forge_cli.demo_entrypoints:demo_run_free_explore"
```

Demo entrypoints are thin wrappers that shell out to `demo/scripts/*.py`.

---

## Dependency Library Internals

### kiln-fork Internals

The two forge-specific additions live in `internal/cli/`:

**`dev.go`** -- the `--no-serve` flag skips the HTTP server goroutine. The
`--on-rebuild` flag stores a URL in the `onRebuildURL` package variable.

The `OnRebuild` callback in the watcher:
1. Updates file modification timestamps
2. Computes changeset via dependency graph
3. Runs `IncrementalBuild` on affected files
4. Refreshes dependency graph
5. Calls `postRebuildWebhook(onRebuildURL, log)` if URL is set

`postRebuildWebhook` uses a package-level `http.Client` with 5-second timeout.
POSTs `{"type":"rebuilt"}` as `application/json`. Errors are logged but never
propagated -- the rebuild loop continues regardless.

Flag registration is in `commands.go` lines 87-88:
```go
var noServe bool
var onRebuildURL string
```

### forge-overlay Internals

**`app.py`** -- `create_app(config)` creates:
- An `EventBroker` instance (in-process pub/sub)
- A shared `httpx.AsyncClient` (closed on shutdown via lifespan)
- Five route handlers as closures over the broker and client
- Wraps the Starlette app with `InjectMiddleware`

**`inject.py`** -- ASGI middleware that buffers the full response body, searches
for `</head>` (case-insensitive), injects the snippet, and recalculates
`Content-Length`. Non-HTML responses pass through unmodified. The snippet is
hardcoded:

```python
SNIPPET = '<link rel="stylesheet" href="/ops/ops.css">\n<script type="module" src="/ops/ops.js"></script>\n'
```

**`events.py`** -- `EventBroker` uses one `asyncio.Queue` per subscriber.
`publish()` does non-blocking `put_nowait()` to all queues. `subscribe()` is
an async generator that creates a queue, adds it to the subscriber set, yields
items, and removes the queue in a `finally` block.

**`proxy.py`** -- `proxy_request()` constructs the upstream URL as
`{upstream}/api/{path}?{query}`. Filters hop-by-hop headers in both
directions. Streams the response body via `aiter_bytes()`. Catches all
`httpx.HTTPError` and returns 502.

**`static_handler.py`** -- `resolve_file()` tries three candidates per URL
path: exact file, `.html` suffix, `/index.html`. All candidates are validated
against the site root via `Path.relative_to()`. `build_404()` serves a custom
`404.html` if present, otherwise plain text.

### obsidian-agent Internals

**`agent.py`** -- The core orchestration class. Holds a PydanticAI `Agent`
instance with `defer_model_check=True`. The `run()` method:
1. Acquires a boolean busy lock
2. Builds `VaultDeps` (vault, interface config, scope constraints)
3. Calls `agent.run(instruction, deps=deps, usage_limits=limits)` with
   `asyncio.wait_for` for timeout
4. On success: commits via `vault.commit(message)`
5. Returns `RunResult` with changed files list
6. Releases busy lock in `finally`

Tool access is controlled by `VaultDeps.allowed_tool_names` (set per
interface profile) and `allowed_write_paths` (set per scope). Write tools
check both before executing.

**`models.py`** -- `ApplyRequest` validates:
- `current_file`: no URLs, forward-slashes only, no `..` traversal
- `scope.path` must match `current_file` if both provided
- Extra fields are forbidden (`model_config = ConfigDict(extra="forbid")`)

**`scope.py`** -- `EditScope` is a Pydantic discriminated union on `"kind"`.
All scope types normalize their `path` field. `MultiScope.scopes` validates
that all children target the same path.

**`routes/agent_routes.py`** -- Maps `ApplyRequest` to `agent.run()`, handles
`BusyError` as 409. Legacy `/api/apply` and `/api/undo` aliases are registered
with deprecation logging.

**`routes/vault_routes.py`** -- Direct CRUD routes. `PUT /api/vault/files`
supports optimistic concurrency via `expected_sha256` -- if the file has
changed since read, returns 409 with `"code": "stale_write"` and both SHA
values.

**`rate_limit.py`** -- `RouteRateLimiter` uses a sliding window deque per
`(client_ip, route_key)`. Configured from `AGENT_DETERMINISTIC_RATE_LIMIT`
and `AGENT_DETERMINISTIC_RATE_WINDOW_SECONDS`. Returns 429 when exceeded.

**`web_paths.py`** -- Bidirectional URL-to-vault-path conversion.
`vault_path_to_url` strips `.md`, handles `flat_urls` mode (trailing slash vs
not). `url_to_vault_path` reverses the mapping, appending `.md`.

### obsidian-ops Internals

**`vault.py`** -- The `Vault` class is the primary API. Constructor takes
`root` (must exist), `jj_bin`, `jj_timeout`. All mutations acquire
`MutationLock` (non-blocking; raises `BusyError` on contention).

**`sandbox.py`** -- `validate_path(root, user_path)` rejects empty paths,
absolute paths, `..` traversal, and symlink escapes. Uses
`Path.relative_to()` for containment checks. Existing paths are resolved via
`realpath()`.

**`frontmatter.py`** -- `parse_frontmatter()` splits on `---` delimiters,
uses a custom YAML loader that keeps timestamps as strings (avoids
`datetime` auto-parsing). `merge_frontmatter()` does recursive dict merging
for nested mappings.

**`content.py`** -- `find_heading()` parses `#` lines to determine heading
level and scans for the next same-or-higher-level heading to bound the
section. `find_block()` matches `^block-id` with word-boundary regex, then
walks backward to find the paragraph or list-item start.

**`vcs.py`** -- `JJ` class wraps `subprocess.run` calls with `cwd`, timeout,
and error handling. `describe(msg)` + `new()` creates a commit. `undo()` +
`restore_from_previous()` implements rollback. All failures raise `VCSError`.

**`lock.py`** -- `MutationLock` wraps `threading.Lock.acquire(blocking=False)`.
Supports context manager. `is_held` property for status checks.

**`templates.py`** -- Templates are YAML files in `.forge/templates/`.
Expressions: `{{ field }}`, `{{ slug(field) }}`, `{{ today }}`, `{{ now }}`.
`render_template()` validates required fields, renders path and body, and
checks path safety.

---

## Testing

### Running Tests

```bash
# Unit tests (fast, no external deps)
devenv shell -- uv run pytest -q

# With coverage
devenv shell -- uv run pytest --cov=forge_cli --cov-report=term-missing

# Integration test (boots real processes on localhost)
FORGE_RUN_DEMO_VALIDATION=1 devenv shell -- uv run pytest -m integration

# Type checking
devenv shell -- uv run mypy

# Linting
devenv shell -- uv run ruff check src tests
devenv shell -- uv run ruff format --check src tests
```

### Test Structure

**`test_config.py`** (3 tests):
- Default values when config file is missing
- Nested YAML block parsing (agent/kiln sections)
- Environment variable overrides take precedence over file values

**`test_commands.py`** (6 tests):
- Process manager starts overlay, agent, kiln in order with correct args
- `wait_for_http` raises `TimeoutError` on persistent failure
- `forge dev` dispatches all three processes in order
- `forge serve` starts only overlay
- `forge generate` invokes `kiln generate` with all flags
- `forge init` scaffolds directories, writes config, refuses overwrite

**`test_demo_harness.py`** (1 integration test):
- Gated by `FORGE_RUN_DEMO_VALIDATION=1`
- Runs `demo/scripts/validate_full_stack.py` end-to-end
- Asserts 6 behaviors: process flags, injection, proxy, webhook, apply, undo

Tests use `_DummyProcess` stubs and `monkeypatch` to avoid real subprocess
spawning in unit tests. The `fake_popen` pattern captures launched commands
and environment variables for assertion.

### Running Dependency Tests

```bash
# kiln-fork
cd /path/to/kiln-fork && devenv shell -- go test ./...

# forge-overlay
cd /path/to/forge-overlay && devenv shell -- uv run pytest -q

# obsidian-ops
cd /path/to/obsidian-ops && devenv shell -- uv run pytest -q

# obsidian-agent
cd /path/to/obsidian-agent && devenv shell -- uv run pytest -q
```

---

## Demo Harness

The `demo/` directory provides a self-contained demonstration without requiring
a real LLM. See `demo/README.md` for full usage.

### Architecture

The demo replaces `obsidian-agent` with a lightweight Python HTTP server
(`demo/tools/dummy_api_server.py`) that provides deterministic apply/undo
behavior. A second backend (`demo/tools/vllm_api_server.py`) routes through
a real vLLM endpoint for the free-explore variant.

The demo overlay (`demo/overlay/ops.js` + `ops.css`) provides an interactive
panel injected into every page: SSE event counter, apply/undo/health buttons,
and a JSON output pane. This is distinct from forge-overlay's minimal example
overlay, which only auto-reloads on rebuild events.

### Key Scripts

| Script | Purpose |
|--------|---------|
| `setup.sh` | Copy vault-template and overlay to `runtime/` |
| `start_stack.sh` | Boot dummy API, overlay, kiln with health gates |
| `validate_full_stack.sh` | Automated 6-assertion integration test |
| `run_demo.py` | Interactive 7-step walkthrough with keypress progression |
| `run_free_explore.py` | vLLM-backed variant launcher |
| `cleanup.sh` | Stop processes, remove runtime |
| `common.sh` | Shared variables, port checks, wait helpers |

### Demo Ports

| Component | Port |
|-----------|------|
| Dummy/vLLM API | 18081 |
| forge-overlay | 18080 |
| kiln (no-serve) | none |

### Demo Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEMO_OVERLAY_PORT` | `18080` | Overlay bind port |
| `DEMO_API_PORT` | `18081` | Backend API bind port |
| `DEMO_VLLM_BASE_URL` | `http://remora-server:8000/v1` | vLLM upstream |
| `DEMO_VLLM_MODEL` | (auto-detect) | vLLM model override |
| `KILN_BIN` | kiln-fork binary if found | Kiln executable path |
| `FORGE_OVERLAY_PROJECT_DIR` | `../forge-overlay` | Overlay project for `uv run` |
| `FORGE_RUN_DEMO_VALIDATION` | `0` | Enable integration test in pytest |

---

## Build and Package

```bash
# Install in development mode
devenv shell -- uv pip install -e ".[dev]"

# Build wheel
devenv shell -- uv build

# The package ships src/forge_cli as the wheel payload
# Entry point: forge = forge_cli.__main__:main
```

### Package Configuration

- **Build backend:** hatchling
- **Python:** >= 3.13
- **Dependencies:** pydantic, pydantic-settings, typer, httpx, pyyaml
- **Dev dependencies:** pytest, pytest-cov, mypy, ruff
- **Mypy:** strict mode enabled
- **Ruff:** line-length 120, double quotes, LF line endings

---

## Adding a New Forge Command

1. Add the command function in `commands.py` with `@app.command()` decorator
2. Accept `--config` as a `Path` option (default `Path("forge.yaml")`)
3. Load config with `ForgeConfig.load(config)`
4. Use `ProcessManager` for any long-running processes
5. Follow the try/except/finally pattern from `dev` for clean shutdown
6. Add tests in `test_commands.py` using the `_FakeManager` monkeypatch pattern

---

## Adding a New Config Field

1. Add the field to `ForgeConfig` in `config.py` with type annotation and default
2. If it belongs to a nested block (agent/kiln), add the YAML key mapping in
   `_load_yaml_config()`
3. Add the `FORGE_` prefixed env var (automatic via pydantic-settings)
4. Add the field to `_render_default_config()` if it should appear in `forge init` output
5. Add a test in `test_config.py` covering the YAML and env-override paths
