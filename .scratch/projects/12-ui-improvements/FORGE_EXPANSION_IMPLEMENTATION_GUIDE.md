# FORGE_EXPANSION_IMPLEMENTATION_GUIDE.md

## Audience

This document is for engineers implementing Forge-side changes from
`FORGE_EXPANSION_CONCEPT.md`.

Backend dependencies are documented in:

- `OBSIDIAN_OPS_EXPANSION_IMPLEMENTATION_GUIDE.md`
- `OBSIDIAN_AGENT_EXPANSION_IMPLEMENTATION_GUIDE.md`

This guide is an expanded execution manual with concrete code examples,
file-by-file change plans, and verification gates.

## Table Of Contents

1. Scope And Non-Goals
   - What this guide includes, and what belongs in backend repos.
2. Delivery Strategy
   - Branching, rollout, and release slices.
3. Prerequisites And Baseline Checks
   - Local environment setup and mandatory green baseline.
4. Phase 0 Overview (Overlay Modularization)
   - What ships, what must remain behavior-compatible.
5. Step 0.1 Meta Tag Contract Expansion
   - Concrete templ changes and tests.
6. Step 0.2 Bundler Toolchain Setup
   - `package.json`, lockfile, and command expectations.
7. Step 0.3 Overlay Module Skeleton
   - Exact folder structure and starter modules.
8. Step 0.4 Port Existing Command Modal
   - Migrating old `ops.js` logic into modules.
9. Step 0.5 Bundle Drift CI Gate
   - Local and CI guardrails to keep generated bundle in sync.
10. Step 0.6 Debug Logging Toggle
   - Meta-driven debug logging and defaults.
11. Phase 1 Overview (Editor Mode)
   - Dependencies on backend `/api/vault/files`.
12. Step 1.1 API Wrappers For Source Editing
   - New `api.js` calls and tests.
13. Step 1.2 CodeMirror Integration
   - Dependency and import strategy.
14. Step 1.3 Full-Screen Editor Mode
   - UI shell, mode lifecycle, conflict handling.
15. Step 1.4 FAB Wiring For Editor Entry
   - Loading and transitions from current UI.
16. Step 1.5 Save Feedback And Reload Flow
   - Reload toast and state consistency.
17. Step 1.6 Phase 1 Exit Gate
   - Required test matrix and manual checks.
18. Phase 2 Overview (Scope Targeting)
   - Dependencies on structure/anchor/scoped apply APIs.
19. Step 2.1 Scoped API Extensions
   - `getStructure`, `postEnsureAnchor`, scoped apply.
20. Step 2.2 Scope Mode And DOM Mapping
   - Non-destructive targeting chips and sheet actions.
21. Step 2.3 Pinned Scope Bar
   - Multi-select and summarize UI behavior.
22. Step 2.4 Command Mode Scope Wiring
   - Command payload and route selection.
23. Step 2.5 Anchor Ensure UX
   - Upgrade selection scope to block scope.
24. Step 2.6 Phase 2 Exit Gate
   - Correctness, containment, and regression criteria.
25. Phase 3 Overview (Template-Based Creation)
   - Dependencies on templates and page creation routes.
26. Step 3.1 Template API Wrappers
   - Fetching template metadata.
27. Step 3.2 New Page Mode
   - Dynamic forms and create flow.
28. Step 3.3 Contextual Quick Create
   - Passing source-page and selection context.
29. Step 3.4 Phase 3 Exit Gate
   - Functional and regression checks.
30. Phase 4 Optional Polish
   - SSE rebuild events, subscriptions, draft restore.
31. Step 4.1 SSE Broker In Forge
   - Server-side event endpoint and publish points.
32. Step 4.2 Overlay Event Subscription
   - EventSource wiring and UX rules.
33. Step 4.3 Editor Draft Autosave
   - LocalStorage keying and restore prompt.
34. Global Test Matrix
   - Required commands at each phase.
35. Troubleshooting Playbook
   - Common failures and fixes.
36. Suggested Commit Plan
   - One commit per step, safe rollback points.
37. Definition Of Done
   - What must be true before merge.

## 1) Scope And Non-Goals

### In scope (Forge repo only)

- Template metadata emission in HTML (`shared.templ` path context tags).
- Overlay frontend modularization (`static/src/**`) and bundled output (`static/ops.js`).
- Overlay interaction modes:
  - command mode
  - editor mode
  - scope mode
  - new-page mode
- Optional Forge server polish (`/ops/events` and watcher event fan-out).
- CI gates for bundle drift and frontend unit checks.

### Out of scope

- New backend business logic in obsidian-agent or obsidian-ops.
- Direct filesystem mutations from Forge handlers.
- Any new mutation endpoint under Forge Go APIs.

### Contract boundaries

- Forge continues to proxy `/api/*` to backend.
- Overlay must tolerate backend route unavailability and show safe errors.
- Existing `/api/apply` and `/api/undo` behavior remains compatible during migration.

## 2) Delivery Strategy

### Branching

- Branch from latest `main`.
- Use short-lived feature branch:
  - `feature/forge-expansion-phase0`
  - then merge, then phase1 branch, etc.

### Release slices

Each phase is independently releasable.

- Phase 0: no user-facing behavior change.
- Phase 1: editor mode ships.
- Phase 2: scoped targeting ships.
- Phase 3: template creation ships.
- Phase 4: optional UX hardening.

### Recommended commit cadence

- 1 commit per numbered step.
- Keep generated `static/ops.js` in the same commit as source changes.
- Keep `templ` generated files in same commit as template source changes.

## 3) Prerequisites And Baseline Checks

Run these before writing code:

```bash
go build ./...
go test ./...
go vet ./...
```

Install required tools:

```bash
go install github.com/a-h/templ/cmd/templ@latest
npm ci
```

Verify backend reachability (adjust host/port):

```bash
curl -fsS http://127.0.0.1:8081/api/health
```

If this fails, do not start Phase 1+ work.

## 4) Phase 0 Overview (Overlay Modularization)

### Objective

Replace single-file hand-edited `static/ops.js` source with modular source in
`static/src/**` while still serving a committed bundled `static/ops.js` file.

### Must-hold invariants

- Existing command modal continues to work after migration.
- `forge dev` still injects overlay assets the same way.
- No backend contract changes required for Phase 0.

---

## 5) Step 0.1 Meta Tag Contract Expansion

### Goal

Emit page-level context tags so frontend can resolve path/url/site state without
reverse engineering URLs in JS.

### Files

- `internal/templates/shared.templ`
- `internal/templates/shared_templ.go` (generated)
- `internal/templates/shared_templ_test.go` (new or expanded)

### Implementation

#### 0.1.a Add helper function

In `internal/templates/shared.templ` helpers section:

```go
func flatURLsMeta(v bool) string {
	if v {
		return "true"
	}
	return "false"
}
```

#### 0.1.b Emit new meta tags in page head

Near existing `forge-current-file` tag logic:

```templ
if data.File.RelPath != "" {
	<meta name="forge-current-file" content={ data.File.RelPath }/>
	<meta name="forge-current-url" content={ data.File.WebPath }/>
}
<meta name="forge-site-base-url" content={ data.Site.BaseURL }/>
<meta name="forge-flat-urls" content={ flatURLsMeta(data.Site.FlatURLs) }/>
```

#### 0.1.c Regenerate templ output

```bash
templ generate ./internal/templates
```

### Test implementation

Create or update `internal/templates/shared_templ_test.go`:

```go
package templates

import (
	"strings"
	"testing"
)

func TestSharedHeadIncludesForgeContextMeta(t *testing.T) {
	// Build minimal view model fixture with known values.
	data := fakePageData()
	data.File.RelPath = "Projects/Example.md"
	data.File.WebPath = "/projects/example"
	data.Site.BaseURL = "https://example.com"
	data.Site.FlatURLs = true

	html := renderSharedForTest(t, data)

	mustContainOnce := func(name, content string) {
		t.Helper()
		needle := `<meta name="` + name + `" content="` + content + `"/>`
		if strings.Count(html, needle) != 1 {
			t.Fatalf("expected exactly one %s meta tag", name)
		}
	}

	mustContainOnce("forge-current-file", "Projects/Example.md")
	mustContainOnce("forge-current-url", "/projects/example")
	mustContainOnce("forge-site-base-url", "https://example.com")
	mustContainOnce("forge-flat-urls", "true")
}
```

### Verification commands

```bash
go build ./...
go test ./internal/templates/...
```

### Done criteria

- Four context tags emitted exactly once in rendered page output.
- Generated templ file committed with source change.

---

## 6) Step 0.2 Bundler Toolchain Setup

### Goal

Introduce repeatable bundling from `static/src/main.js` to `static/ops.js`.

### Files

- `package.json`
- `package-lock.json`

### Implementation

Update `package.json` scripts:

```json
{
  "scripts": {
    "build:ops": "esbuild static/src/main.js --bundle --format=iife --target=es2020 --outfile=static/ops.js --legal-comments=none",
    "build:ops:watch": "esbuild static/src/main.js --bundle --format=iife --target=es2020 --outfile=static/ops.js --watch",
    "check:ops": "node ./scripts/check-ops-bundle.mjs",
    "test:ops": "node --test static/src/__tests__/*.test.js"
  },
  "devDependencies": {
    "esbuild": "^0.24.0",
    "prettier": "^3.7.4",
    "prettier-plugin-go-template": "^0.0.15"
  }
}
```

Install:

```bash
npm install
```

### Verification

```bash
npm run build:ops
node_modules/.bin/esbuild --version
```

Expected now:
- `build:ops` fails if `static/src/main.js` does not exist yet.
- esbuild binary resolves correctly.

### Done criteria

- `package.json` and `package-lock.json` committed.
- Tooling is ready for Step 0.3.

## 7) Step 0.3 Overlay Module Skeleton

### Goal

Create stable module boundaries before behavior migration.

### Files to create

```text
static/src/
├── main.js
├── api.js
├── logger.js
├── page-context.js
├── fab.js
├── state.js
├── ui/
│   ├── modal.js
│   ├── sheet.js
│   └── toast.js
└── modes/
    └── command-mode.js
```

### Implementation

#### `static/src/state.js`

```js
export function createState() {
  return {
    mode: "reading", // reading|commanding|editing|scoping|templating|running
    running: false,
    currentFile: null,
    currentUrl: null,
    siteBaseUrl: null,
    flatUrls: false,
    pinnedScopes: [],
  };
}
```

#### `static/src/page-context.js`

```js
function readMeta(name) {
  return (
    document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") ?? null
  );
}

export function readPageContext() {
  return {
    currentFile: readMeta("forge-current-file"),
    currentUrl: readMeta("forge-current-url"),
    siteBaseUrl: readMeta("forge-site-base-url"),
    flatUrls: readMeta("forge-flat-urls") === "true",
  };
}
```

#### `static/src/logger.js`

```js
const DEBUG =
  document.querySelector('meta[name="forge-overlay-debug"]')?.getAttribute("content") ===
  "true";

export function debugLog(level, message, details) {
  if (!DEBUG) return;
  if (details === undefined) {
    console[level](`[ops-ui] ${message}`);
    return;
  }
  console[level](`[ops-ui] ${message}`, details);
}
```

#### `static/src/ui/modal.js`

```js
export function createModalRoot() {
  const root = document.createElement("div");
  root.id = "ops-modal-root";
  root.className = "ops-modal-root";
  return root;
}

export function closeModal(root) {
  if (root && root.parentNode) root.parentNode.removeChild(root);
}
```

#### `static/src/ui/sheet.js`

```js
export function openSheet({ title = "", body = "" }) {
  const root = document.createElement("div");
  root.className = "ops-sheet";
  root.innerHTML = `<div class="ops-sheet-title"></div><div class="ops-sheet-body"></div>`;
  root.querySelector(".ops-sheet-title").textContent = title;
  root.querySelector(".ops-sheet-body").textContent = body;
  document.body.appendChild(root);
  return {
    root,
    close() {
      if (root.parentNode) root.parentNode.removeChild(root);
    },
  };
}
```

#### `static/src/ui/toast.js`

```js
export function showToast(message, { actionLabel, onAction } = {}) {
  const el = document.createElement("div");
  el.className = "ops-toast";
  const text = document.createElement("span");
  text.textContent = message;
  el.appendChild(text);

  if (actionLabel && onAction) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = actionLabel;
    btn.addEventListener("click", onAction);
    el.appendChild(btn);
  }

  document.body.appendChild(el);
  setTimeout(() => {
    if (el.parentNode) el.parentNode.removeChild(el);
  }, 3500);
}
```

#### `static/src/api.js` (stub)

```js
export async function parseApiResponse(resp, context = "api") {
  let payload;
  try {
    payload = await resp.json();
  } catch {
    return { ok: false, error: `${context}: invalid JSON response` };
  }
  if (!resp.ok) {
    const error = payload?.error || payload?.detail || `${context}: request failed`;
    return { ok: false, error };
  }
  return payload;
}

export async function postApply(payload) {
  const resp = await fetch("/api/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseApiResponse(resp, "postApply");
}

export async function postUndo() {
  const resp = await fetch("/api/undo", { method: "POST" });
  return parseApiResponse(resp, "postUndo");
}
```

#### `static/src/modes/command-mode.js` (stub for now)

```js
export function enterCommandMode(state) {
  state.mode = "commanding";
}
```

#### `static/src/fab.js`

```js
import { enterCommandMode } from "./modes/command-mode.js";

export function installFab(state) {
  const btn = document.createElement("button");
  btn.id = "ops-fab";
  btn.type = "button";
  btn.textContent = "+";
  btn.addEventListener("click", () => enterCommandMode(state));
  document.body.appendChild(btn);
}
```

#### `static/src/main.js`

```js
import { createState } from "./state.js";
import { readPageContext } from "./page-context.js";
import { installFab } from "./fab.js";

export function bootOverlay() {
  const state = createState();
  const ctx = readPageContext();
  state.currentFile = ctx.currentFile;
  state.currentUrl = ctx.currentUrl;
  state.siteBaseUrl = ctx.siteBaseUrl;
  state.flatUrls = ctx.flatUrls;
  installFab(state);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootOverlay);
} else {
  bootOverlay();
}
```

### Verification

```bash
npm run build:ops
```

Add minimal bundle check script `scripts/check-ops-bundle.mjs`:

```js
import fs from "node:fs";

const content = fs.readFileSync("static/ops.js", "utf8");
if (!content.includes("bootOverlay")) {
  console.error("expected bootOverlay in static/ops.js");
  process.exit(1);
}
console.log("overlay bundle check passed");
```

Run:

```bash
npm run check:ops
```

---

## 8) Step 0.4 Port Existing Command Modal

### Goal

Move current `static/ops.js` command behavior into modular source with no UX
regression.

### Files

- `static/src/modes/command-mode.js`
- `static/src/fab.js`
- `static/src/api.js`
- `static/src/ui/modal.js`

### Implementation approach

1. Copy existing modal DOM builder from legacy `static/ops.js`.
2. Move fetch and response parse into `api.js`.
3. Keep mode transitions explicit in state.
4. Keep existing button labels and behavior for parity.

### Concrete code (`static/src/modes/command-mode.js`)

```js
import { postApply, postUndo } from "../api.js";
import { createModalRoot, closeModal } from "../ui/modal.js";
import { showToast } from "../ui/toast.js";

export function enterCommandMode(state) {
  if (state.running) return;
  if (state.mode === "commanding") return;

  state.mode = "commanding";

  const root = createModalRoot();
  root.innerHTML = `
    <div class="ops-modal-backdrop"></div>
    <div class="ops-modal-card" role="dialog" aria-modal="true" aria-label="Ask AI">
      <textarea id="ops-instruction" placeholder="Describe the change..."></textarea>
      <div class="ops-actions">
        <button id="ops-cancel" type="button">Cancel</button>
        <button id="ops-undo" type="button">Undo</button>
        <button id="ops-submit" type="button">Apply</button>
      </div>
    </div>
  `;
  document.body.appendChild(root);

  const ta = root.querySelector("#ops-instruction");
  const cancelBtn = root.querySelector("#ops-cancel");
  const undoBtn = root.querySelector("#ops-undo");
  const submitBtn = root.querySelector("#ops-submit");

  function close() {
    closeModal(root);
    state.mode = "reading";
  }

  cancelBtn.addEventListener("click", close);
  root.querySelector(".ops-modal-backdrop").addEventListener("click", close);

  undoBtn.addEventListener("click", async () => {
    if (state.running) return;
    state.running = true;
    undoBtn.disabled = true;
    const res = await postUndo();
    state.running = false;
    undoBtn.disabled = false;
    if (!res.ok) {
      showToast(res.error || "Undo failed");
      return;
    }
    showToast("Undo complete");
    window.location.reload();
  });

  submitBtn.addEventListener("click", async () => {
    const instruction = ta.value.trim();
    if (!instruction) {
      showToast("Instruction is required");
      return;
    }
    if (state.running) return;

    state.running = true;
    submitBtn.disabled = true;
    const res = await postApply({ instruction, current_file: state.currentFile });
    state.running = false;
    submitBtn.disabled = false;

    if (!res.ok) {
      showToast(res.error || "Apply failed");
      return;
    }

    close();
    showToast("Applied. Reloading...");
    window.location.reload();
  });

  setTimeout(() => ta.focus(), 0);
}
```

### API tests (`static/src/__tests__/api.test.js`)

```js
import test from "node:test";
import assert from "node:assert/strict";
import { parseApiResponse } from "../api.js";

test("parseApiResponse handles non-200", async () => {
  const resp = new Response(JSON.stringify({ error: "boom" }), {
    status: 500,
    headers: { "Content-Type": "application/json" },
  });
  const out = await parseApiResponse(resp, "x");
  assert.equal(out.ok, false);
  assert.equal(out.error, "boom");
});

test("parseApiResponse handles success json", async () => {
  const resp = new Response(JSON.stringify({ ok: true, value: 1 }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
  const out = await parseApiResponse(resp, "x");
  assert.equal(out.ok, true);
  assert.equal(out.value, 1);
});
```

### Verification

```bash
npm run build:ops
npm run check:ops
npm run test:ops
go test ./...
```

### Done criteria

- Command modal behavior matches previous UX.
- Bundle builds from modular source only.

## 9) Step 0.5 Bundle Drift CI Gate

### Goal

Fail CI when `static/src/**` and committed `static/ops.js` diverge.

### Files

- `scripts/check-ops-bundle.mjs`
- `.github/workflows/overlay-check.yml`

### Implementation

Replace `scripts/check-ops-bundle.mjs` with deterministic hash comparison:

```js
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { build } from "esbuild";

function sha256(text) {
  return crypto.createHash("sha256").update(text).digest("hex");
}

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ops-bundle-"));
const tmpOut = path.join(tmpDir, "ops.js");

await build({
  entryPoints: ["static/src/main.js"],
  bundle: true,
  format: "iife",
  target: "es2020",
  outfile: tmpOut,
  legalComments: "none",
  logLevel: "silent",
});

const generated = fs.readFileSync(tmpOut, "utf8");
const committed = fs.readFileSync("static/ops.js", "utf8");

const a = sha256(generated);
const b = sha256(committed);
if (a !== b) {
  console.error("static/ops.js is out of date");
  console.error("run: npm run build:ops");
  process.exit(1);
}

console.log("overlay bundle is up to date");
```

Add workflow `.github/workflows/overlay-check.yml`:

```yaml
name: overlay-check
on:
  push:
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - run: npm run check:ops
      - run: npm run test:ops
```

### Verification

```bash
npm run check:ops
```

Expected behavior:
- Passes on synced source/bundle.
- Fails after editing `static/src` without running build.

---

## 10) Step 0.6 Debug Logging Toggle

### Goal

Remove noisy default logging and make it opt-in via meta flag.

### Files

- `static/src/logger.js`
- `internal/templates/shared.templ`

### Implementation

Emit optional debug flag tag from server:

```templ
if data.Site.DebugOverlay {
  <meta name="forge-overlay-debug" content="true"/>
}
```

Note: if no such field exists, add config plumbing in the smallest possible
surface to keep default off.

Use `debugLog` from modules instead of direct `console.*` calls.

### Verification

- Without meta flag: no overlay debug logs.
- With meta flag: logs appear with `[ops-ui]` prefix.

---

## 11) Phase 1 Overview (Editor Mode)

### Objective

Ship deterministic markdown editing with optimistic concurrency:
- fetch source
- edit in full-screen editor
- save via `/api/vault/files`
- recover gracefully on conflicts

### Backend dependencies

- `GET /api/vault/files`
- `PUT /api/vault/files`
- `POST /api/vault/undo`

---

## 12) Step 1.1 API Wrappers For Source Editing

### Files

- `static/src/api.js`

### Implementation

```js
export async function getSource({ path, url }) {
  const q = new URLSearchParams();
  if (path) q.set("path", path);
  else if (url) q.set("url", url);
  else return { ok: false, error: "path or url required" };

  const resp = await fetch(`/api/vault/files?${q.toString()}`);
  return parseApiResponse(resp, "getSource");
}

export async function putSource({ path, content, expectedSha256 }) {
  const body = { path, content };
  if (expectedSha256) body.expected_sha256 = expectedSha256;

  const resp = await fetch("/api/vault/files", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseApiResponse(resp, "putSource");
}

export async function postVaultUndo() {
  const resp = await fetch("/api/vault/undo", { method: "POST" });
  return parseApiResponse(resp, "vaultUndo");
}
```

### Tests

Add tests for query/body shape:

```js
test("getSource query uses path", async () => {
  const seen = [];
  global.fetch = async (url) => {
    seen.push(String(url));
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  await getSource({ path: "Projects/Example.md" });
  assert.match(seen[0], /\/api\/vault\/files\?path=Projects%2FExample\.md/);
});
```

---

## 13) Step 1.2 CodeMirror Integration

### Files

- `package.json`
- `static/src/lib/codemirror.js` (new)

### Install

```bash
npm install --save codemirror @codemirror/lang-markdown @codemirror/state @codemirror/view @codemirror/commands @codemirror/search
```

### Re-export module

```js
export { EditorState } from "@codemirror/state";
export { EditorView, keymap, lineNumbers, highlightActiveLine } from "@codemirror/view";
export { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
export { markdown } from "@codemirror/lang-markdown";
export { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
```

### Verification

```bash
npm run build:ops
npm run check:ops
```

---

## 14) Step 1.3 Full-Screen Editor Mode

### Files

- `static/src/modes/editor-mode.js`
- `static/src/ui/editor-shell.js`
- `static/ops.css`

### `static/src/ui/editor-shell.js`

```js
export function createEditorShell() {
  const root = document.createElement("section");
  root.id = "ops-editor-root";
  root.innerHTML = `
    <header id="ops-editor-toolbar">
      <button id="ops-editor-back" type="button">Back</button>
      <button id="ops-editor-save" type="button">Save</button>
      <button id="ops-editor-undo" type="button">Undo</button>
      <button id="ops-editor-ask" type="button">Ask AI</button>
      <button id="ops-editor-scope" type="button">Scope</button>
      <button id="ops-editor-new" type="button">New</button>
    </header>
    <div id="ops-editor-status"></div>
    <div id="ops-editor-cm"></div>
  `;
  return root;
}
```

### `static/src/modes/editor-mode.js`

```js
import {
  EditorState,
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLine,
  defaultKeymap,
  history,
  historyKeymap,
  markdown,
  searchKeymap,
  highlightSelectionMatches,
} from "../lib/codemirror.js";
import { getSource, putSource, postVaultUndo } from "../api.js";
import { createEditorShell } from "../ui/editor-shell.js";
import { showToast } from "../ui/toast.js";

export async function enterEditorMode(state, ctx) {
  if (state.mode === "editing") return;
  state.mode = "editing";

  const shell = createEditorShell();
  document.body.appendChild(shell);

  const status = shell.querySelector("#ops-editor-status");
  const cmHost = shell.querySelector("#ops-editor-cm");
  const saveBtn = shell.querySelector("#ops-editor-save");
  const backBtn = shell.querySelector("#ops-editor-back");
  const undoBtn = shell.querySelector("#ops-editor-undo");

  const targetPath = ctx.currentFile;
  if (!targetPath) {
    showToast("No source file found for this page");
    teardown();
    return;
  }

  status.textContent = "Loading source...";
  const src = await getSource({ path: targetPath });
  if (!src.ok) {
    showToast(src.error || "Failed to load source");
    teardown();
    return;
  }

  let currentSha = src.sha256;
  let dirty = false;

  const view = new EditorView({
    parent: cmHost,
    state: EditorState.create({
      doc: src.content,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        markdown(),
        history(),
        highlightSelectionMatches(),
        keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap]),
        EditorView.lineWrapping,
        EditorView.updateListener.of((u) => {
          if (u.docChanged) {
            dirty = true;
            status.textContent = "Unsaved changes";
          }
        }),
      ],
    }),
  });

  status.textContent = "Loaded";

  async function onSave() {
    const content = view.state.doc.toString();
    const out = await putSource({ path: targetPath, content, expectedSha256: currentSha });

    if (!out.ok) {
      if (typeof out.error === "object" || String(out.error).includes("stale")) {
        showToast("Conflict detected. Reload or overwrite.");
      } else {
        showToast(out.error || "Save failed");
      }
      return;
    }

    currentSha = out.sha256;
    dirty = false;
    status.textContent = "Saved";
    showToast("Saved", {
      actionLabel: "Reload page",
      onAction: () => window.location.reload(),
    });
  }

  async function onUndo() {
    const out = await postVaultUndo();
    if (!out.ok) {
      showToast(out.error || "Undo failed");
      return;
    }
    showToast("Undo complete", { actionLabel: "Reload", onAction: () => window.location.reload() });
  }

  function teardown() {
    state.mode = "reading";
    if (view && !view.destroyed) view.destroy();
    if (shell.parentNode) shell.parentNode.removeChild(shell);
  }

  saveBtn.addEventListener("click", onSave);
  undoBtn.addEventListener("click", onUndo);
  backBtn.addEventListener("click", () => {
    if (dirty && !window.confirm("Discard unsaved changes?")) return;
    teardown();
  });

  setTimeout(() => view.focus(), 0);
}
```

### CSS (`static/ops.css` additions)

```css
#ops-editor-root {
  position: fixed;
  inset: 0;
  background: var(--ops-bg, #fff);
  z-index: 10002;
  display: flex;
  flex-direction: column;
}

#ops-editor-toolbar {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  position: sticky;
  top: 0;
  background: var(--ops-bg, #fff);
  border-bottom: 1px solid #e2e8f0;
}

#ops-editor-status {
  font-size: 12px;
  color: #64748b;
  padding: 6px 12px;
}

#ops-editor-cm {
  flex: 1;
  min-height: 0;
}

@media (max-width: 640px) {
  #ops-editor-toolbar button {
    min-height: 44px;
    min-width: 44px;
  }
}
```

---

## 15) Step 1.4 FAB Wiring For Editor Entry

### Files

- `static/src/fab.js`
- `static/src/main.js`

### Implementation (`static/src/fab.js`)

```js
import { enterCommandMode } from "./modes/command-mode.js";
import { readPageContext } from "./page-context.js";

export function installFab(state) {
  const wrap = document.createElement("div");
  wrap.id = "ops-fab-wrap";

  const cmd = document.createElement("button");
  cmd.id = "ops-fab";
  cmd.type = "button";
  cmd.textContent = "+";
  cmd.addEventListener("click", () => enterCommandMode(state));

  const edit = document.createElement("button");
  edit.id = "ops-fab-edit";
  edit.type = "button";
  edit.textContent = "Edit";
  edit.addEventListener("click", async () => {
    const { enterEditorMode } = await import("./modes/editor-mode.js");
    await enterEditorMode(state, readPageContext());
  });

  wrap.appendChild(edit);
  wrap.appendChild(cmd);
  document.body.appendChild(wrap);
}
```

---

## 16) Step 1.5 Save Feedback And Reload Flow

### Goal

After successful save, keep editor open, surface reload action, and preserve
new sha hash for subsequent saves.

### Required behavior

- First save success updates local `currentSha`.
- Second save without reload also succeeds.
- Conflict path gives actionable prompt.

### Verification

1. Save once.
2. Edit again.
3. Save again without reload.
4. Confirm no stale conflict.

---

## 17) Step 1.6 Phase 1 Exit Gate

All must pass:

```bash
go test ./...
go vet ./...
npm run build:ops
npm run check:ops
npm run test:ops
```

Manual gates:

- Open page -> Edit -> Save -> Reload works.
- Command modal still works.
- No console errors on desktop/mobile viewport.

## 18) Phase 2 Overview (Scope Targeting)

### Objective

Enable users to target precise note regions (heading/block/selection) for AI
operations, not whole-file mutations.

### Backend dependencies

- `GET /api/vault/files/structure`
- `POST /api/vault/files/anchors`
- `POST /api/agent/apply` with scope-aware contract

---

## 19) Step 2.1 Scoped API Extensions

### Files

- `static/src/api.js`

### Implementation

```js
export async function getStructure({ path }) {
  const q = new URLSearchParams({ path });
  const resp = await fetch(`/api/vault/files/structure?${q.toString()}`);
  return parseApiResponse(resp, "getStructure");
}

export async function postEnsureAnchor({ path, lineStart, lineEnd }) {
  const resp = await fetch("/api/vault/files/anchors", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, line_start: lineStart, line_end: lineEnd }),
  });
  return parseApiResponse(resp, "postEnsureAnchor");
}

export async function postAgentApply({
  instruction,
  interfaceId,
  scope,
  intent,
  allowedWriteScope,
}) {
  const resp = await fetch("/api/agent/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      instruction,
      interface_id: interfaceId,
      scope,
      intent,
      allowed_write_scope: allowedWriteScope,
    }),
  });
  return parseApiResponse(resp, "postAgentApply");
}

// Temporary compatibility alias.
export async function postApply(payload) {
  return postAgentApply({
    instruction: payload.instruction,
    interfaceId: "command",
    scope: null,
    intent: null,
    allowedWriteScope: "unrestricted",
  });
}
```

### Tests

- Request path and body validation for all three methods.

---

## 20) Step 2.2 Scope Mode And DOM Mapping

### Files

- `static/src/modes/scope-mode.js`
- `static/src/targeting/dom-map.js`
- `static/src/ui/sheet.js` (expanded)

### `static/src/targeting/dom-map.js`

```js
function collectTargets(root = document) {
  return Array.from(
    root.querySelectorAll("h1,h2,h3,h4,h5,h6,p,li,blockquote")
  ).filter((el) => !el.closest("#ops-editor-root"));
}

export function mapDomToStructure(structure) {
  const targets = collectTargets();
  const mapped = [];

  // Basic deterministic strategy:
  // headings matched by text, block candidates mapped by order fallback.
  let blockIdx = 0;

  for (const el of targets) {
    const text = (el.textContent || "").trim();
    if (!text) continue;

    if (/^H[1-6]$/.test(el.tagName)) {
      const match = structure.headings.find(
        (h) => h.title === text || h.text.replace(/^#+\s*/, "") === text
      );
      if (match) {
        mapped.push({
          el,
          kind: "heading",
          lineStart: match.line_start,
          lineEnd: match.line_end,
          heading: match.title,
        });
        continue;
      }
    }

    // Fallback block mapping by sequence.
    if (blockIdx < structure.blocks.length) {
      const b = structure.blocks[blockIdx++];
      mapped.push({
        el,
        kind: "block",
        lineStart: b.line_start,
        lineEnd: b.line_end,
        blockId: b.block_id,
      });
    }
  }

  return mapped;
}
```

### `static/src/modes/scope-mode.js` (core skeleton)

```js
import { getStructure, postEnsureAnchor } from "../api.js";
import { mapDomToStructure } from "../targeting/dom-map.js";
import { openSheet } from "../ui/sheet.js";
import { showToast } from "../ui/toast.js";

export async function enterScopeMode(state, ctx) {
  if (!ctx.currentFile) {
    showToast("Scope mode unavailable on this page");
    return;
  }

  const structure = await getStructure({ path: ctx.currentFile });
  if (!structure.ok) {
    // Degrade gracefully.
    return;
  }

  const mapped = mapDomToStructure(structure);
  for (const item of mapped) {
    attachChip(item, state, ctx);
  }
}

function attachChip(item, state, ctx) {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "ops-scope-chip";
  chip.textContent = "...";

  chip.addEventListener("click", () => {
    const sheet = openSheet({ title: "Scope action" });
    const actions = document.createElement("div");
    actions.className = "ops-scope-actions";

    actions.appendChild(actionButton("Pin to scope", () => {
      pinScope(item, state, ctx);
      sheet.close();
    }));

    actions.appendChild(actionButton("Create anchor", async () => {
      const out = await postEnsureAnchor({
        path: ctx.currentFile,
        lineStart: item.lineStart,
        lineEnd: item.lineEnd,
      });
      if (!out.ok) {
        showToast(out.error || "Anchor ensure failed");
      } else {
        showToast(`Anchor ${out.block_id} ${out.created ? "created" : "reused"}`);
      }
      sheet.close();
    }));

    sheet.root.querySelector(".ops-sheet-body").appendChild(actions);
  });

  item.el.style.position = item.el.style.position || "relative";
  chip.style.position = "absolute";
  chip.style.left = "-28px";
  chip.style.top = "0";
  item.el.prepend(chip);
}

function actionButton(label, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function pinScope(item, state, ctx) {
  const scope = item.kind === "heading"
    ? { kind: "heading", path: ctx.currentFile, heading: item.heading }
    : item.blockId
      ? { kind: "block", path: ctx.currentFile, block_id: item.blockId }
      : {
          kind: "selection",
          path: ctx.currentFile,
          text: (item.el.textContent || "").trim(),
          line_start: item.lineStart,
          line_end: item.lineEnd,
        };

  state.pinnedScopes.push(scope);
}
```

---

## 21) Step 2.3 Pinned Scope Bar

### Files

- `static/src/ui/scope-bar.js`
- `static/src/modes/scope-mode.js`

### `static/src/ui/scope-bar.js`

```js
export function renderScopeBar(state, { onAskAI, onClear }) {
  let bar = document.querySelector("#ops-scope-bar");
  if (!state.pinnedScopes.length) {
    if (bar) bar.remove();
    return;
  }

  if (!bar) {
    bar = document.createElement("div");
    bar.id = "ops-scope-bar";
    document.body.appendChild(bar);
  }

  const count = state.pinnedScopes.length;
  bar.innerHTML = "";

  const label = document.createElement("span");
  label.textContent = `${count} scope${count === 1 ? "" : "s"}`;

  const ask = document.createElement("button");
  ask.type = "button";
  ask.textContent = "Ask AI";
  ask.addEventListener("click", onAskAI);

  const clear = document.createElement("button");
  clear.type = "button";
  clear.textContent = "Clear";
  clear.addEventListener("click", onClear);

  bar.append(label, ask, clear);
}
```

### Behavior

- `state.pinnedScopes.length === 0` => hidden.
- 1 scope => send direct scope.
- >1 scopes => send `multi` scope wrapper.

---

## 22) Step 2.4 Command Mode Scope Wiring

### Files

- `static/src/modes/command-mode.js`

### Implementation detail

When command mode is entered from scope mode, attach scope to submit payload:

```js
const scope = state.pendingScope ||
  (state.pinnedScopes.length === 1
    ? state.pinnedScopes[0]
    : state.pinnedScopes.length > 1
      ? { kind: "multi", path: state.currentFile, scopes: state.pinnedScopes }
      : null);

const out = await postAgentApply({
  instruction,
  interfaceId: scope ? "forge_web" : "command",
  scope,
  intent: null,
  allowedWriteScope: scope ? "target_only" : "unrestricted",
});
```

After successful call:
- clear pending scope
- optionally keep pinned scope if user preference is sticky
- reload when backend reports content updated

---

## 23) Step 2.5 Anchor Ensure UX

### Objective

Allow user to convert selection/line-range into durable block anchor.

### UX rule

- If `postEnsureAnchor` returns `created` or existing id, upgrade pinned scope to
  `{ kind: "block", path, block_id }`.

### Implementation snippet

```js
function upgradePinnedScopeToBlock(state, oldScope, blockId) {
  state.pinnedScopes = state.pinnedScopes.map((s) => {
    if (s !== oldScope) return s;
    return { kind: "block", path: s.path, block_id: blockId };
  });
}
```

---

## 24) Step 2.6 Phase 2 Exit Gate

Required:

```bash
go test ./...
go vet ./...
npm run build:ops
npm run check:ops
npm run test:ops
```

Manual:

1. Pin heading, run scoped rewrite, verify only that section changed.
2. Pin paragraph, ensure anchor, run scoped rewrite, verify target accuracy
   remains after unrelated file edits.

## 25) Phase 3 Overview (Template-Based Creation)

### Objective

Provide deterministic page creation from backend templates.

### Backend dependencies

- `GET /api/vault/pages/templates`
- `POST /api/vault/pages`

---

## 26) Step 3.1 Template API Wrappers

### Files

- `static/src/api.js`

### Implementation

```js
export async function getTemplates() {
  const resp = await fetch("/api/vault/pages/templates");
  return parseApiResponse(resp, "getTemplates");
}

export async function createPage({ id, fields, parent }) {
  const resp = await fetch("/api/vault/pages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, fields, parent }),
  });
  return parseApiResponse(resp, "createPage");
}
```

---

## 27) Step 3.2 New Page Mode

### Files

- `static/src/modes/new-page-mode.js`
- `static/src/ui/form.js`

### `static/src/ui/form.js`

```js
export function fieldInput(field) {
  const wrap = document.createElement("label");
  wrap.className = "ops-form-field";

  const title = document.createElement("span");
  title.textContent = field.label || field.name;
  wrap.appendChild(title);

  let input;
  if (field.type === "textarea") {
    input = document.createElement("textarea");
  } else if (field.type === "select") {
    input = document.createElement("select");
    for (const option of field.options || []) {
      const el = document.createElement("option");
      el.value = option.value;
      el.textContent = option.label;
      input.appendChild(el);
    }
  } else {
    input = document.createElement("input");
    input.type = "text";
  }

  input.name = field.name;
  if (field.required) input.required = true;
  if (field.default) input.value = field.default;
  wrap.appendChild(input);

  return { wrap, input };
}
```

### `static/src/modes/new-page-mode.js`

```js
import { getTemplates, createPage } from "../api.js";
import { fieldInput } from "../ui/form.js";
import { showToast } from "../ui/toast.js";

export async function enterNewPageMode(state, ctx) {
  const tpl = await getTemplates();
  if (!tpl.ok) {
    showToast(tpl.error || "Failed to load templates");
    return;
  }

  const root = document.createElement("div");
  root.className = "ops-new-page";
  root.innerHTML = `
    <div class="ops-new-page-card">
      <h2>New page</h2>
      <label>Template <select id="ops-template"></select></label>
      <form id="ops-template-form"></form>
      <div class="ops-actions">
        <button id="ops-new-cancel" type="button">Cancel</button>
        <button id="ops-new-create" type="button">Create</button>
      </div>
    </div>
  `;
  document.body.appendChild(root);

  const select = root.querySelector("#ops-template");
  const form = root.querySelector("#ops-template-form");
  const createBtn = root.querySelector("#ops-new-create");

  for (const t of tpl.templates || []) {
    const opt = document.createElement("option");
    opt.value = t.id;
    opt.textContent = t.label || t.id;
    select.appendChild(opt);
  }

  function renderFields(templateId) {
    const t = (tpl.templates || []).find((x) => x.id === templateId);
    form.innerHTML = "";
    for (const f of t?.fields || []) {
      const { wrap } = fieldInput(f);
      form.appendChild(wrap);
    }
  }

  renderFields(select.value);
  select.addEventListener("change", () => renderFields(select.value));

  createBtn.addEventListener("click", async () => {
    const data = Object.fromEntries(new FormData(form).entries());
    const out = await createPage({
      id: select.value,
      fields: data,
      parent: null,
    });

    if (!out.ok) {
      showToast(out.error || "Create failed");
      return;
    }

    window.location.href = out.url;
  });

  root.querySelector("#ops-new-cancel").addEventListener("click", () => root.remove());
}
```

---

## 28) Step 3.3 Contextual Quick Create

### Goal

Use current scope/page context to pre-seed templates.

### Example integration

When invoking `enterNewPageMode`, pass optional context:

```js
await enterNewPageMode(state, {
  currentFile: state.currentFile,
  selection: state.pendingSelectionText || null,
});
```

Then inject context into create payload fields:

```js
const fields = {
  ...Object.fromEntries(new FormData(form).entries()),
  context_source_page: ctx.currentFile || "",
  context_selection: ctx.selection || "",
};
```

---

## 29) Step 3.4 Phase 3 Exit Gate

- Template picker works with backend metadata.
- Page creation navigates to returned URL.
- Contextual quick-create includes source page and selection context.
- No regressions in command/editor/scope flows.

---

## 30) Phase 4 Optional Polish

These are recommended but not blocking for initial feature rollout.

---

## 31) Step 4.1 SSE Broker In Forge

### Files

- `internal/overlay/events.go` (new)
- `internal/watch/watcher.go` (publish callback)
- `internal/server/mux.go` (route)
- `internal/cli/dev.go` (wiring)

### `internal/overlay/events.go` (example)

```go
package overlay

import (
	"fmt"
	"net/http"
	"sync"
)

type EventBroker struct {
	mu   sync.Mutex
	subs map[chan string]struct{}
}

func NewEventBroker() *EventBroker {
	return &EventBroker{subs: make(map[chan string]struct{})}
}

func (b *EventBroker) Publish(payload string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	for ch := range b.subs {
		select {
		case ch <- payload:
		default:
		}
	}
}

func (b *EventBroker) Handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "stream unsupported", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")

		ch := make(chan string, 8)
		b.mu.Lock()
		b.subs[ch] = struct{}{}
		b.mu.Unlock()

		defer func() {
			b.mu.Lock()
			delete(b.subs, ch)
			b.mu.Unlock()
			close(ch)
		}()

		ctx := r.Context()
		for {
			select {
			case <-ctx.Done():
				return
			case msg := <-ch:
				fmt.Fprintf(w, "data: %s\\n\\n", msg)
				flusher.Flush()
			}
		}
	})
}
```

### Route wiring (mux)

```go
mux.Handle("/ops/events", cfg.OverlayEvents.Handler())
```

### Publish point

After successful build/rebuild:

```go
cfg.OverlayEvents.Publish(`{"type":"rebuilt"}`)
```

---

## 32) Step 4.2 Overlay Event Subscription

### Files

- `static/src/events.js`
- `static/src/main.js`

### Implementation

```js
export function subscribeOpsEvents(onEvent) {
  const es = new EventSource("/ops/events");
  es.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(ev.data));
    } catch {
      // ignore malformed events
    }
  };
  es.onerror = () => {
    // keep default browser reconnect behavior
  };
  return () => es.close();
}
```

In `main.js`:

```js
import { subscribeOpsEvents } from "./events.js";

const stopEvents = subscribeOpsEvents((ev) => {
  if (ev.type !== "rebuilt") return;
  if (state.mode === "reading") {
    window.location.reload();
    return;
  }
  showToast("Vault rebuilt");
});
```

---

## 33) Step 4.3 Editor Draft Autosave

### Files

- `static/src/modes/editor-mode.js`

### Key strategy

- key: `forge:draft:${path}:${sha256}`
- write every 2 seconds while dirty (throttled)
- on load, if draft exists newer than backend `modified_at`, prompt restore

### Snippet

```js
function draftKey(path, sha) {
  return `forge:draft:${path}:${sha}`;
}

function saveDraft(path, sha, content) {
  localStorage.setItem(
    draftKey(path, sha),
    JSON.stringify({ content, ts: Date.now() })
  );
}

function readDraft(path, sha) {
  const raw = localStorage.getItem(draftKey(path, sha));
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
```

---

## 34) Global Test Matrix

Run for every phase before commit:

```bash
go build ./...
go vet ./...
go test ./...
templ generate ./internal/templates && git diff --exit-code
npm run build:ops
npm run check:ops
npm run test:ops
npx prettier --check static/src
```

Recommended e2e smoke:

```bash
demo/run_demo.sh
```

Confirm flows:
- command apply
- editor save
- scoped rewrite
- template page create

---

## 35) Troubleshooting Playbook

### `npm run check:ops` fails

- Cause: `static/src` changed but `static/ops.js` stale.
- Fix: `npm run build:ops` and commit generated file.

### Template tags not visible

- Cause: templ generated file not updated.
- Fix: `templ generate ./internal/templates`.

### Editor save always conflicts

- Cause: backend hash mismatch due stale editor copy.
- Fix: reload source in editor and reapply, verify backend route returns `sha256`.

### Scoped chips not appearing

- Cause: structure API failed or mapping mismatch.
- Fix: inspect `/api/vault/files/structure` response and DOM text matching logic.

---

## 36) Suggested Commit Plan

1. `phase0-step01-meta-tags`
2. `phase0-step02-bundler`
3. `phase0-step03-module-skeleton`
4. `phase0-step04-command-mode-port`
5. `phase0-step05-overlay-check-ci`
6. `phase0-step06-debug-flag`
7. `phase1-step11-api-wrappers`
8. `phase1-step12-codemirror`
9. `phase1-step13-editor-mode`
10. `phase1-step14-fab-wiring`
11. `phase1-step15-save-reload`
12. Continue similarly for phases 2-4.

Use one tag at each phase boundary.

---

## 37) Definition Of Done

All are true:

- Each phase exit gate is green.
- Backend/Forge contracts are version-compatible.
- Legacy command flow still works until deliberate deprecation.
- `static/ops.js` and templ generated files are in sync in repo.
- No severe console/runtime errors in desktop or mobile smoke tests.

