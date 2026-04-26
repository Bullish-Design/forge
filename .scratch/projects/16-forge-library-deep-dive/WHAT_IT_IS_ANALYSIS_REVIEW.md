# What Forge Is: Deep Analysis and Review

## Executive Definition

Forge is a Go-based Obsidian-oriented static site generation system with an integrated development runtime. It builds publishable static output from a vault of markdown/content files and, in dev mode, adds a request-routing layer for:

- `/api/*` reverse proxying to an external backend (typically `obsidian-agent`)
- `/ops/*` static overlay assets
- optional HTML injection of overlay UI assets

In short, Forge is both:

1. A static site generator (SSG)
2. A local development and interaction gateway around that SSG

## Product Identity: Generator vs Library vs Runtime

From the implementation, Forge is not a classic reusable "library-first" package consumed by third-party Go imports. It is primarily a CLI product (`cmd/forge/main.go`) that orchestrates internal packages.

The internal package structure is modular enough to behave like a composed library architecture, but the ergonomic entrypoint is the CLI command surface (`forge generate`, `forge dev`, `forge serve`, `forge init`, etc.).

## Origin and Positioning

Top-level docs define Forge as a Kiln fork that adds:

- overlay injection
- API reverse proxying
- overlay static serving

That positioning is consistent with runtime code in:

- `internal/server/mux.go` (`NewForgeHandler`)
- `internal/overlay/inject.go`
- `internal/proxy/reverse.go`

## Core Domain Model (as Implemented)

At the center of the build model is `BuildContext` (`internal/builder/builder.go`), which captures all generation/runtime knobs in one explicit value object:

- input/output paths
- mode (`default` / `custom`)
- theme/font/layout options
- URL format options (flat URLs)
- feature toggles (TOC/local graph/backlinks)
- locale/accent options
- logger

This is a strong architectural marker: Forge currently treats configuration as explicit context passed through build functions, rather than hidden global mutable state.

## Modes of Operation

Forge exposes two generation modes:

- `default` mode:
  - markdown-centric, Obsidian conventions first
  - built-in rendering pipeline with notes/tags/folders/canvas/graph/search output
- `custom` mode:
  - collection + layout driven
  - config files, template functions, field validation, richer content-model control

The mode split is explicit in `builder.Build(...)` and `builder.IncrementalBuild(...)`.

## Architectural Boundaries

### Included in Forge

- Vault scan and metadata extraction
- Markdown rendering/transforms
- Static asset and page generation
- Local static server with clean URL behavior
- Dev watcher and incremental rebuild
- Overlay injection/static route handling
- API reverse proxy for `/api/*`

### Explicitly Outside Forge (Current Runtime)

`internal/ops/README.md` marks in-process ops runtime as deprecated for active Forge wiring. Operational mutation logic is expected to live in external agent/backend services.

This means Forge is intentionally becoming a boundary component between:

- content generation and web serving (inside Forge)
- mutation/orchestration logic (outside Forge, proxied)

## Analysis: Why This Identity Makes Sense

1. It keeps the SSG deterministic and file-based.
2. It decouples interactive write operations from static generation internals.
3. It supports "plain SSG only" and "full interactive stack" without forking codebases.
4. It matches modern local-dev architecture patterns (frontend shell + backend API service).

## Review: Strengths

1. Clear composition:
   - CLI layer -> build/runtime services -> package-specialized modules
2. Explicit configuration passing (`BuildContext`) reduces hidden coupling.
3. Dev/runtime extensions are optional and path-scoped (`/api`, `/ops`, inject flag).
4. Backward-compatible enough to run as a straightforward static generator when needed.

## Review: Risks and Ambiguities

1. The term "library" can mislead:
   - operationally this is CLI-first software
2. There are still legacy traces/docs from older runtime patterns (`internal/ops` remains in tree).
3. Setup complexity depends heavily on whether user needs:
   - static publishing only
   - or mutation pipeline with agent/backend integration

## Bottom-Line Characterization

Forge is best understood as:

- a production-minded Obsidian SSG engine
- wrapped by a development gateway that can proxy and inject operational UI/runtime integrations

It is not merely a markdown converter and not merely a reverse proxy. It is a layered system designed to keep static-site generation at the core while enabling interactive editing workflows through explicit external integration points.

