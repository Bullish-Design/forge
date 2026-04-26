# CONTEXT

## What Was Reviewed

- Primary architecture brief:
  - `.scratch/projects/06-forge-architecture-refactor/forge-architecture-refactor.md`
- Existing analysis/review docs under:
  - `.scratch/projects/06-forge-architecture-refactor/`
- Forge code paths:
  - `internal/cli/dev.go`
  - `internal/server/mux.go`
  - `internal/proxy/reverse.go`
  - `internal/ops/*` (handler, tools, resolve, lock, jj)
  - `internal/watch/*`
  - `static/ops.js`, `static/ops.css`
- Dependency libraries:
  - `/home/andrew/Documents/Projects/obsidian-agent` (source + tests + config)
  - `/home/andrew/Documents/Projects/obsidian-ops` (source + tests + server)

## Key Facts Confirmed

- Forge still wires in-process Go ops backend by default (`APIHandler: opsHandler`).
- Forge UI currently sends `POST /api/apply` payload:
  - `{ instruction, current_url_path }`
- `obsidian-agent` currently accepts:
  - `{ instruction, current_file }`
  - and rejects `current_url_path` as extra field (422).
- `obsidian-ops` already provides:
  - sandboxed vault IO
  - deep-merge frontmatter updates
  - heading/block patch operations
  - JJ commit/undo wrappers
  - optional FastAPI server

## Validation Performed

- `obsidian-agent` test suite:
  - `122 passed in 26.36s`
- `obsidian-ops` test suite:
  - passed with ~96% coverage

## Latest Update

- Final architecture decisions were confirmed:
  - URL-to-file ownership stays in Forge.
  - v1 deployment topology is two-process (`forge` + `obsidian-agent`).
- Created and finalized:
  - `ARCHITECTURE_REFACTOR_PLAN.md`
  - `ARCHITECTURE_REFACTOR_GUIDE.md`
- The guide was written using the large-document process from `CRITICAL_RULES.md`:
  - table of contents saved first
  - sections appended in order
