# OBSIDIAN_OPS_EXPANSION_IMPLEMENTATION_GUIDE.md

## Audience

This guide is written for an engineer implementing the **obsidian-ops**
library changes described in `FORGE_EXPANSION_CONCEPT.md`.

It covers only library-level functionality in obsidian-ops (no FastAPI
route wiring).

## Ground rules

1. obsidian-ops remains an importable library.
2. Do not add FastAPI/uvicorn HTTP wiring to core package modules.
3. Every write operation must go through existing mutation lock and sandboxing.
4. Keep primitives composable so obsidian-agent routes can wrap them directly.

## Prerequisites

- obsidian-ops checked out with editable install.
- Python 3.12+.
- A scratch vault fixture with `jj git init`.

---

# Phase 0 — obsidian-ops primitives

Goal: Add the `Vault` methods needed by expanded backend APIs.

## Step 0.1 — `StructureView` model and markdown parser

**Files.**
- `obsidian_ops/structure.py` (new)
- `obsidian_ops/__init__.py` (exports)
- `obsidian_ops/vault.py` (`list_structure` wrapper)

**Deliverables.**
- `Heading`, `Block`, `StructureView` models.
- Deterministic heading-range parsing.
- Block-id (`^id`) extraction and range derivation.
- `sha256` hash in structure output.

**Tests.**
- Mixed heading levels produce correct section ranges.
- Multi-line paragraph ending with `^block` reports correct line span.
- Empty file returns valid empty structure + hash.
- Sandbox escape path fails.

## Step 0.2 — `ensure_block_id` primitive

**Files.**
- `obsidian_ops/anchors.py` (new)
- `obsidian_ops/vault.py` (`ensure_block_id`)
- `obsidian_ops/__init__.py` (exports)

**Deliverables.**
- `EnsureBlockResult` model.
- Idempotent ensure behavior:
  - Reuses existing block id if target already anchored.
  - Appends a generated `^forge-xxxxxx` anchor otherwise.
- Lock-protected write path.

**Tests.**
- Existing anchor returns `created=False` and original id.
- New anchor path returns `created=True` and writes id to file.
- Concurrent ensures on same range converge on one anchor.
- Sandbox escape fails.

## Step 0.3 — Template registry and `create_from_template`

**Files.**
- `obsidian_ops/templates.py` (new)
- `obsidian_ops/vault.py` (`list_templates`, `create_from_template`)
- `obsidian_ops/__init__.py` (exports)

**Deliverables.**
- Vault template registry (`<vault>/.forge/templates/*.yaml`).
- Template field metadata and listing support.
- Rendering with allowed expressions:
  - `{{ today }}`
  - `{{ now }}`
  - `{{ slug(field) }}`
  - `{{ field }}`
- Safe path rendering + sandbox enforcement.
- Create + commit flow for generated pages.

**Tests.**
- Template discovery/listing works from fixture files.
- Valid create renders expected path/body.
- Missing required field fails.
- Duplicate path fails.
- Path escape fails.
- Jujutsu commit created on successful create.

## Step 0.4 — Phase 0 exit gate

- `pytest obsidian-ops/tests/ -v` passes.
- Coverage on new modules is high (target ≥ 90%).
- `Vault` exports include `list_structure`, `ensure_block_id`,
  `list_templates`, `create_from_template`.

---

# obsidian-ops test matrix

| Gate | Command |
|------|---------|
| Unit + integration | `pytest -v` |
| Coverage | `pytest --cov=obsidian_ops --cov-fail-under=90` |
| Type check | `mypy src/obsidian_ops` |
| Lint | `ruff check src tests` |

---

# Hand-off to obsidian-agent

obsidian-agent phase work depends on these primitives:

- `Vault.list_structure`
- `Vault.ensure_block_id`
- `Vault.list_templates`
- `Vault.create_from_template`

Once these ship, continue with
`OBSIDIAN_AGENT_EXPANSION_IMPLEMENTATION_GUIDE.md`.
