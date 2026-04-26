# Architecture Refactor Research Report — Detailed Review

**Reviewing:** `forge-architecture-refactor.md` (deep research synthesis)
**Date:** 2026-04-07
**Method:** Line-by-line review against actual Forge source code and all prior concept documents

---

## Executive Summary

The research report is **substantively accurate** in its reading of the codebase and its synthesis of the three-library split. It correctly identifies the key boundary violations, the migration path, and the existing ecosystem options. The three-library split (Forge, obsidian-ops, obsidian-agent) is the right architecture — obsidian-ops as a standalone vault interaction primitive layer that obsidian-agent imports but that remains independently useful. However, the report has several gaps: it underestimates the complexity of the PathIndex/rebuild coupling, doesn't sufficiently flesh out obsidian-ops's standalone value proposition and API surface, and doesn't adequately address the practical sequencing of work or the risks of the Jujutsu dependency crossing process boundaries. Below is a section-by-section review with findings.

---

## Section-by-Section Review

### 1. "What Forge contains today" (lines 13–28)

**Accuracy: Correct**

The report correctly identifies the four host-layer responsibilities:

| Claim | Verified Against |
|-------|-----------------|
| HTML overlay injection inserts `/ops/ops.css` and `/ops/ops.js` before `</head>` | `internal/overlay/inject.go` — confirmed, injects exact tags via `responseRecorder` |
| Overlay static serving at `/ops/*` | `internal/overlay/static.go` — `http.StripPrefix("/ops/", http.FileServer(...))` |
| `/api/` dispatched to APIHandler, fallback to proxy | `internal/server/mux.go:NewForgeHandler` — confirmed, exact branching logic |
| Reverse proxy via `httputil.ReverseProxy` | `internal/proxy/proxy.go` — confirmed |

The report also correctly identifies the coupling problem: `internal/cli/dev.go` wires `ops.NewHandler()` directly into `ForgeConfig.APIHandler`, making the agent in-process by default. The mux does fall back to `ProxyHandler` when `APIHandler` is nil — this is verified in `mux.go`.

**One nuance missed:** The injection middleware also handles Content-Length recalculation (removes the header since body size changes). Minor, but relevant if anyone tries to reproduce the injection behavior in another language.

---

### 2. "The goal modal interface with swappable UI modes" (lines 30–47)

**Accuracy: Correct, well-sourced**

The report accurately summarizes `FORGE_INTERFACE_ARCHITECTURE.md`:
- Persistent launcher → operations shell (not full-page takeover)
- Bottom tab bar driven by a mode registry
- Generic submission envelope with `interface_id`
- Same-origin `/api/*` via Forge proxy
- SSE for progress (websockets deferred)

The contrast with the current `ops.js` implementation is accurate: single-mode modal, no registry, fixed `{instruction, current_url_path}` contract to `/api/apply`.

**Design implication is sound:** The recommendation to avoid per-mode endpoints and use a generic envelope with `interface_id` is directly supported by the architecture doc's own drift-risk callout.

**Gap:** The report doesn't mention that `FORGE_INTERFACE_ARCHITECTURE_MVP.md` exists as a stepping stone. The MVP spec is important because it validates the current simplified contract as intentionally minimal — the multi-mode shell is a planned evolution, not a prerequisite for the split. This distinction matters for sequencing: you can extract the agent without touching the UI contract at all.

---

### 3. "Proposed three-library split" (lines 49–98)

#### 3a. Forge (lines 51–63)

**Accuracy: Correct**

The boundary is well-defined: keep injection, `/ops/*` serving, reverse proxy, and Kiln. Remove everything under `internal/ops/`.

The "practical enforcement" recommendation (`APIHandler=nil` by default, rely on `ProxyHandler`) is the right approach and is verified by the mux fallback logic.

**Missing consideration: PathIndex ownership.** Currently `PathIndex` is created and updated in `dev.go`, then passed into `ops.NewHandler()`. After the split, who owns URL-to-file resolution?

- **Option A:** Forge keeps PathIndex and exposes it via a new endpoint (e.g., `GET /api/resolve?url=/projects/alpha/`), so the Python backend can resolve URLs.
- **Option B:** The Python agent builds its own path index by scanning the vault directory.
- **Option C:** Forge passes the resolved file path as an additional field in the proxied request (header or body rewrite).

Option C is simplest and preserves the current data flow without adding new endpoints. The report doesn't address this, but it's a concrete decision that must be made during extraction.

**Missing consideration: Rebuild triggering.** Currently, after the agent finishes, `handler.go` calls a `RebuildFunc` callback that triggers `builder.Build()`. Once the agent is a separate process behind the proxy, how does Forge know to rebuild?

The existing file watcher (`internal/watch/watcher.go`) already monitors the vault directory and triggers incremental rebuilds on file changes (with 300ms debounce). This means the watcher should automatically detect agent-written files and rebuild — **no explicit rebuild trigger is needed** in the proxy path. The report doesn't call this out, but it's actually a simplification: removing the explicit rebuild callback from the handler and relying entirely on the watcher is cleaner and eliminates the cross-process rebuild coordination problem.

However, there's a timing subtlety: the current in-process flow is synchronous (agent writes → commit → rebuild → respond), so the response to the browser always reflects the rebuilt state. With the watcher, there's a race: the agent responds before the watcher detects changes and rebuilds. The user might click "Refresh" and see stale content. The `SIMPLIFIED_CONCEPT.md` doc acknowledges this as an acceptable MVP tradeoff ("rebuild timing: user may see stale page"), but the research report should have flagged it.

---

#### 3b. Obsidian Editing Server / obsidian-ops (lines 65–81)

**Accuracy: Correct direction, but needs sharper articulation of the standalone value**

The report correctly proposes this as a dedicated layer between the agent and the vault filesystem, with two backend interpretations:
1. **Plugin-backed:** Use the Obsidian Local REST API plugin when desktop Obsidian is available.
2. **Headless:** Implement the same capabilities in Python for docker/headless deployments.

**The three-library split is the right call.** obsidian-ops should be a standalone Python package that provides vault interaction primitives — importable as a library by obsidian-agent, but independently useful as a server endpoint that connects commands to the Obsidian vault. This separation has clear architectural value:

- **Independent utility:** Scripts, CLI tools, other agents, CI pipelines, and non-LLM workflows can all interact with the vault through obsidian-ops without pulling in the agent's LLM dependencies.
- **Clean dependency direction:** obsidian-agent depends on obsidian-ops, never the reverse. This prevents the vault interaction layer from accumulating agent-specific concerns.
- **Testability:** Vault operations (sandboxing, frontmatter patching, content editing, search) can be tested in isolation without mocking LLM calls or agent state.
- **Composability:** Other agent frameworks (not just obsidian-agent) could use obsidian-ops as their vault backend — directly aligned with the "opencode for Obsidian" vision.

The current Go implementation (`ops/tools.go`) has basic read/write/list/search with sandboxing. obsidian-ops should go beyond this baseline to include the richer primitives the report identifies:
- Frontmatter read/write/patch (targeted field operations, not full-file rewrites)
- Content patching by semantic anchors (heading, block reference)
- Extension hooks for custom scripts/skills
- The same safety properties: vault-root sandboxing, symlink guards, mutation lock

**What the report underdelivers on:** It doesn't clearly articulate obsidian-ops's **API shape as a standalone server**. If it's going to serve as an independent endpoint, it needs a well-defined HTTP surface — not just "the same primitives as VaultTools." Key questions the report should have addressed:

- **Endpoint design:** RESTful resource-oriented (`GET /files/{path}`, `PATCH /files/{path}/frontmatter`) vs. RPC-style (`POST /read`, `POST /write`)?
- **Dual-use surface:** How does the same package work both as an importable Python library (`from obsidian_ops import VaultTools; tools.read_file("note.md")`) and as an HTTP server (`uvicorn obsidian_ops.server:app`)?
- **Relationship to obsidian-agent's HTTP surface:** Does obsidian-agent proxy to obsidian-ops's HTTP server, or does it import the library directly and only expose its own `/api/apply` endpoint to Forge? The latter is simpler for the MVP (two processes: Forge + agent), with obsidian-ops as a library dependency rather than a third running service.

**Recommended architecture for MVP:** obsidian-ops is a Python package (installable via pip). obsidian-agent imports it directly as a library. obsidian-ops *also* ships an optional HTTP server entrypoint for standalone use. This gives you two deployment models:
- **Integrated (MVP):** Forge → proxy → obsidian-agent (which imports obsidian-ops internally). Two processes.
- **Standalone:** obsidian-ops runs as its own server for scripts/tools/other agents. No LLM involvement.

This is a stronger framing than the research report provides — the report describes obsidian-ops primarily through the lens of the Local REST API plugin, but the real value is the **library-first, server-optional** design that keeps the dependency graph clean.

---

#### 3c. Python Obsidian Agent Framework (lines 83–98)

**Accuracy: Correct and well-aligned with existing concept docs**

The report accurately summarizes what the agent framework should own:
- Agent loop orchestration (replacing `ops/agent.go`)
- Mode-aware interface handlers (registry pattern)
- Session state and run history
- Versioning/undo via Jujutsu
- HTTP surface proxied behind Forge

The references to pi-mono's layered architecture and obsidian-skills as domain knowledge sources are useful context but somewhat tangential — they're "nice to know" rather than actionable inputs for the immediate extraction.

**Gap: Jujutsu across process boundaries.** Currently, `ops/jj.go` runs `jj` commands against the vault directory, which is the same directory Forge watches and builds from. After the split:
- The Python agent runs `jj` commands against the vault.
- Forge's watcher detects the resulting file changes and rebuilds.
- `jj undo` in the Python agent reverts files, which the watcher also detects.

This works, but there's a subtle issue: `jj undo` may revert files that the watcher has already processed, causing a double rebuild. More importantly, if Forge's dev server is writing any state to the vault directory (it shouldn't be, but worth verifying), `jj` operations could conflict. The report doesn't explore this.

---

### 4. "Obsidian API landscape" (lines 100–134)

**Accuracy: Good ecosystem survey**

The coverage of the Local REST API plugin, obsidian-skills, obsidiantools, and py-obsidianmd is useful context. The distinction between "HTTP API with patch semantics" (Local REST API) and "Python libraries for metadata manipulation" (obsidiantools, py-obsidianmd) is correctly drawn.

**Practical concern:** The Local REST API plugin requires a running Obsidian desktop instance. For the primary deployment scenario described in the concept docs (headless Docker + Tailscale), this plugin is not usable. The report acknowledges this but then continues to reference it as a design blueprint. This is fine for API design inspiration, but the implementation path is clearly the headless Python approach.

---

### 5. "Migration path" (lines 136–183)

**Accuracy: Sound overall, with some sequencing gaps**

#### Step 1: Align Forge with thin host role (lines 138–146)

Correct. Setting `APIHandler=nil` and relying on `ProxyHandler` is the right technical change. The mux already supports this.

**Addition needed:** When `APIHandler=nil`, the PathIndex and rebuild callback currently wired into `ops.NewHandler()` become unused. The `dev.go` wiring should be simplified to remove the ops-related flag parsing and handler construction entirely. This is straightforward but the report should have been explicit about it.

#### Step 2: Stand up obsidian-ops (lines 148–159)

The specific primitives called out (sandboxing, mutation lock, frontmatter ops, content patching, extension mechanism) are the right requirements. obsidian-ops should be built as a standalone Python package first, with a clean library API, then obsidian-agent imports it. This order is correct because obsidian-ops has no dependency on the agent and can be developed and tested independently.

**Addition needed:** The report should specify that obsidian-ops ships both a library interface (`from obsidian_ops import Vault`) and an optional HTTP server entrypoint. For the MVP integration with Forge, the agent imports the library directly — obsidian-ops doesn't need to run as a separate process until there are standalone consumers.

#### Step 3: Replace Go agent with Python (lines 161–169)

The four-step migration sequence is practical and well-ordered:
1. Implement `/api/apply`, `/api/undo`, `/api/health` in Python
2. Keep request payload identical (`instruction`, `current_url_path`)
3. Move to Python tool implementations
4. Add Jujutsu wrappers

**Missing step:** The report doesn't mention that `ops/resolve.go` (PathIndex) must either be ported to Python or handled by Forge (see discussion in 3a above). The Python agent needs to know which vault file corresponds to `current_url_path`. This is a concrete gap.

**Missing step:** The report doesn't address how the Python agent discovers its configuration. The `SIMPLIFIED_CONCEPT.md` specifies `AGENT_*` environment variables, and the `OBSIDIAN_AGENT_CONCEPT.md` specifies `AgentConfig` with explicit fields. The report should reference these existing specs.

#### Step 4: Evolve modal UI (lines 172–183)

Correct that this is independent of the backend split and can happen later. The registry pattern, tab bar, and generic envelope are well-described in the architecture doc.

**Important sequencing note:** The UI evolution should happen *after* the backend split is stable, not during it. The report implies this ordering but doesn't state it explicitly.

---

## Cross-Cutting Concerns Not Addressed

### 1. Error propagation through the proxy

Currently, `handler.go` returns structured JSON errors with specific HTTP status codes (409 for lock conflicts, 500 for agent errors). When Forge proxies to the Python backend, these responses pass through transparently — but the proxy adds its own failure modes (connection refused, timeout, bad gateway). The frontend `ops.js` needs to handle proxy-layer errors in addition to application-layer errors. The current implementation has basic error handling but assumes the backend is always reachable.

### 2. Health check semantics

`GET /api/health` currently returns `{"ok": true}` from the in-process handler. When proxied, it becomes a health check of the Python backend. Forge itself has no separate health endpoint — if the proxy is configured and the backend is down, `/api/health` will return a proxy error. Consider whether Forge should have its own health endpoint (e.g., `GET /ops/health`) independent of the backend.

### 3. Logging and observability

The current Go implementation uses `slog.Logger` throughout, with structured logging in the agent loop (tool calls, LLM responses, timing). The Python agent should maintain equivalent observability. The report doesn't mention logging requirements.

### 4. The 3-minute agent timeout

`ops/agent.go` enforces a 3-minute context deadline. The proxy handler in `proxy.go` has a configurable `ResponseHeaderTimeout`. These need to be coordinated: the proxy timeout must exceed the agent timeout, or the proxy will kill the connection before the agent finishes. The `SIMPLIFIED_CONCEPT.md` specifies agent=120s, proxy=180s. The report should have referenced these concrete values.

### 5. Docker deployment changes

The current Dockerfile builds a single Go binary with embedded assets. After the split, the Docker deployment needs:
- A Python runtime (or a separate container for the agent)
- Two processes (Forge + Python agent) managed by a supervisor
- The `SIMPLIFIED_CONCEPT.md` proposes `obsidian-ops` as the orchestrator. The Dockerfile and docker-compose.yml will need significant changes.

### 6. The `internal/ops/agent.go` complexity

At 991 lines, the agent module is the largest and most complex file in the repository. It handles:
- Dual backend support (Anthropic + OpenAI-compatible)
- Multiple tool-call parsing formats (native, XML, JSON-in-prose, Qwen edge cases)
- System prompt construction
- Tool execution and result formatting
- Conversation history management

Porting this to Python is the highest-risk item in the migration. The Python ecosystem has better SDKs (anthropic, openai) that handle much of the parsing complexity, but the dual-backend support and edge-case handling represent significant accumulated knowledge. The report underemphasizes this risk.

---

## Comparison with Existing Concept Documents

| Document | Alignment with Research Report |
|----------|-------------------------------|
| `SIMPLIFIED_CONCEPT.md` | **High.** Both describe the same core split. The research report correctly identifies obsidian-ops as a third library; SIMPLIFIED_CONCEPT.md merges vault tools into the agent but the separation is a natural evolution of the same boundary. |
| `OBSIDIAN_AGENT_CONCEPT.md` | **High.** The research report's description of the Python agent matches this spec closely. |
| `FORGE_INTERFACE_ARCHITECTURE.md` | **High.** The research report accurately summarizes the multi-mode shell spec. |
| `FORGE_INTERFACE_ARCHITECTURE_MVP.md` | **Underreferenced.** The MVP spec validates the current simplified contract and provides a clear stepping stone. |

---

## Verdict: What's Right, What's Wrong, What's Missing

### Correct

1. The three host-layer responsibilities of Forge are accurately identified and verified against source.
2. The `APIHandler=nil` enforcement mechanism is the right approach and works with existing mux logic.
3. The current `internal/ops` package clearly violates the "thin host" goal and should be extracted.
4. The multi-mode shell design is accurately summarized and correctly identified as a future evolution.
5. The generic submission envelope with `interface_id` is the right pattern for preventing endpoint sprawl.
6. The Python ecosystem is a better fit for the agent runtime (better LLM SDKs, tool-use patterns).
7. The migration sequence (match existing contract → port tools → add jj → evolve UI) is practical.

### Needs Strengthening

1. **obsidian-ops's standalone value and API surface are underspecified.** The three-library split is correct, but the report leans too heavily on the Local REST API plugin as a framing device rather than articulating obsidian-ops's own identity: a library-first Python package for vault interaction primitives, with an optional HTTP server for standalone use. The report should define the library API shape, the HTTP endpoint design, and the dual-use (import vs. serve) model.
2. **The Local REST API plugin is overemphasized as a practical runtime option.** It requires desktop Obsidian, which conflicts with the primary headless/Docker deployment model. It's useful as API design inspiration but not as a runtime dependency.

### Missing

1. **PathIndex ownership after the split.** Who resolves `current_url_path` to a vault file path? This is a concrete decision with multiple valid approaches.
2. **Rebuild timing semantics.** The watcher-based rebuild introduces a race condition vs. the current synchronous flow. This is acknowledged in SIMPLIFIED_CONCEPT.md but not in the research report.
3. **Error propagation through the proxy layer.** New failure modes (connection refused, timeout) that don't exist in the current in-process model.
4. **Timeout coordination.** Agent timeout vs. proxy timeout must be explicitly configured.
5. **Docker/deployment architecture changes.** Two processes, Python runtime, process supervision.
6. **Logging and observability requirements** for the Python agent.
7. **The complexity and risk of porting `agent.go`** (991 lines of accumulated edge-case handling for dual backends and multiple tool-call formats).
8. **Configuration discovery** for the Python agent (existing specs define this but the report doesn't reference them).

---

## Recommended Next Steps

1. **Build obsidian-ops first** as a standalone Python package (library-first, server-optional). Port the vault safety properties from Go (`safePath`, `MutationLock`), then add the richer primitives (frontmatter patching, semantic-anchor content editing). This has zero external dependencies and can be tested in isolation.
2. **Build obsidian-agent second**, importing obsidian-ops for vault interaction. Port the agent loop from `agent.go`, leveraging Python SDKs (anthropic, openai) to eliminate the custom tool-call parsing. This is the highest-risk item due to the 991 lines of accumulated edge-case handling.
3. **Decide PathIndex ownership** before wiring the proxy. Recommend Option C: Forge passes the resolved file path as a header in the proxied request.
4. **Slim down Forge** to the thin host role: set `APIHandler=nil`, remove `internal/ops/`, simplify `dev.go` wiring.
5. **Accept the rebuild timing race** for MVP (watcher-based detection is good enough).
6. **Defer the multi-mode shell** until the backend split is stable and proven in production.
7. **Update the Dockerfile** and docker-compose.yml as part of the integration phase, not as an afterthought.
