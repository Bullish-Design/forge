# OBSIDIAN_AGENT_EXPANSION_IMPLEMENTATION_GUIDE.md

## Audience

This guide is written for an engineer implementing **obsidian-agent**
(FastAPI backend) changes described in `FORGE_EXPANSION_CONCEPT.md`.

It covers route structure, scoped agent contract, and vault/agent APIs.
obsidian-ops library primitives are covered separately in:
`OBSIDIAN_OPS_EXPANSION_IMPLEMENTATION_GUIDE.md`.

## Ground rules

1. obsidian-agent is the single HTTP backend Forge proxies to.
2. All filesystem writes must flow through `obsidian_ops.Vault`.
3. Keep legacy `/api/apply` and `/api/undo` behavior available during migration.
4. Implement phases in order; each phase has an explicit test gate.

## Prerequisites

- obsidian-agent checked out locally with editable install.
- Compatible obsidian-ops version containing required Vault primitives.
- Python 3.12+.
- Scratch vault with `jj git init`.
- Reachable LLM backend for e2e tests.

---

# Phase 1 — Restructure and `/api/vault/*` foundations

Goal: Introduce route-group architecture and deterministic file APIs.

## Step 1.1 — Split routers into `routes/` package

**Files.**
- `obsidian_agent/routes/agent_routes.py`
- `obsidian_agent/routes/vault_routes.py`
- `obsidian_agent/routes/__init__.py`
- `obsidian_agent/app.py`

**Deliverables.**
- Existing agent routes preserved in `agent_routes.py`.
- New `vault_router` mounted at `/api/vault`.
- Shared app state wiring for `Vault` access.

## Step 1.2 — `web_paths.py` URL/path resolver

**Files.**
- `obsidian_agent/web_paths.py` (new)

**Deliverables.**
- URL-to-vault-path conversion helper for route and scope consumers.
- Deterministic handling for trailing slash and absolute URLs.

## Step 1.3 — `GET/PUT /api/vault/files`

**Files.**
- `obsidian_agent/routes/vault_routes.py`

**Deliverables.**
- Read endpoint supporting `path` or `url`.
- Write endpoint with optimistic concurrency via `expected_sha256`.
- 409 response includes current server hash when stale.

## Step 1.4 — `POST /api/vault/undo`

**Files.**
- `obsidian_agent/routes/vault_routes.py`

**Deliverables.**
- Dedicated deterministic undo route mapped to vault undo behavior.

## Step 1.5 — Legacy alias compatibility

**Files.**
- `obsidian_agent/app.py`

**Deliverables.**
- Keep `/api/apply` and `/api/undo` aliases functional during migration.
- Add deprecation logging for legacy route usage.

## Step 1.6 — Phase 1 exit gate

- Full obsidian-agent tests pass.
- `/api/vault/files` editor workflow works end-to-end with Forge Phase 1.

---

# Phase 2 — Scoped agent contract + structure/anchor APIs

Goal: Backend support for precise scope-targeted editing.

## Step 2.1 — `EditScope` discriminated union

**Files.**
- `obsidian_agent/scope.py` (new)

**Deliverables.**
- `FileScope`, `HeadingScope`, `BlockScope`, `SelectionScope`, `MultiScope`.
- Pydantic discriminated union for request validation.

## Step 2.2 — Interface registry

**Files.**
- `obsidian_agent/interfaces/__init__.py`
- `obsidian_agent/interfaces/command.py`
- `obsidian_agent/interfaces/forge_web.py`

**Deliverables.**
- Registry-based interface selection.
- Scope-specific tool allowlists for `forge_web`.

## Step 2.3 — Extend `ApplyRequest` and dispatch

**Files.**
- `obsidian_agent/models.py`
- `obsidian_agent/routes/agent_routes.py`
- `obsidian_agent/agent.py`

**Deliverables.**
- `interface_id`, `scope`, `intent`, `allowed_write_scope` contract.
- `/api/agent/apply` route.
- Legacy payload shim for `/api/apply`.

## Step 2.4 — `GET /api/vault/files/structure`

**Files.**
- `obsidian_agent/routes/vault_routes.py`

**Deliverables.**
- Route wrapping `Vault.list_structure`.

## Step 2.5 — `POST /api/vault/files/anchors`

**Files.**
- `obsidian_agent/routes/vault_routes.py`

**Deliverables.**
- Route wrapping `Vault.ensure_block_id`.

## Step 2.6 — Phase 2 exit gate

- Scoped tool exposure enforced by tests.
- End-to-end scope editing from Forge Phase 2 works.
- Block scope changes remain localized in diff output.

---

# Phase 3 — Template routes

Goal: Deterministic new-page creation APIs.

## Step 3.1 — `GET /api/vault/pages/templates`

**Files.**
- `obsidian_agent/routes/vault_routes.py`

**Deliverables.**
- List template metadata from vault registry.

## Step 3.2 — `POST /api/vault/pages`

**Files.**
- `obsidian_agent/routes/vault_routes.py`
- `obsidian_agent/web_paths.py` (path-to-url helper)

**Deliverables.**
- Create page from template with validation/error mapping.
- Return rendered URL for frontend navigation.

## Step 3.3 — Default template seed set (optional bootstrap)

**Files.**
- `obsidian_agent/_default_templates/` (package data)

**Deliverables.**
- Optional one-shot seed when vault template dir is empty.

## Step 3.4 — Phase 3 exit gate

- Template routes pass tests and e2e creation flow.
- No regressions in Phase 1/2 behavior.

---

# Phase 4 — Polish

## Step 4.1 — `create_from_template` as LLM tool

- Add deterministic creation tool in allowed interface contexts.

## Step 4.2 — Rate-limit deterministic routes

- Add lightweight per-route token bucket.

## Step 4.3 — Structured request logging

- Route/status/duration/scope/interface structured logs.

---

# obsidian-agent test matrix

| Gate | Command |
|------|---------|
| Unit | `pytest -v` |
| Type check | `mypy src/obsidian_agent` |
| Lint | `ruff check src tests` |
| Contract | `pytest tests/contract -v` |
| End-to-end | `scripts/e2e.sh` |

---

# Rollout sequence summary

1. Complete obsidian-ops Phase 0 first.
2. Complete obsidian-agent Phase 1.
3. Integrate with Forge Phase 1.
4. Continue in lockstep through Phases 2 and 3.
5. Treat Phase 4 as polish/optional hardening.

Each phase remains independently deployable.
