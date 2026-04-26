# Obsidian Agent: Concept Guide

## Status

- Status: Proposed
- Target: Standalone Python library for LLM-powered Obsidian vault operations
- Relationship: Extracts and replaces the `internal/ops/` package from Forge
- Audience: Implementers of the agent backend and maintainers of Forge integration

---

## 1. One-Sentence Summary

Obsidian Agent is a Python library that accepts a natural-language instruction and a page context, runs a tool-using LLM agent loop against an Obsidian vault, commits changes with Jujutsu, triggers a site rebuild, and returns a structured result — replacing what Forge currently does in Go inside `internal/ops/`.

---

## 2. Why a Separate Library

### 2.1 Current state

Forge is a Go static site generator (forked from Kiln) that has grown an `internal/ops/` package containing:

- An LLM agent loop (`agent.go`) with Anthropic and OpenAI-compatible backends
- Vault tool implementations (`tools.go`) with path sandboxing
- An HTTP handler (`handler.go`) with `/api/apply`, `/api/undo`, `/api/health`
- Jujutsu VCS wrapper (`jj.go`)
- Mutation lock (`lock.go`)
- URL-to-file path resolution (`resolve.go`)

This works, but it couples agent orchestration tightly to the Go binary. Go is not the natural language for LLM agent development — the Python ecosystem has better libraries for prompt engineering, tool-use patterns, structured output parsing, embedding, and model provider integration.

### 2.2 Extraction rationale

- **Better ecosystem fit**: Python has first-class SDKs for Anthropic, OpenAI, and every major model provider. Agent frameworks (Claude Agent SDK, LangChain, etc.) are Python-native.
- **Faster iteration**: Agent prompts, tool definitions, and orchestration logic change frequently. Python's development loop is faster for this kind of work.
- **Cleaner separation**: Forge should remain a thin host — serving rendered pages, injecting overlays, and proxying API calls. It should not own agent logic.
- **Path to the full architecture**: The eventual multi-interface architecture (FORGE_INTERFACE_ARCHITECTURE.md) envisions a local backend service with SSE streaming, session management, and a pluggable interface registry. That service is better built in Python than bolted onto a Go static site generator.

### 2.3 Relationship to the architecture docs

| Concern | MVP Spec | Full Spec | Obsidian Agent Role |
|---|---|---|---|
| Agent/tool loop | Backend runs one agent loop | Same, with SSE events | Owns entirely |
| Tool definitions | read, write, list, search, fetch, history | Same + extensible | Owns entirely |
| Vault mutation | Atomic writes, jj commit | Same | Owns entirely |
| Site rebuild | kiln generate after mutation | Same | Calls rebuild hook |
| Mutation lock | Global in-process lock | Same | Owns entirely |
| HTTP API | POST /api/run, POST /api/undo | POST /api/interfaces/:id/submit, SSE streams | Provides or exposes |
| URL-to-file resolution | Backend resolves path from URL | Same | Owns entirely |
| Page context | Browser sends current_url_path | Same + selection, session | Consumes from caller |
| Overlay UI | Forge injects ops.js/ops.css | Same, richer shell | Not in scope |

---

## 3. Library Scope

### 3.1 What Obsidian Agent owns

1. **Agent loop** — Accept an instruction, run an LLM with tools, iterate until done or limit reached.
2. **Tool implementations** — Read, write, list, search files in an Obsidian vault with path sandboxing.
3. **Vault conventions** — Preserve YAML frontmatter, wikilinks, Obsidian folder structure.
4. **System prompt** — Context-aware instructions for the LLM about vault operations.
5. **Version control** — Jujutsu commit after successful mutation, undo support.
6. **Mutation lock** — One operation at a time.
7. **Path resolution** — Map URL paths to vault-relative markdown file paths.
8. **Result model** — Structured response with summary, changed files, created files, history hint.

### 3.2 What Obsidian Agent does NOT own

- **HTTP server** — The library exposes functions/classes, not a running server. A thin server wrapper can be provided as an optional extra or example, but the core is a library.
- **Overlay UI** — No JavaScript, no CSS, no frontend code.
- **Site rendering** — No HTML generation. Rebuild is triggered via a callback/hook.
- **Static site serving** — Forge continues to serve rendered pages.

### 3.3 Optional extras (can ship later)

- A standalone HTTP server (FastAPI or similar) that wraps the library for use independent of Forge.
- SSE streaming adapter for the agent loop.
- A `fetch_url` tool for creating source notes from web content.
- A `get_file_history` tool wrapping jj log.

---

## 4. Core API Design

### 4.1 Primary entry point

```python
from obsidian_agent import Agent, AgentConfig, VaultConfig, RunRequest, RunResult

config = AgentConfig(
    vault=VaultConfig(root="/path/to/vault"),
    api_key="...",           # or from environment
    model="claude-sonnet-4-20250514",
    max_iterations=20,
)

agent = Agent(config)

result: RunResult = agent.run(RunRequest(
    instruction="Clean up this note and add related links",
    current_url_path="/projects/alpha/meeting-notes/",
))
```

### 4.2 RunRequest

```python
@dataclass
class RunRequest:
    instruction: str
    current_url_path: str
    current_file_path: str | None = None  # optional override
```

Matches the MVP spec's request model (section 7.2).

### 4.3 RunResult

```python
@dataclass
class RunResult:
    summary: str
    changed_files: list[str]
    created_files: list[str]
    history_hint: str | None = None
    error: str | None = None
```

Matches the MVP spec's response model (section 7.3).

### 4.4 Undo

```python
undo_result: UndoResult = agent.undo()
```

### 4.5 Rebuild hook

The library does not know how to rebuild the site. The caller provides a callback:

```python
config = AgentConfig(
    ...,
    on_rebuild=lambda: subprocess.run(["kiln", "generate"]),
)
```

Or for Forge integration, Forge calls rebuild itself after the agent returns.

---

## 5. Tool Set

### 5.1 MVP tools (match current Go implementation)

| Tool | Description | Current Go equivalent |
|---|---|---|
| `read_file(path)` | Read a vault-relative file (max 512KB) | `VaultTools.ReadFile` |
| `write_file(path, content)` | Write/create a file, create parent dirs | `VaultTools.WriteFile` |
| `list_files(glob)` | List files matching a glob pattern (max 200) | `VaultTools.ListFiles` |
| `search_files(query, glob)` | Search file contents with snippets (max 50) | `VaultTools.SearchFiles` |

### 5.2 Path sandboxing (port from Go)

All tool operations must enforce:

- No absolute paths
- No `..` traversal
- Symlink resolution stays within vault root
- Vault root is the only writable directory

### 5.3 Future tools

- `fetch_url(url)` — Fetch web content for source notes
- `get_file_history(path, limit)` — Query jj log for a file

---

## 6. Agent Loop

### 6.1 Design

The agent loop follows a standard tool-use pattern:

1. Build system prompt with vault context and current file info
2. Send user instruction + system prompt to LLM
3. If LLM returns tool calls, execute them and send results back
4. Repeat until LLM returns a final text response or iteration limit hit
5. Parse the final response into a RunResult

### 6.2 LLM backend support

Support at minimum:

- **Anthropic API** — Primary, using the official `anthropic` Python SDK
- **OpenAI-compatible** — For local models (vLLM, Ollama, etc.) via the `openai` SDK or `httpx`

This matches the current Go implementation's dual-backend support.

### 6.3 System prompt

Port the existing system prompt from `agent.go:buildSystemPrompt()`:

- You are an assistant that helps manage an Obsidian vault
- Preserve YAML frontmatter unless asked to change it
- Preserve wikilinks unless asked to change them
- Prefer minimal edits
- Do not delete content unless clearly intended
- Summarize changes at the end
- Current file context when available

---

## 7. Version Control

### 7.1 Jujutsu integration

Port the `JJ` wrapper from `jj.go`:

```python
class JJ:
    def __init__(self, repo_path: str, timeout: int = 30):
        ...

    def commit(self, message: str) -> None:
        """jj commit -m <message>, then jj new"""

    def undo(self) -> None:
        """jj undo"""

    def status(self) -> str:
        """jj status"""
```

### 7.2 Commit flow

After the agent loop completes with file changes:

1. `jj commit -m "ops: <instruction summary>"`
2. Trigger rebuild callback
3. Return result

This matches the MVP spec's section 8.3 behavior.

---

## 8. Concurrency

### 8.1 Mutation lock

A single in-process lock prevents concurrent vault mutations:

```python
class MutationLock:
    def try_acquire(self) -> bool: ...
    def release(self) -> None: ...
```

Returns a busy error if the lock is held, matching the current Go `MutationLock` and the MVP spec's section 4.5.

### 8.2 No queue

The MVP spec explicitly says no job queue, no worker pool, no background scheduler. One blocking request at a time.

---

## 9. Path Resolution

### 9.1 URL to file mapping

Port the `PathIndex` from `resolve.go`:

```python
class PathIndex:
    def resolve(self, url_path: str) -> str | None:
        """Map a URL path like /projects/alpha/ to projects/alpha.md"""

    def rebuild(self, vault_root: str, output_dir: str) -> None:
        """Scan vault and rebuild the index"""
```

This allows the agent to know which source file corresponds to the page the user is viewing.

---

## 10. Project Structure

```
obsidian-agent/
  pyproject.toml
  src/
    obsidian_agent/
      __init__.py          # Public API exports
      agent.py             # Agent loop, LLM interaction
      config.py            # AgentConfig, VaultConfig
      tools.py             # VaultTools implementations
      tool_defs.py         # Tool schemas for LLM
      prompt.py            # System prompt builder
      jj.py                # Jujutsu wrapper
      lock.py              # MutationLock
      resolve.py           # PathIndex (URL to file mapping)
      models.py            # RunRequest, RunResult, UndoResult
      sandbox.py           # Path validation and sandboxing
  tests/
    test_tools.py
    test_agent.py
    test_resolve.py
    test_sandbox.py
    test_jj.py
```

### 10.1 Dependencies

Core:
- `anthropic` — Anthropic API SDK
- `httpx` — HTTP client (for OpenAI-compatible backends and fetch_url)

Optional:
- `openai` — OpenAI-compatible SDK alternative
- `fastapi` + `uvicorn` — For standalone server mode

No heavy frameworks. Keep the dependency tree small.

---

## 11. Changes Required in Forge

### 11.1 Overview

Forge transitions from owning the agent to being a thin host that proxies to it. The `internal/ops/` package gets replaced by proxy calls to the Python obsidian-agent service.

### 11.2 What stays in Forge (unchanged)

- **Site serving** — `internal/server/` continues to serve rendered HTML
- **Builder** — `internal/builder/` continues to generate static sites
- **Obsidian vault parsing** — `internal/obsidian/` continues to parse markdown for rendering
- **Watch/rebuild** — `internal/watch/` continues to watch for file changes
- **Overlay injection** — `internal/overlay/inject.go` continues to inject ops.js/ops.css into pages
- **Overlay static serving** — `internal/overlay/static.go` continues to serve `/ops/*` assets
- **All other modules** — search, RSS, JSON-LD, templates, themes, etc.

### 11.3 What changes in Forge

#### 11.3.1 Remove `internal/ops/` agent logic

The following files become unnecessary in Forge:

| File | Current role | Disposition |
|---|---|---|
| `internal/ops/agent.go` | LLM agent loop | **Remove** — moved to obsidian-agent |
| `internal/ops/tools.go` | Vault tool implementations | **Remove** — moved to obsidian-agent |
| `internal/ops/jj.go` | Jujutsu wrapper | **Remove** — moved to obsidian-agent |
| `internal/ops/lock.go` | Mutation lock | **Remove** — moved to obsidian-agent |
| `internal/ops/resolve.go` | URL-to-file resolution | **Keep or share** — Forge may still need this for its own path mapping, but the agent also needs it |

#### 11.3.2 Simplify `internal/ops/handler.go`

The handler currently:
1. Accepts HTTP requests
2. Acquires the mutation lock
3. Runs the agent
4. Commits with jj
5. Rebuilds the site
6. Returns the result

After extraction, it becomes a thin proxy:
1. Accept HTTP request from browser
2. Forward to obsidian-agent backend (localhost)
3. Return the response

This can reuse the existing `internal/proxy/reverse.go` reverse proxy, or the handler can be replaced entirely by configuring the proxy to forward `/api/*` to the Python backend.

#### 11.3.3 Update the `dev` command

`internal/cli/dev.go` currently:
- Creates `VaultTools` with the vault root
- Creates the ops handler with agent config, tools, jj, and rebuild callback
- Passes the handler to the server

After extraction:
- The dev command starts (or expects) the obsidian-agent service
- Configures Forge to proxy `/api/*` to the agent's port
- The `--ops-api-key`, `--ops-llm-base-url`, `--ops-llm-model` flags move to the Python service's configuration
- Forge keeps `--proxy-backend` (or a new `--agent-backend`) flag pointing to the Python service

#### 11.3.4 Remove Go LLM dependencies

The current Go implementation makes direct HTTP calls to Anthropic/OpenAI APIs. After extraction, Forge no longer needs any LLM-related code or configuration.

#### 11.3.5 Rebuild coordination

Currently the Go handler calls `builder.Build()` directly after the agent mutates files. Two options after extraction:

**Option A: Agent triggers rebuild via callback/webhook**
- The Python agent calls a Forge endpoint like `POST /api/internal/rebuild` after committing
- Forge runs the build and returns

**Option B: Forge watches for jj commits**
- The existing file watcher detects changes after jj commit
- Incremental rebuild triggers automatically
- No explicit rebuild coordination needed

**Option C: Agent returns, Forge rebuilds**
- Forge's proxy handler, upon receiving the agent's response, triggers a rebuild before forwarding the response to the browser
- Simplest approach, maintains current behavior

Option C is recommended for the MVP as it requires the least change to the overall flow.

### 11.4 Frontend changes

#### 11.4.1 API endpoint rename

The current frontend (`static/ops.js`) calls:
- `POST /api/apply` — Run an instruction
- `POST /api/undo` — Undo last change
- `GET /api/health` — Health check

The MVP spec uses:
- `POST /api/run` — Run an instruction
- `POST /api/undo` — Undo last change
- `GET /api/health` — Health check

The only rename is `/api/apply` to `/api/run`. This is a good time to make that change.

#### 11.4.2 Request/response format

Current request:
```json
{"instruction": "...", "current_url_path": "/..."}
```

MVP spec request (same shape):
```json
{"instruction": "...", "current_url_path": "/..."}
```

Current response format should be updated to match the MVP spec's response model (section 7.3) with `summary`, `changed_files`, `created_files`, and `history_hint`.

### 11.5 Deployment model

For local development:
1. User starts obsidian-agent (e.g., `obsidian-agent serve --vault /path/to/vault --port 9100`)
2. User starts Forge with `forge dev --proxy-backend http://localhost:9100`
3. Forge serves the site, injects the overlay, and proxies `/api/*` to the agent

For production (Tailscale):
- Same model, both services run on the same machine
- Forge is the single network-facing entrypoint
- The agent listens only on localhost

---

## 12. Migration Path

### Phase 1: Build obsidian-agent as a standalone library

- Port tool implementations from Go to Python
- Port agent loop with Anthropic SDK
- Port jj wrapper
- Port path sandboxing
- Port path resolution
- Add a minimal HTTP server wrapper (FastAPI) for testing
- Test against a real vault

### Phase 2: Wire Forge to proxy to obsidian-agent

- Add/update `--agent-backend` flag to Forge dev command
- Route `/api/run`, `/api/undo`, `/api/health` through the reverse proxy
- Add rebuild-after-proxy logic (Option C from section 11.3.5)
- Update `ops.js` to use `/api/run` instead of `/api/apply`

### Phase 3: Remove Go agent code from Forge

- Remove `internal/ops/agent.go`, `tools.go`, `jj.go`, `lock.go`
- Simplify `handler.go` to pure proxy (or remove it entirely if using `reverse.go`)
- Remove LLM-related CLI flags
- Remove LLM-related Go dependencies

### Phase 4: Extend obsidian-agent toward full architecture

- Add SSE streaming from the agent loop
- Add session/context management
- Add `fetch_url` and `get_file_history` tools
- Support the full interface architecture's submission envelope

---

## 13. Acceptance Criteria (Phase 1)

The obsidian-agent library is correct when:

1. It can accept a natural-language instruction and a URL path
2. It resolves the URL path to a vault-relative markdown file
3. It runs an LLM agent loop with read/write/list/search tools
4. Tools correctly sandbox paths within the vault root
5. After mutation, it commits with jj
6. It returns a structured result with summary and changed files
7. It supports undo via jj undo
8. It enforces one mutation at a time via a lock
9. It works with the Anthropic API
10. It can optionally work with OpenAI-compatible backends

---

## 14. Explicit Non-Goals for Phase 1

- HTTP server as a hard requirement (library-first)
- SSE streaming
- Session persistence
- Chat/conversation history
- Interface registry
- Frontend code
- Database-backed state
- Multi-user support
- Authentication
