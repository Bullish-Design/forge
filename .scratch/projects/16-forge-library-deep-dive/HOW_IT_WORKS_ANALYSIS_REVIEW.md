# How Forge Works: Deep Analysis and Review

## End-to-End Architecture

At runtime, Forge is a layered flow:

1. CLI command resolves config + flags
2. Build pipeline compiles vault content to output files
3. Server layer serves static output with clean URLs
4. Dev mode adds watcher + incremental build loop
5. Forge handler routes `/api` and `/ops` requests and optionally injects overlay assets

## Layer 1: CLI Orchestration

Entrypoint:

- `cmd/forge/main.go` -> `cli.Init()` -> Cobra commands

Command behavior:

- `generate`:
  - resolves merged config (flags + `kiln.yaml`)
  - constructs `builder.BuildContext`
  - runs `builder.Build(context)`
- `dev`:
  - same context resolution
  - full build
  - watch + incremental rebuild setup
  - server start with Forge routing config

Key detail:

- Config precedence is explicit:
  - if flag is not changed, use config field fallback (`resolveStringFlag` / `resolveBoolFlag`)

## Layer 2: Build Engine

### Core build dispatch

- `builder.Build(context)`:
  - safety-clean output dir (`CleanOutputDir`)
  - mode dispatch:
    - default -> `buildDefault(context, nil)`
    - custom -> `buildCustom(context)`

### Default-mode pipeline (`buildDefault`)

High-level sequence:

1. Resolve theme + layout templates
2. Scan vault into canonical model (`obsidian.New(...).Scan()`)
3. Instantiate markdown engine with resolver/index context
4. Categorize vault files (notes/base/canvas/static)
5. Copy static assets and optimize images where applicable
6. Render pages:
   - folders
   - canvas
   - base pages
   - notes
   - tags
7. Build search index
8. Write compiled CSS/JS assets
9. Write metadata pages/files (`graph.json`, graph page, 404, sitemap, RSS, robots, etc.)

Error behavior:

- `ErrorCollector` aggregates non-fatal per-file/per-stage build failures so build can finish and report totals.

### Custom-mode pipeline (`buildCustom`)

High-level sequence:

1. Vault scan
2. Construct `CustomSite` model maps
3. Walk and classify files
4. Parse env/config/components/layouts
5. Load notes and static assets
6. Validate frontmatter fields against collection config
7. Render templates per page (collection or custom layout)

Custom mode is content-model driven and template-centric, with stronger field typing and validation than default mode.

## Layer 3: Obsidian Parsing and Markdown Rendering

### Vault processing

`obsidian` package handles:

- file/folder path normalization
- output/web path derivation
- metadata extraction from markdown
- wikilink/embed/tag/link parsing
- backlink generation
- sitemap/RSS data feeding

### Markdown engine composition

`internal/obsidian/markdown/markdown.go` composes:

- Goldmark core
- GFM + Footnote + metadata
- math extension
- syntax highlighting
- wikilink resolver
- post-render transform chain

Transform chain (`applyTransforms`):

1. highlights
2. mermaid container normalization
3. callout conversion
4. tag-to-link conversion

Resolver behavior:

- link/image/wikilink rendering hooks normalize URLs
- graph links are recorded while resolving internal references
- embed depth and circular guard logic are enforced

## Layer 4: Dev Watch and Incremental Rebuild

In `dev` mode:

1. Forge scans initial vault and builds dependency graph.
2. `watch.Watcher` recursively watches directories (skips hidden patterns).
3. File events are debounced.
4. Mtime update computes changed/removed paths.
5. `watch.ComputeChangeSet` expands dependents via graph edges.
6. `builder.IncrementalBuild(...)` re-renders only relevant outputs.
7. SSE broker publishes rebuild signal to `/ops/events`.

This design keeps feedback fast without forcing full rebuild on every write.

## Layer 5: Request Routing and Serving

### Static server behavior (`server.Serve`)

- clean URL fallback logic
- custom 404 handling
- optional base path mount support

### Forge request multiplexer (`NewForgeHandler`)

Route order:

1. `/ops/events` -> SSE handler
2. `/api/*` -> API handler if present, otherwise proxy handler
3. `/ops/*` -> overlay static files
4. fallback -> injected static handler

### Injection middleware

When enabled, Forge captures HTML responses and inserts:

- `/ops/ops.css`
- `/ops/ops.js`

before `</head>`, then recalculates `Content-Length`.

### Reverse proxy details

Proxy setup includes:

- backend scheme/host rewrite
- forwarded headers:
  - `X-Forwarded-For`
  - `X-Forwarded-Proto`
  - `X-Forwarded-Host`
- configurable response header timeout

## Concurrency and Lifecycle

- server runs in main goroutine
- watcher loop runs in background goroutine
- signal context (`SIGINT`, `SIGTERM`) coordinates shutdown
- server shutdown uses timeout context for graceful close

## Analysis: Why This Internal Design Works

1. Clear package boundaries reduce accidental coupling.
2. Build and runtime concerns are separated but composable.
3. Incremental rebuild is dependency-aware, not naive mtime-only rerender.
4. Proxy/injection features are additive, not intrusive into static build core.

## Review: Engineering Quality Signals

Positive signals:

- explicit context objects over global mutable state
- dedicated error aggregation path for build
- focused tests around routing, events, and watcher behaviors
- deprecation notices in code for old runtime paths (`internal/ops`)

Residual technical risk areas:

1. Complexity of custom-mode typing and template behavior can be harder to reason about than default mode.
2. Runtime correctness depends on clean composition of multiple optional handlers in `ForgeConfig`.
3. Incremental rebuild correctness is only as good as dependency graph completeness.

## Practical Mental Model

You can think of Forge as:

- compiler: vault -> static site artifacts
- dev kernel: watch + rebuild + serve
- edge adapter: proxy/inject/overlay route glue

That mental model remains stable across small local use and full multi-service deployments.

