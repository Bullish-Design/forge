# Forge v2 Architecture

Forge is a local-first system for publishing an Obsidian vault as a live,
AI-augmented static site. It coordinates four independent components through a
thin Python orchestrator.

---

## System Overview

```
 Browser
   |
   v
 forge-overlay (:8080)          <-- public HTTP entrypoint
   |  serves HTML from kiln output with injected overlay assets
   |  proxies /api/* to obsidian-agent
   |  broadcasts SSE rebuild events to connected browsers
   |
   +--- /internal/rebuild <--- kiln-fork webhook (POST {"type":"rebuilt"})
   |
   +--- /api/* proxy -------> obsidian-agent (:8081)
                                  |  LLM-powered vault editing
                                  |  uses obsidian-ops for all file I/O
                                  v
                               obsidian-ops
                                  |  sandboxed vault CRUD
                                  |  frontmatter, headings, blocks
                                  |  jujutsu VCS integration
                                  v
                               vault/ (markdown files on disk)
                                  ^
                                  |
                               kiln-fork (filesystem watcher)
                                  |  detects changes, incremental rebuild
                                  |  writes HTML to output/
                                  |  POSTs webhook on completion
```

### Data Flow: Edit Cycle

1. User (or agent) writes a vault file
2. kiln-fork detects the change via fsnotify
3. kiln-fork performs incremental rebuild of affected pages
4. kiln-fork POSTs `{"type":"rebuilt"}` to forge-overlay's `/internal/rebuild`
5. forge-overlay broadcasts event to all SSE subscribers at `/ops/events`
6. Browser receives SSE event and reloads the page
7. forge-overlay serves the updated HTML with injected overlay assets

### Data Flow: Agent Apply

1. Browser POSTs to `/api/agent/apply` on forge-overlay
2. forge-overlay proxies to obsidian-agent
3. obsidian-agent runs PydanticAI agent loop with vault tools
4. Agent tools call obsidian-ops to read/write vault files
5. obsidian-ops writes files, commits via jujutsu
6. kiln-fork detects changes and triggers rebuild cycle (above)

### Process Startup Order

The orchestrator starts components in dependency order:

1. **forge-overlay** -- must be listening before kiln fires its first webhook
2. **obsidian-agent** -- must be healthy before accepting proxied requests
3. **kiln-fork** -- starts building immediately and fires webhooks on completion

Shutdown is reverse order: kiln, agent, overlay.

### Data Flow: Startup Sync Bootstrap

When `sync.remote_url` (or `FORGE_SYNC_REMOTE_URL`) is configured, Forge runs
sync bootstrap after agent health and before kiln startup:

1. `POST /api/vault/vcs/sync/ensure`
2. `PUT /api/vault/vcs/sync/remote` (URL + optional token)
3. `POST /api/vault/vcs/sync` (fetch/rebase/push)

Conflicts are warnings, not fatal startup errors. Migration-needed states are
also warnings so the system can continue in local mode.

---

## Component Details

---

## 1. kiln-fork

**Language:** Go
**Role:** Obsidian vault to static HTML generator with filesystem watching
**Repository:** `kiln-fork` (fork of `otaleghani/kiln`)
**Version:** v0.10.3

kiln-fork converts markdown files into a complete static site with support for
wikilinks, backlinks, tags, table of contents, local graph, canvas rendering,
math (KaTeX), code highlighting, and Obsidian callouts.

### CLI Commands

#### `kiln generate`

One-shot static site build.

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--input` | `-i` | `./vault` | Source markdown directory |
| `--output` | `-o` | `./public` | Output HTML directory |
| `--theme` | `-t` | `default` | Color scheme (default, dracula, catppuccin, nord) |
| `--font` | `-f` | `inter` | Font family (inter, merriweather, lato, system) |
| `--name` | `-n` | `My Notes` | Site name for browser tab and meta tags |
| `--url` | `-u` | (empty) | Base URL for sitemap/canonical links |
| `--lang` | `-g` | `en` | HTML lang attribute |
| `--layout` | `-L` | `default` | Page layout |
| `--mode` | `-m` | `default` | Build mode |
| `--flat-urls` | | `false` | `note.html` instead of `note/index.html` |
| `--disable-toc` | | `false` | Hide table of contents sidebar |
| `--disable-local-graph` | | `false` | Hide local graph sidebar |
| `--disable-backlinks` | | `false` | Hide backlinks panel |
| `--accent-color` | `-a` | (empty) | Theme accent (red, orange, yellow, green, blue, purple, cyan) |
| `--log` | `-l` | `info` | Log verbosity (debug, info) |

#### `kiln dev`

Watch mode: builds, watches for changes, optionally serves and/or fires webhooks.
Accepts all `generate` flags plus:

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--port` | `-p` | `8080` | HTTP server port (ignored when `--no-serve`) |
| `--no-serve` | | `false` | Skip built-in HTTP server (watch/rebuild only) |
| `--on-rebuild` | | (empty) | URL to POST after each successful rebuild |

When `--on-rebuild` is set, kiln POSTs after every incremental rebuild:

```
POST <url>
Content-Type: application/json

{"type":"rebuilt"}
```

The webhook uses a 5-second timeout. Failures are logged but do not interrupt
the rebuild loop.

#### `kiln serve`

Serve a previously-generated site.

| Flag | Short | Default |
|------|-------|---------|
| `--port` | `-p` | `8080` |
| `--output` | `-o` | `./public` |

#### Other Commands

| Command | Description |
|---------|-------------|
| `kiln init` | Scaffold vault directory and `kiln.yaml` config |
| `kiln clean` | Remove output directory |
| `kiln doctor` | Check for broken wikilinks |
| `kiln stats` | Display vault statistics |

### Configuration File

All commands load defaults from `kiln.yaml` in the current directory.
CLI flags override file values. File values override built-in defaults.

---

## 2. forge-overlay

**Language:** Python (Starlette + uvicorn)
**Role:** Browser-facing HTTP edge server
**Version:** 0.2.1
**Entry point:** `forge-overlay`

forge-overlay is a generic HTTP server that:
- Serves kiln's HTML output with clean URLs
- Injects overlay assets (`ops.css`, `ops.js`) into every HTML page
- Provides an SSE endpoint for real-time rebuild notifications
- Reverse-proxies `/api/*` requests to an upstream backend

### CLI Flags

| Flag | Env Var | Default | Description |
|------|---------|---------|-------------|
| `--site-dir` | `FORGE_SITE_DIR` | `public` | Directory of generated HTML (kiln output) |
| `--overlay-dir` | `FORGE_OVERLAY_DIR` | `overlay` | Directory of overlay assets to inject |
| `--api-upstream` | `FORGE_API_UPSTREAM` | `http://127.0.0.1:3000` | Upstream URL for `/api/*` proxy |
| `--host` | `FORGE_HOST` | `127.0.0.1` | Bind address |
| `--port` | `FORGE_PORT` | `8080` | Bind port |

### HTTP Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/{path}` | GET | Serve site HTML/assets with clean URLs and injection |
| `/ops/{path}` | GET | Serve overlay assets (ops.js, ops.css) |
| `/ops/events` | GET | SSE stream of rebuild events |
| `/internal/rebuild` | POST | Webhook receiver, broadcasts to SSE subscribers |
| `/api/{path}` | ALL | Reverse proxy to `--api-upstream` |

### HTML Injection

Every HTML response has the following injected before `</head>`:

```html
<link rel="stylesheet" href="/ops/ops.css">
<script type="module" src="/ops/ops.js"></script>
```

Non-HTML responses (CSS, JS, images) pass through unmodified.

### Clean URL Resolution

For a request to `/about`, the handler tries in order:
1. `{site-dir}/about` (exact file)
2. `{site-dir}/about.html` (.html extension)
3. `{site-dir}/about/index.html` (directory index)

Trailing slashes redirect: `/about/` -> 301 -> `/about`.

### Reverse Proxy

- Forwards request method, body, and headers (minus hop-by-hop headers)
- Streams response body for memory efficiency
- Returns 502 `{"error":"upstream_unavailable"}` on connection failure
- Does not follow redirects (3xx returned to client)

### SSE Event Broker

- `POST /internal/rebuild` publishes `{"type":"rebuilt"}` to all subscribers
- `GET /ops/events` yields events as `data: {"type":"rebuilt"}\n\n`
- Subscribers are cleaned up on disconnect
- The broker is an in-process asyncio.Queue per subscriber

### Security

- Path traversal prevention on both site and overlay directories
- Resolved paths validated to stay within configured root via `Path.relative_to()`

---

## 3. obsidian-agent

**Language:** Python (FastAPI + PydanticAI)
**Role:** LLM-powered vault editing service
**Version:** 0.3.1
**Entry point:** `obsidian-agent`

obsidian-agent exposes an HTTP API for AI-assisted vault editing. It runs a
PydanticAI agent loop that calls obsidian-ops vault tools to read and write
files, then commits the changes via jujutsu.

### Environment Variables

All prefixed with `AGENT_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_VAULT_DIR` | (required) | Path to vault root |
| `AGENT_LLM_MODEL` | `anthropic:claude-sonnet-4-20250514` | `provider:model` identifier |
| `AGENT_LLM_BASE_URL` | (none) | Custom LLM endpoint URL |
| `AGENT_LLM_MAX_TOKENS` | `4096` | Max tokens per LLM call |
| `AGENT_MAX_ITERATIONS` | `20` | Max agent tool-use iterations |
| `AGENT_OPERATION_TIMEOUT` | `120` | Seconds before operation timeout |
| `AGENT_JJ_BIN` | `jj` | Path to jujutsu binary |
| `AGENT_JJ_TIMEOUT` | `120` | Seconds for VCS operations |
| `AGENT_SITE_BASE_URL` | `http://127.0.0.1:8080` | Base URL for URL-to-path conversion |
| `AGENT_FLAT_URLS` | `false` | Match kiln's `--flat-urls` setting |
| `AGENT_HOST` | `127.0.0.1` | Bind address |
| `AGENT_PORT` | `8081` | Bind port |
| `AGENT_DETERMINISTIC_RATE_LIMIT` | `120` | Max events per window (0 = disabled) |
| `AGENT_DETERMINISTIC_RATE_WINDOW_SECONDS` | `60` | Rate limit window |

### HTTP API

#### Agent Routes

**POST `/api/agent/apply`** -- Apply an LLM instruction to the vault

Request body (`ApplyRequest`):

```json
{
  "instruction": "Add a summary section",
  "current_file": "projects/forge-v2.md",
  "interface_id": "command",
  "scope": { "kind": "file", "path": "projects/forge-v2.md" },
  "intent": "rewrite",
  "allowed_write_scope": "target_only"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `instruction` | string | yes | What the agent should do |
| `current_file` | string | no | Vault-relative path (context for agent) |
| `interface_id` | string | no | `"command"` (all tools) or `"forge_web"` (scoped) |
| `scope` | EditScope | no | Constrains where the agent can write |
| `intent` | string | no | `rewrite`, `summarize`, `insert_below`, `annotate`, `extract_tasks` |
| `allowed_write_scope` | string | no | `target_only`, `target_plus_frontmatter`, `unrestricted` |

Response body (`OperationResult`):

```json
{
  "ok": true,
  "updated": true,
  "summary": "Added summary section with 3 key points",
  "changed_files": ["projects/forge-v2.md"],
  "error": null,
  "warning": null
}
```

Status codes: 200 (success), 400 (bad request), 409 (busy).

**POST `/api/agent/undo`** -- Undo the last agent operation

Empty request body. Returns `OperationResult`. Status: 200, 409.

**Legacy aliases** (deprecated): `POST /api/apply`, `POST /api/undo`.

#### Vault Routes

Direct vault CRUD without LLM involvement:

| Route | Method | Description |
|-------|--------|-------------|
| `/api/vault/files` | GET | Read file (by `?path=` or `?url=`) |
| `/api/vault/files` | PUT | Write file (with optional SHA256 optimistic lock) |
| `/api/vault/undo` | POST | Undo last vault change |
| `/api/vault/files/structure` | GET | Get headings and block IDs |
| `/api/vault/files/anchors` | POST | Ensure block anchor exists for line range |
| `/api/vault/pages/templates` | GET | List available page templates |
| `/api/vault/pages` | POST | Create page from template |
| `/api/health` | GET | Health check |

#### Edit Scopes

The `scope` field in `ApplyRequest` is a discriminated union on `"kind"`:

| Kind | Fields | Constrains agent to |
|------|--------|---------------------|
| `file` | `path` | Entire file |
| `heading` | `path`, `heading` | Content under a heading |
| `block` | `path`, `block_id` | Content of a block reference |
| `selection` | `path`, `text`, `line_start`, `line_end` | Selected text range |
| `multi` | `path`, `scopes[]` | Multiple heading/block/selection targets |

#### Interface Profiles

| Profile | Tools Available | Use Case |
|---------|----------------|----------|
| `command` | All 14 vault tools | CLI / unrestricted |
| `forge_web` | Scoped by edit scope | Browser UI / constrained |

The `forge_web` profile always allows read tools. Write tools are gated by the
scope kind (e.g., `block` scope only allows `write_block`).

### Agent Tool Inventory

Read tools: `read_file`, `list_files`, `search_files`, `get_frontmatter`,
`read_heading`, `read_block`.

Write tools: `write_file`, `delete_file`, `set_frontmatter`,
`update_frontmatter`, `delete_frontmatter_field`, `write_heading`,
`write_block`, `create_from_template`.

### Concurrency

- A global busy lock prevents concurrent agent operations (returns 409)
- obsidian-ops has its own mutation lock (non-blocking, raises BusyError)
- Rate limiting on vault write routes (sliding window per client IP)

---

## 4. obsidian-ops

**Language:** Python
**Role:** Sandboxed vault operations library
**Version:** 0.7.1

obsidian-ops provides the `Vault` class for all file I/O against an Obsidian
vault. It enforces path sandboxing, provides structured markdown operations,
and integrates with jujutsu for version control.

### Vault Class API

```python
from obsidian_ops import Vault

vault = Vault("/path/to/vault", jj_bin="jj", jj_timeout=120)
```

#### File Operations

| Method | Returns | Mutation | Description |
|--------|---------|----------|-------------|
| `read_file(path)` | `str` | no | Read file contents (max 512 KB) |
| `write_file(path, content)` | `None` | yes | Write file, create parents |
| `delete_file(path)` | `None` | yes | Delete a file |
| `list_files(pattern, max_results)` | `list[str]` | no | Glob match, default `*.md` |
| `search_files(query, glob, max_results)` | `list[SearchResult]` | no | Case-insensitive text search |

#### Frontmatter Operations

| Method | Returns | Mutation | Description |
|--------|---------|----------|-------------|
| `get_frontmatter(path)` | `dict \| None` | no | Read YAML frontmatter |
| `set_frontmatter(path, data)` | `None` | yes | Replace entire frontmatter |
| `update_frontmatter(path, updates)` | `None` | yes | Deep-merge into frontmatter |
| `delete_frontmatter_field(path, field)` | `None` | yes | Remove a frontmatter field |

#### Content Patch Operations

| Method | Returns | Mutation | Description |
|--------|---------|----------|-------------|
| `read_heading(path, heading)` | `str \| None` | no | Read content under a heading |
| `write_heading(path, heading, content)` | `None` | yes | Replace/create heading section |
| `read_block(path, block_id)` | `str \| None` | no | Read block by `^block-id` |
| `write_block(path, block_id, content)` | `None` | yes | Replace block content |
| `ensure_block_id(path, line_start, line_end)` | `EnsureBlockResult` | yes | Add block anchor to line range |

#### Structure Analysis

| Method | Returns | Description |
|--------|---------|-------------|
| `list_structure(path)` | `StructureView` | Extract headings, blocks, SHA256 |

#### VCS Operations (Jujutsu)

| Method | Returns | Mutation | Description |
|--------|---------|----------|-------------|
| `commit(message)` | `None` | yes | Describe + create new commit |
| `undo()` | `None` | yes | Undo last jj operation |
| `undo_last_change()` | `UndoResult` | yes | Undo + restore previous state |
| `vcs_status()` | `str` | no | Current jj status |
| `is_busy()` | `bool` | no | Check if mutation lock is held |

#### Templates

| Method | Returns | Mutation | Description |
|--------|---------|----------|-------------|
| `list_templates()` | `list[TemplateDefinition]` | no | List `.forge/templates/*.yaml` |
| `create_from_template(id, fields)` | `CreatePageResult` | yes | Create page from template |

### Path Sandboxing

All path arguments are vault-relative strings (e.g., `"projects/forge-v2.md"`).
The sandbox validates:

- No empty paths
- No absolute paths or drive letters
- No `..` traversal
- Symlinks cannot escape vault root
- All resolved paths must be within vault root

Violations raise `PathError`.

### Mutation Lock

All write operations acquire a non-blocking mutex. If the lock is already held,
`BusyError` is raised immediately. This prevents concurrent writes from
corrupting vault state.

### Error Hierarchy

```
VaultError (base)
  PathError           -- path validation failure
  FileTooLargeError   -- file exceeds 512 KB read limit
  BusyError           -- mutation lock held
  FrontmatterError    -- YAML parse or structure error
  ContentPatchError   -- heading/block patch failure
  VCSError            -- jujutsu command failure
```

### Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `MAX_READ_SIZE` | 512 KB | Maximum file read size |
| `MAX_LIST_RESULTS` | 200 | Default glob result limit |
| `MAX_SEARCH_RESULTS` | 50 | Default search result limit |
| `SNIPPET_CONTEXT` | 80 chars | Search snippet context window |

---

## 5. Forge Orchestrator (this repo)

**Language:** Python (Typer + Pydantic)
**Role:** Process orchestration CLI
**Version:** 0.2.0
**Entry point:** `forge`

The forge CLI coordinates startup, health-gating, and shutdown of the three
runtime components.

### Commands

| Command | Description |
|---------|-------------|
| `forge dev` | Start overlay + agent + kiln in coordinated dev mode |
| `forge generate` | Run a one-off kiln static site build |
| `forge serve` | Start overlay-only preview (no kiln watcher) |
| `forge init` | Scaffold directories and write `forge.yaml` |

### Configuration

Config is loaded from `forge.yaml` with `FORGE_*` environment variable
overrides. Env vars take precedence over file values.

```yaml
vault_dir: ./vault
output_dir: ./public
overlay_dir: ./static
host: 127.0.0.1
port: 8080

agent:
  host: 127.0.0.1
  port: 8081
  vault_dir: ./vault        # defaults to top-level vault_dir
  llm_model: anthropic:claude-sonnet-4-20250514

kiln:
  bin: kiln
  theme: default
  font: inter
  lang: en
  site_name: My Notes
```

### Derived URLs

| Property | Default Value |
|----------|---------------|
| `overlay_url` | `http://127.0.0.1:8080` |
| `agent_url` | `http://127.0.0.1:8081` |
| `on_rebuild_url` | `http://127.0.0.1:8080/internal/rebuild` |

### Health Gating

- **Overlay:** polls root URL, accepts 200/301/302/404
- **Agent:** polls `/api/health`, expects 200
- **Kiln:** no health check (starts building immediately)

Default timeout: 60 seconds per component.

---

## Port Assignments

| Component | Default Port | Configurable Via |
|-----------|-------------|------------------|
| forge-overlay | 8080 | `FORGE_PORT` / `forge.yaml port` |
| obsidian-agent | 8081 | `FORGE_AGENT_PORT` / `forge.yaml agent.port` |
| kiln-fork (dev server) | 8080 | `--port` (not used in forge; `--no-serve`) |

---

## Technology Stack

| Component | Runtime | Framework | Key Libraries |
|-----------|---------|-----------|---------------|
| kiln-fork | Go | Cobra CLI | fsnotify, goldmark, charmbracelet/log |
| forge-overlay | Python 3.13+ | Starlette | sse-starlette, httpx, uvicorn, typer |
| obsidian-agent | Python 3.13+ | FastAPI | pydantic-ai, pydantic, httpx, uvicorn |
| obsidian-ops | Python 3.12+ | (library) | pyyaml, optional FastAPI server |
| forge | Python 3.13+ | Typer | pydantic-settings, httpx, pyyaml |
