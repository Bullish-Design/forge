# Project 20: Forge v2 Demo Review

Date: 2026-04-26
Scope: Thorough review of `demo/` directory — architecture, code quality, upstream boundary analysis, and recommendations.

---

## Executive Summary

The demo is **well-built and functional**. It provides two modes (deterministic + vLLM-backed), validates the full data flow (vault edit → kiln rebuild → webhook → overlay SSE → browser), and includes both automated validation and an interactive walkthrough. The M3 orchestrator (`forge_cli`) is also implemented alongside the demo — `forge dev`, `forge generate`, `forge serve`, and `forge init` all exist with tests.

The primary concern is **overlay asset ownership**: `demo/overlay/ops.js` and `demo/overlay/ops.css` are demo-specific UI files and do NOT duplicate upstream `forge-overlay` assets. However, the current split raises questions about where production overlay assets should live long-term.

---

## What Was Reviewed

| Path | Description |
|---|---|
| `demo/README.md` | Demo documentation |
| `demo/DEMO_SCRIPT.md` | 7-step operator talk track |
| `demo/overlay/ops.js` (80 lines) | Demo UI panel — SSE counter, apply/undo buttons, output pane |
| `demo/overlay/ops.css` (87 lines) | Dark-theme panel styling |
| `demo/tools/dummy_api_server.py` (178 lines) | Deterministic apply/undo API |
| `demo/tools/vllm_api_server.py` (321 lines) | Real vLLM-backed API adapter |
| `demo/scripts/common.sh` (189 lines) | Shared bash utilities |
| `demo/scripts/setup.sh` (35 lines) | Runtime initialization |
| `demo/scripts/start_stack.sh` (96 lines) | Process boot sequence |
| `demo/scripts/start_stack_free_explore.py` (247 lines) | vLLM variant launcher |
| `demo/scripts/run_demo.py` (317 lines) | Interactive 7-step walkthrough |
| `demo/scripts/run_free_explore.py` (94 lines) | Free-explore launcher |
| `demo/scripts/validate_full_stack.sh` (130 lines) | Automated assertion suite |
| `demo/scripts/cleanup.sh` (19 lines) | Process teardown |
| `demo/vault-template/` | 7 markdown files + 1 canvas + 1 SVG |
| `src/forge_cli/` | M3 orchestrator (config, processes, commands) |
| `tests/` | 10 unit tests + 1 integration test harness |

---

## Architecture Assessment

### Data Flow (Correct)

```
vault edit → kiln fsnotify → incremental rebuild
         → POST /internal/rebuild (webhook)
         → forge-overlay SSE broadcast
         → browser EventSource → page reload

browser → POST /api/agent/apply → overlay proxy → backend API
       → backend writes vault file
       → kiln detects change → rebuild cycle repeats
```

The demo proves this full loop with both deterministic and real-LLM backends.

### Process Startup Order (Correct)

1. Backend API (dummy or vLLM) on `:18081` — health-gated
2. `forge-overlay` on `:18080` — HTTP-gated
3. `kiln dev --no-serve --on-rebuild` — log-pattern-gated

This matches the M3 plan requirement: overlay must listen before kiln fires its first webhook.

### Shutdown (Correct)

Reverse-order SIGTERM with fallback to SIGKILL after 10s timeout.

---

## Overlay Asset Ownership Analysis

This was the specific concern raised. Here's the breakdown:

### What `forge-overlay` provides

`forge-overlay` is a **generic injection server**. It:
- Injects `<link href="/ops/ops.css">` and `<script src="/ops/ops.js">` before `</head>` in every HTML response
- Serves whatever files are in `--overlay-dir` at `/ops/{path}`
- Does NOT bundle any default overlay assets

The upstream `forge-overlay/demo/overlay/` contains minimal example files:
- `ops.js` (13 lines): SSE listener that auto-reloads on `{"type": "rebuilt"}`
- `ops.css` (13 lines): Tiny green status indicator

### What `forge/demo/overlay/` provides

The demo overlay is a **rich interactive UI panel**:
- `ops.js` (80 lines): Creates a floating aside with SSE counter, textarea prompt, apply/undo/health buttons, JSON output pane
- `ops.css` (87 lines): Full dark-theme panel with grid layout, hover effects, scrollable output

### Verdict: NOT a duplication problem

The two overlay directories serve completely different purposes:

| Aspect | `forge-overlay/demo/overlay/` | `forge/demo/overlay/` |
|---|---|---|
| Purpose | Minimal infrastructure example | Rich demo UI |
| ops.js | 13 lines — auto-reload on SSE | 80 lines — interactive panel with API calls |
| ops.css | 13 lines — tiny status badge | 87 lines — full panel styling |
| SSE handling | Triggers `location.reload()` | Increments counter, shows event data |
| API calls | None | Health, apply, undo |
| Hardcoded paths | None | `projects/forge-v2.md` |

**These files should NOT be moved upstream.** They are demo-specific, hardcode demo vault paths, and implement demo-only UI. The upstream overlay assets should remain minimal (reload-on-rebuild behavior).

### Longer-term question

In production, what ships as the default overlay assets? Three options:

1. **forge-overlay ships minimal defaults** (current: reload + indicator) and forge orchestrator provides richer UI via `--overlay-dir`. This is the current architecture and it works.
2. **forge-overlay ships a richer default UI** that includes the interactive panel. This would mean the demo overlay migrates upstream eventually, but stripped of hardcoded paths.
3. **forge repo ships production overlay assets** in a `static/` directory alongside the orchestrator. The demo overlay is a preview of this.

Option 1 (current) is fine for now. The decision can be deferred until production UI requirements are clearer.

---

## Code Quality Assessment

### Strengths

1. **Deterministic demo is genuinely useful.** The dummy API provides reproducible apply/undo without any external dependencies — ideal for CI and offline demos.

2. **Validation script is thorough.** `validate_full_stack.sh` asserts 6 concrete behaviors: process flags, HTML injection, API proxy, webhook delivery, apply, and undo.

3. **Clean separation of concerns.** Shell scripts handle process lifecycle, Python handles API logic, overlay handles browser UI. No leaky abstractions.

4. **vLLM adapter is robust.** Handles multiple response formats, auto-detects models, truncates large files, has timeout handling.

5. **M3 orchestrator is implemented.** `forge_cli` with config, process manager, and 4 commands. 10 unit tests covering config loading, command dispatch, process ordering, and init scaffolding.

6. **Error handling in scripts.** `cleanup_partial()` trap on ERR, PID tracking, graceful shutdown with SIGKILL fallback.

### Issues

#### Medium Priority

1. **`assert_json_expr()` uses `eval()`.** (`common.sh:184`)
   - Evaluates arbitrary Python expressions from shell arguments.
   - In this context (local demo scripts) the risk is minimal, but it's a pattern worth noting.
   - Consider replacing with `jq` expressions for standard JSON assertions.

2. **Hardcoded absolute paths in `common.sh`.** (`common.sh:25-31`)
   - `FORGE_OVERLAY_PROJECT_DIR` defaults to `/home/andrew/Documents/Projects/forge-overlay`
   - `KILN_BIN` defaults to `/home/andrew/Documents/Projects/kiln-fork/kiln`
   - These are fine for the developer workstation but would break for any other user. Document as known limitation or source from a shared config.

3. **`demo/overlay/ops.js` hardcodes target file.** (line 71)
   - `current_file: "projects/forge-v2.md"` is baked into the apply button handler.
   - For the demo this is correct. For production, the overlay UI would need to resolve the current page.

4. **`demo/overlay/ops.js` uses `/api/undo` (legacy alias).** (line 77)
   - Apply uses the canonical `/api/agent/apply`, but undo uses deprecated `/api/undo`.
   - Should be `/api/agent/undo` for consistency.

#### Low Priority

5. **`start_stack_free_explore.py` reimplements process management in Python** instead of reusing `start_stack.sh` with env var overrides.
   - 247 lines of Python that largely duplicates the shell script's logic.
   - Could be simplified to: set `DEMO_BACKEND=vllm` env var and let `start_stack.sh` branch on it.

6. **No SSE auto-reload in demo overlay.**
   - The demo `ops.js` increments a counter on SSE events but doesn't auto-reload the page.
   - The upstream minimal `ops.js` does auto-reload. The demo panel should probably also trigger reload (or offer a button for it).

7. **`run_demo.py` is 317 lines** for a 7-step walkthrough.
   - Functional but verbose. The polling logic could be extracted into shared helpers to reduce duplication across steps 3, 5, and 6.

8. **`vllm_api_server.py` uses `http.server.HTTPServer`** (stdlib, single-threaded).
   - Fine for demo, but will block on long vLLM completions. A concurrent server (e.g., `ThreadingHTTPServer`) would be more robust for the free-explore mode.

---

## M3 Orchestrator Status (Bonus Finding)

The M3 orchestrator implementation exists and appears solid:

| Component | File | Status |
|---|---|---|
| Config model | `src/forge_cli/config.py` (129 lines) | Pydantic + YAML + env overrides |
| Process manager | `src/forge_cli/processes.py` (197 lines) | Start/stop with health gates |
| Commands | `src/forge_cli/commands.py` (149 lines) | dev, generate, serve, init |
| Entry point | `src/forge_cli/__main__.py` (11 lines) | Typer CLI |
| Demo wrappers | `src/forge_cli/demo_entrypoints.py` (51 lines) | Script dispatchers |
| Tests | `tests/test_config.py` + `tests/test_commands.py` | 10 unit tests |
| Integration | `tests/test_demo_harness.py` | Opt-in via `FORGE_RUN_DEMO_VALIDATION=1` |

This means **M3 is substantially implemented** — not "not started" as the Project 18 status review claims. The status review should be updated.

---

## Vault Template Assessment

The vault template is well-designed for demonstrating kiln capabilities:

- **index.md**: Tables, code fences, math, wikilinks, embeds, tags, task lists, footnotes, SVG
- **projects/forge-v2.md**: Primary mutation target with callouts and cross-references
- **references/kiln-capabilities.md**: Feature-to-artifact mapping table
- **experiments/live-reload.md**: Minimal file for watch-mode testing
- **daily/2026-04-26.md**: Daily note format
- **canvas/roadmap.canvas**: Obsidian canvas JSON

Good coverage of kiln rendering features without being artificially complex.

---

## Recommendations

### Immediate (before declaring demo complete)

1. Fix the `/api/undo` → `/api/agent/undo` inconsistency in `demo/overlay/ops.js`.
2. Update Project 18 status review to reflect that M3 is now substantially implemented.

### Short-term

3. Add page auto-reload behavior to demo overlay (on SSE rebuild event), or at minimum a "Reload" button.
4. Consider consolidating `start_stack_free_explore.py` into `start_stack.sh` with a backend-type flag.

### Deferred

5. Decide on production overlay asset ownership (forge repo `static/` vs forge-overlay defaults).
6. Replace `eval()` in `assert_json_expr()` with `jq` if demo scripts will be used in CI.
7. Address hardcoded developer paths if the demo needs to be portable.

---

## Final Assessment

The demo successfully validates the v2 architecture end-to-end. The overlay files in `demo/overlay/` are correctly placed — they are demo-specific UI, not duplicates of upstream forge-overlay assets. The forge-overlay design (external `--overlay-dir`) is the right abstraction; it keeps the overlay server generic and lets consumers (like this demo, or the future production UI) provide their own browser-side assets.

The biggest update to project status: **M3 is no longer "not started"** — the orchestrator exists with config, process management, all four commands, and tests. Combined with this demo, the project is much closer to M4 (end-to-end validation) than previously documented.
