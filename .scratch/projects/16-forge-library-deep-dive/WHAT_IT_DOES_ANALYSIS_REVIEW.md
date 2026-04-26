# What Forge Does: Deep Analysis and Review

## Functional Capability Map

Forge's behavior falls into four capability domains:

1. Build static sites from Obsidian vault content
2. Serve output with clean URL behavior for local preview/dev
3. Watch vault changes and incrementally rebuild
4. Route and augment runtime requests (`/api` proxy, `/ops`, optional injection)

## 1) Static Site Generation Capabilities

### Content discovery and indexing

During scan/build Forge discovers vault structure:

- markdown notes (`.md`)
- canvas files (`.canvas`)
- base/config abstractions (`.base`, custom-mode configs)
- static assets (images and other allowed file extensions)
- folders/tags/link relationships/backlinks

Implementation center:

- `internal/obsidian/obsidian.go`
- `internal/builder/builder_default.go`
- `internal/builder/builder_custom.go`

### Markdown and Obsidian feature support

Renderer stack combines Goldmark plus Obsidian-specific behavior:

- wikilinks and embeds
- frontmatter
- callouts
- tags
- Mermaid blocks
- MathJax delimiters
- syntax highlighting
- TOC extraction

Implementation center:

- `internal/obsidian/markdown/markdown.go`
- `internal/obsidian/markdown/wikilinks.go`
- `internal/obsidian/markdown/transformer.go`
- `internal/obsidian/markdown/toc.go`

### Generated outputs

Default mode generates:

- page HTML for notes/folders/tags/canvas/graph/404
- `graph.json`
- `search.json` (search index)
- site assets (`style.css`, `shared.css`, `app.js`, `graph.js`, `canvas.js`, `search.js`, etc.)
- feed/sitemap/robots/CNAME/favicon/redirects when applicable
- OG/Twitter images

### Theming/layout behavior

- Theme definitions are embedded YAML-backed (`internal/builder/themes.yaml`)
- Theme resolution supports accent variants and font handling
- Layout-specific templates are loaded and merged with shared assets

## 2) Local Serving Capabilities

`forge serve` and `forge dev` expose local HTTP serving behavior:

- extensionless route resolution:
  - try `path.html`
  - try `path/index.html`
- custom 404 fallback from generated `404.html`
- base-path support when serving under a path prefix

Implementation center:

- `internal/server/server.go`

## 3) Dev Watch and Incremental Rebuild Capabilities

`forge dev` performs:

1. Initial full build
2. Mtime baseline capture
3. Dependency graph construction
4. File watch with debounce
5. Incremental rebuild on changed/removed paths
6. SSE publish event on rebuild (`{"type":"rebuilt"}`)

Implementation center:

- `internal/cli/dev.go`
- `internal/watch/watcher.go`
- `internal/watch/changeset.go`
- `internal/overlay/events.go`

## 4) Runtime Routing and Integration Capabilities

Forge runtime routing distinguishes request classes:

- `/api/*` -> API handler or reverse proxy backend
- `/ops/events` -> SSE stream
- `/ops/*` -> overlay static file serving
- everything else -> static site handler (optionally with HTML injection)

Implementation center:

- `internal/server/mux.go`
- `internal/proxy/reverse.go`
- `internal/overlay/inject.go`
- `internal/overlay/static.go`

## CLI-Level User Actions It Supports

From command surface:

- `init`: scaffold vault and config
- `generate`: full static build
- `serve`: static preview
- `dev`: build + watch + serve + optional routing extensions
- `doctor`: broken-link checks
- `stats`: vault stats
- `clean`: remove output directory

## What It Does Not Do (By Current Runtime Design)

1. It does not own in-process ops mutation runtime as a primary runtime path.
2. It does not require a database for core operation.
3. It does not depend on network services for static generation itself.
4. It does not directly expose a "SDK API contract" as its primary usage model.

## Analysis: Capability Coherence

Forge capabilities are coherent around one main product promise:

"Take Obsidian-style content, build static output fast, and provide a dev runtime that can attach interactive editing integrations without collapsing the SSG architecture."

That coherence is visible in:

- explicit build context passing
- compositional routing
- package separation by domain (builder/obsidian/server/proxy/overlay/watch)

## Review: Strengths

1. Practical feature depth for Obsidian-style sites.
2. Strong local dev ergonomics (watch + incremental + SSE).
3. Integration points are explicit and easy to reason about (`--proxy-backend`, `--overlay-dir`, `--inject-overlay`).
4. Good separation between content compilation and API mutation concerns.

## Review: Tradeoffs

1. The more capabilities enabled (overlay + proxy + external agent), the more operational moving parts users must configure.
2. Custom mode introduces significant modeling power but also greater complexity.
3. Multiple setup paths (plain local, demo, Docker stack) can create onboarding branch confusion without clear intent-specific guidance.

## Practical Summary

Forge is capable of:

- being a standalone Obsidian-to-static publisher
- and being the presentation/runtime gateway for an interactive editing stack

without forcing users into only one of those two operating models.

