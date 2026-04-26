# Deep research on splitting Forge into Forge, an Obsidian editing server, and a Python Obsidian agent framework

## Research scope and key takeaways

The Bullish-Design Forge repository on GitHub already contains most of what you want in the first library (Kiln + overlay injection + reverse proxy + overlay static assets), plus an additional “ops backend” currently implemented in Go that you explicitly want to move out.

Your “goal interface” for easily swapping UI modes inside the popup is documented in `.scratch/projects/02-reconcept-refactoring/FORGE_INTERFACE_ARCHITECTURE.md` as a generic “operations shell” with a tab bar and a registry-driven mode system (Command, Chat, etc.), sitting on top of rendered pages and routing all actions through same-origin `/api/*` calls proxied by Forge.

For the second library (“Obsidian editing server / Obsidian API”), there is a high-quality existing option: the **Obsidian Local REST API** plugin (community plugin) provides file CRUD and *surgical patching* of headings, block references, and frontmatter fields, as well as search (including Dataview DQL / JsonLogic) and an extension interface for other plugins to add routes.

For the third library (Python agent framework + “pi-mono starter”), there is a clear pattern to emulate: **pi-mono** is organized as layered packages (unified LLM API, agent-core runtime, UIs, etc.). Separately, **obsidian-skills** provides “skills” describing Obsidian file grammars (Obsidian-flavored Markdown, Bases, JSON Canvas) and tool surfaces in a standardized “Agent Skills” format, explicitly designed to be consumed by multiple agent harnesses (Claude Code, Codex CLI, OpenCode).

## What Forge contains today and what that implies for the split

Forge’s host-layer responsibilities (the part you want to keep as “Forge”) are implemented as three small internal Go packages plus frontend assets:

- **HTML overlay injection** inserts tags for `/ops/ops.css` and `/ops/ops.js` right before `</head>` when enabled.  
- **Overlay static serving** is routed at `/ops/*` (serving the injected assets).  
- **API routing**: requests under `/api/` are dispatched to `APIHandler` if configured; otherwise they fall back to a reverse proxy handler.  
- **Reverse proxy** is implemented via `httputil.ReverseProxy`, with a configurable backend URL and response-header timeout.

The current overlay UI in `static/ops.js` is a “single-modal MVP”: it injects a floating action button, opens a modal with a textarea + Run/Undo/Refresh, and posts to `POST /api/apply` and `POST /api/undo`.

However, the dev command (`internal/cli/dev.go`) *also wires an in-process Go ops backend* (`internal/ops`) into `APIHandler`, meaning `/api/*` is served by Forge itself rather than being proxied to an external backend (unless you explicitly set `APIHandler=nil`).

That `internal/ops` package is substantial and already contains many things you want to move into Python: a tool-calling LLM loop that supports both Anthropic and OpenAI–compatible endpoints, a sandboxed “vault tools” layer (read/write/list/search), a Jujutsu wrapper, a mutation lock, URL→file resolution via a path index, and HTTP handlers for `/api/apply`, `/api/undo`, and `/api/health`.

The repo’s own concept docs explicitly describe the intended separation: Forge as “thin host” (Kiln dev + HTML injection + `/api/*` reverse proxy + `/ops/*` assets), with a separate backend process owning the agent loop and vault tools behind `POST /api/apply`, `POST /api/undo`, `GET /api/health`.

## The goal modal interface with swappable UI modes

The concept document you’re referring to—the one that makes UI mode swapping “easy”—is the “multi-interface overlay architecture” spec. It proposes that:

- A persistent launcher opens a shared “operations shell” layered over the rendered page (not a full-page takeover).  
- Inside that shell, multiple interface modes exist (Command, Chat, future Diff/Review/Runs/Context), and the UI switches modes using a **bottom tab bar**.  
- Mode switching is driven by a **registry**, not hard-coded toggles (“tabs should come from a registry”).  
- Submissions should go to a **generic endpoint** using an envelope that includes `interface_id` (and later `session_id`, page context, optional selection), so new modes don’t force backend endpoint sprawl.  
- Transport should be **same-origin `/api/*`** calls via Forge’s proxy; the v1 recommendation is `POST` for submission + **SSE** for progress/results (with websockets deferred).

This is materially different from the current `ops.js` implementation, which is a single-mode modal (no registry, no tabs), and whose request contract is fixed to `{instruction, current_url_path}` going to `/api/apply`.

Design implication for your split: if you want *easy* mode switching, the backend should not expose “one endpoint per UI mode.” Instead, you want either:

- one “submit” endpoint that accepts `interface_id` (and can dispatch to an interface handler map), or  
- a stable “run” endpoint that accepts a structured request with `interface_id` and lets the backend interpret it.

That is precisely the drift risk called out in the architecture doc (“generic interfaces can encourage backend sprawl… mitigate by standardizing on a generic interface submission envelope”).

## Proposed three-library split with concrete boundaries

### Forge

**Purpose:** keep Forge as the Go “host + UI bridge” layer: Kiln dev/build/watch/serve plus the overlay injection, overlay static serving, and `/api/*` reverse proxy.

**What stays (evidence in repo):**
- Injection middleware (adds `<link rel="stylesheet" href="/ops/ops.css">` and `<script src="/ops/ops.js" defer></script>`).  
- `/ops/*` static serving and handler chain routing (`/api/` first, then `/ops/`, then base).  
- Reverse proxy handler construction, configured by a backend URL + timeout.  
- The current modal overlay assets as a baseline (even if you later implement the multi-mode shell).

**What should leave Forge:** everything currently under `internal/ops` (LLM loop, vault tools, JJ, lock, apply/undo handlers), because it violates the “Forge stays thin host/proxy” goal stated in both the simplified MVP doc and the multi-interface architecture doc.

A practical way to enforce this boundary is to make Forge run with `APIHandler=nil` by default and rely on `ProxyHandler` for `/api/*` (since the mux already falls back to proxy when `APIHandler` is nil).

### Obsidian editing server

**Purpose:** “Obsidian API” as a service: the authoritative endpoint that performs *actual vault edits* and exposes primitives for editing **frontmatter** and **content**, plus a minimal “scripting/helpers” extension mechanism.

There are two viable interpretations, and you can support both via a backend interface:

- **Plugin-backed API (existing):** adopt the **Obsidian Local REST API** plugin as the editing server when running a desktop Obsidian instance is acceptable. It already provides targeted patching of headings/blocks/frontmatter, full file CRUD (including binary), search (including Dataview DQL and JsonLogic), and a route-extension interface.  
- **Headless file-system editing server (custom):** implement the same *capabilities* in Python against the vault directory directly (for docker/headless deployments), using the Local REST API feature set as a blueprint for your primitives and API ergonomics.

**Why a dedicated editing server (vs folding into the agent):** it creates a stable, testable “Obsidian filesystem API” that both the agent framework and non-agent tools/scripts can rely on. This mirrors the Local REST API plugin’s intentional separation and explicit “extend the API” mechanism.

**Minimum primitive surface (strongly aligned to what already exists in Forge + best-in-class external API):**
- Safe, sandboxed file addressing within a configured vault root (Forge’s Go `VaultTools.safePath` forbids absolute paths, blocks `..`, and guards against symlink escape).  
- Read/write/list/search operations (Forge already has these primitives; the agent tool loop uses them under tool names like `read_file`, `write_file`, `list_files`, `search_files`).  
- Frontmatter operations as first-class primitives (read/replace/merge/set/delete; nested paths; preserve ordering/format where possible). The Local REST API plugin explicitly supports targeting frontmatter fields and replacing values via PATCH.  
- Content patching relative to semantic anchors (heading, block reference) rather than “rewrite full file”; again, Local REST API exposes this as a core feature.  
- Extension hooks / scripting: the Local REST API plugin advertises an “extend the API” interface; your server can mirror this by loading local “skills/scripts” modules in a controlled way (trusted single-user environment).

### Python Obsidian agent framework

**Purpose:** the agent runtime that “feels like opencode for Obsidian,” but with better ergonomics because the Kiln/Forge overlay UI acts as the primary interaction surface.

Your own repository docs already argue for moving the agent to Python because of ecosystem fit and because the “full multi-interface backend service” (SSE, sessions, interface registry) is better built in Python.

Concretely, this library/framework should own:
- The agent loop orchestration (tool calling, retries, structured results), replacing the current Go loop in `internal/ops/agent.go`.  
- Mode-aware “interface handlers” (Command, Chat, Diff/Review later), matching the “interface registry” idea in the UI spec.  
- Session state, run history, and (later) streaming events via SSE if/when you adopt the full spec transport.  
- Versioning/undo semantics (the current Forge ops stack uses Jujutsu commit+undo; your concept docs preserve that durability model).  
- A stable HTTP surface proxied behind Forge (`/api/*`), starting with the simplified MVP contract and evolving to the generic multi-interface submit contract.

Where “pi-mono starter framework” fits: pi-mono is explicitly structured as layered packages (LLM API, agent-core, UIs, etc.). Even if you implement in Python, you can copy the same layering principle: keep a core agent runtime package, a thin HTTP server package, and a UI-integration package (Forge-aware), rather than baking everything into one app.

A second “starter framework” input is **obsidian-skills**, which provides standardized skills describing Obsidian file grammars and tool usage patterns, designed to be consumed by multiple agent harnesses (including OpenCode). This is directly relevant to your “opencode for Obsidian” goal: you can treat those skills as canonical domain instructions and use them to drive tool schemas, validators, and prompt supplements.

## Obsidian API landscape and what to reuse

### A mature existing Obsidian API

The Obsidian Local REST API plugin is the strongest “already exists” answer for an Obsidian editing API:

- It exposes authenticated HTTPS endpoints for vault file CRUD (including binary), active file operations, periodic notes, multiple search modes, tag queries, and command execution.  
- It supports *targeted edits* (patch/read/write under a heading, a block reference, or a frontmatter field) without rewriting the whole file, and documents PATCH semantics and examples.  
- It advertises an “extend the API” interface so other plugins can register their own routes.

If you can run Obsidian desktop on the server machine (or a companion machine), this plugin can serve as your “Obsidian editing server” almost directly—your agent framework becomes a client that maps higher-level intentions into these patch operations.

### Domain “skills” that can become your helper/scripting layer

The `kepano/obsidian-skills` project provides skills for:
- Obsidian flavored Markdown (`.md`)  
- Obsidian Bases (`.base`)  
- JSON Canvas (`.canvas`)  
- an Obsidian CLI skill for interacting with vaults, plus related tooling instructions

…and it explicitly follows an Agent Skills specification so it can be used by multiple “skills-compatible” agents, including OpenCode.

This is exactly the kind of reusable “helper/scripting primitives” layer you described—except represented as portable skill docs rather than a server. A strong approach is to treat these skill definitions as:
- authoritative format constraints and editing dos/don’ts (validators), and  
- structured “capability modules” that your server/agent can expose as tools.

That reduces the amount of bespoke Obsidian-format knowledge you have to encode yourself.

### Python libraries that help but don’t fully solve the “server” requirement

For Python-native frontmatter/metadata manipulation, there are existing libraries/projects frequently referenced by the Obsidian community:
- `obsidiantools` (metadata extraction, graph/link analysis, frontmatter retrieval).  
- `py-obsidianmd` (batch metadata manipulation, including moving metadata between frontmatter and inline/dataview-style notation).  

These are useful inputs for implementing your own headless editing server, but they’re not drop-in “Obsidian API servers” in the sense of providing a stable HTTP surface with patch semantics.

## Migration path that preserves velocity and enforces boundaries

### Align Forge with the “thin host/proxy” role

Your repo’s own “Simplified MVP” concept doc defines Forge as: Kiln dev + HTML injection + `/api/*` reverse proxy → backend + `/ops/*` asset serving, with a stable shared API contract.

But the actual dev wiring currently creates both a reverse proxy and an in-process ops API handler, and the mux prioritizes `APIHandler` when present.

To make Forge behave as “Kiln + modal UI → server endpoint proxy” (your requested Forge), the key technical change is: **when a backend is configured, run with `APIHandler=nil` so `/api/*` flows through the reverse proxy**. The mux already supports this fallback behavior.

This single change lets you move the ops backend out without rewriting the frontend or the server router.

### Stand up the Obsidian editing server as a stable substrate

Start by porting (or re-implementing) the same safety properties Forge already has in Go:
- strict vault-root sandboxing; forbid absolute paths and vault escapes; guard against symlink traversal.  
- a global mutation lock to enforce “one active mutation at a time,” which matches both the Forge code (`MutationLock`) and the MVP concept’s serial execution model.

Then add the primitives you explicitly called out:
- frontmatter read/write/patch primitives (ideally with targeted patch ops rather than rewriting whole files), aligning with the Local REST API plugin’s successful UX.  
- content patch primitives keyed by semantic anchors (heading/block), again aligned with Local REST API.  
- a small extension mechanism for “helpers/scripts” (mirroring “extend the API” from Local REST API).

At this stage, the agent framework can be very thin: it can call the editing server tools rather than implement file IO itself.

### Replace the Go agent with the Python agent framework

The repo’s `OBSIDIAN_AGENT_CONCEPT.md` is already a near-direct blueprint: it proposes extracting and replacing `internal/ops/` with a standalone Python library because Python is a better environment for agent development (provider SDKs, tool-use patterns, structured parsing), and because the longer-term architecture needs sessions, SSE, and a pluggable interface registry.

A practical migration sequence is:
1. Implement `POST /api/apply`, `POST /api/undo`, `GET /api/health` in Python to match the shared contract described in `SIMPLIFIED_CONCEPT.md`.  
2. Initially keep the request payload identical to today (`instruction`, `current_url_path`) so the existing `ops.js` continues to work unchanged.  
3. Internally, move from the Go tool names (`read_file`, `write_file`, `list_files`, `search_files`) to equivalent Python tool implementations that call your editing server (or the Obsidian Local REST API if you choose that backend).  
4. Add versioning/undo via Jujutsu wrappers similarly to Forge’s current Go implementation (`jj describe` + `jj new` for commit; `jj undo` for undo).

### Evolve the modal UI into the multi-mode shell without backend sprawl

Once the proxy split is stable, you can implement the “goal interface” by evolving `/ops/ops.js` from “single modal” into:
- a shell container + mode registry,  
- a tab bar driven by registered modes, and  
- a submission envelope that includes `interface_id` (plus later `session_id`, selection, etc.).

The critical design constraint is the one your architecture doc already calls out: don’t let every mode create its own endpoint family. Keep one generic submission endpoint and route by `interface_id`.

That gives you the “easily adaptable way to swap between UI modes” you asked about—because adding a new mode is primarily:
- a frontend registration + view component, and  
- a backend handler registration under the same envelope.

Not a cross-cutting `/api/new-mode/*` proliferation.