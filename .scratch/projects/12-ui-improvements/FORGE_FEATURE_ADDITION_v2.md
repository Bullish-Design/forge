# FORGE_FEATURE_ADDITION_v2.md

## Purpose

This v2 report revises the original feature-addition analysis after directly studying the `obsidian-agent` repo in addition to Forge and Obsidian-Ops.

The main correction in this report is architectural:

- **Forge** should remain the thin transport and injection shell.
- **Obsidian-Ops** should continue owning raw vault I/O, path safety, locking, rebuilds, and deterministic page/template creation.
- **Obsidian-Agent** should own the **semantic / LLM-facing interaction layer** for constrained edits, interface-specific request shaping, prompt enrichment, and tool selection.

That means the direct CodeMirror editor still belongs mostly in Forge + Obsidian-Ops, but the "edit *this exact section*" workflows are better served by **Obsidian-Agent** than the original v1 report gave it credit for.

---

## What changed from v1

The original report treated Obsidian-Agent as mostly irrelevant to the web interaction work.

After studying the repo, that is **too conservative**.

Obsidian-Agent is intentionally the semantic service boundary. It already owns:

- HTTP request handling for agent operations
- orchestration of the LLM loop
- prompt construction
- tool dispatch and response shaping
- validation of `current_file`
- an `interface_id` extension seam
- heading-level and block-level read/write tools

That materially changes the recommended split for feature 2, and slightly changes the way feature 3 should be exposed to the agent later.

The revised guidance is:

1. **Full-screen CodeMirror mode**: still primarily **Obsidian-Ops** + Forge overlay.
2. **Section/item targeting for constrained edits**: primarily **Obsidian-Agent**, backed by **Obsidian-Ops** anchor/discovery primitives.
3. **New page creation from web UI**: primarily **Obsidian-Ops** for deterministic template/path creation, with **optional Obsidian-Agent integration** for semantic prefills.

---

## Repositories studied

### Forge

Forge is the outer shell around the site generator runtime. It is the right place to remain thin and focused on:

- serving and injecting the overlay assets
- proxying browser API calls
- providing a stable container for the browser experience

### Obsidian-Ops

Obsidian-Ops is the vault/runtime layer. It is already the owner of:

- vault-relative path validation
- atomic file writes
- mutation locking
- undo/history
- content patching primitives
- the FastAPI-side app concerns currently used by the browser overlay
- rebuild / generated-site refresh mechanics

### Obsidian-Agent

Obsidian-Agent is a separate backend service whose boundary is now very clear.

It explicitly owns:

- `/api/apply`, `/api/undo`, `/api/health`
- agent orchestration and prompt construction
- tool dispatch
- request/response shaping

It explicitly does **not** own:

- raw filesystem mutation logic
- raw `jj` subprocess lifecycle management
- URL-to-file resolution for caller web routes

This is the most important design fact for the revised report.

---

## Current reusable seams that matter for these features

## Forge

Forge already gives you the right shell for browser interaction:

- overlay assets can be served and injected without modifying the site generator
- browser APIs can continue to proxy to backend services
- the editor can be implemented as an overlay mode instead of replacing site rendering infrastructure

## Obsidian-Ops

Obsidian-Ops already gives you the correct raw-operation foundation:

- read / write whole-file access
- atomic updates
- locking
- undo/history
- vault path safety
- heading/block patching support exposed through the Vault surface that Obsidian-Agent consumes
- URL-to-file resolution on the web side
- rebuild + re-serve behavior

## Obsidian-Agent

Obsidian-Agent already gives you a stronger extension seam than v1 assumed:

- `ApplyRequest` already includes `current_file` and `interface_id`
- `app.py` already routes through an `interface_handlers` map keyed by `interface_id`
- `prompt.py` already builds a system prompt dynamically from context
- `tools.py` already exposes semantic edit tools:
  - `read_heading` / `write_heading`
  - `read_block` / `write_block`
  - `get_frontmatter` / `set_frontmatter` / `update_frontmatter`
  - whole-file fallback tools

This means the browser can ask the agent to edit **a heading** or **a block** without inventing a brand-new agent capability model from scratch.

---

# Revised architectural conclusion

## Ownership by feature

### Feature 1: full-screen CodeMirror editing mode

**Primary owner:** Obsidian-Ops  
**Secondary owner:** Forge  
**Obsidian-Agent role:** optional, only for "AI from editor" actions

### Feature 2: section/item targeting for constrained LLM edits

**Primary owner:** Obsidian-Agent  
**Supporting owner:** Obsidian-Ops  
**Forge role:** browser UI only

### Feature 3: new-page creation from the web UI

**Primary owner:** Obsidian-Ops  
**Secondary owner:** Forge  
**Obsidian-Agent role:** optional semantic prefill / assist layer

---

# Feature 1: full-screen CodeMirror editor mode

## Product goal

Switch the page entirely into a CodeMirror editor mode, optimized for mobile.

No split view.
No default preview pane.
The page becomes an editor-first surface with explicit save / discard / AI actions.
Works on desktop and mobile browsers

## Why this still belongs outside Obsidian-Agent

This mode is a **direct source editing** experience, not an LLM operation.

The critical requirements are:

- load the full source for the current page
- edit the full source locally in the browser
- save the full source back to the vault
- enforce path safety
- detect conflicts
- rebuild / refresh the generated site

Those are raw file and web-route concerns, which align with Obsidian-Ops, not Obsidian-Agent.

Obsidian-Agent should not be inserted into the save path for direct source editing.

## Recommended ownership split

### Forge

Keep Forge thin:

- continue serving the overlay assets
- continue proxying browser `/api/*` requests
- continue injecting the overlay into rendered pages

### Obsidian-Ops

Own the full direct-edit pipeline:

- load source for current page
- save source for current page
- validate vault-relative path
- check optimistic concurrency hash
- atomically write file
- rebuild site
- expose undo/history for direct edits

### Obsidian-Agent

No required role in the save flow.

Optional later role:

- `Ask AI about this page`
- `Rewrite selected section`
- `Create outline from this note`

Those should remain explicit agent actions from inside the editor toolbar.

## Browser UX

### Entering editor mode

Add a top-level overlay action:

- `Edit`

When activated:

- rendered-page interaction is replaced with a full-screen editor shell
- CodeMirror mounts over the page
- the current note markdown is loaded into the editor
- the top bar shows note path, dirty state, and save/cancel actions

### Toolbar actions

Recommended toolbar:

- `Back`
- `Save`
- `Discard`
- `Undo`
- `History`
- `Ask AI`
- `Select scope`
- `New`

### Mobile details

Because this is intended for frequent mobile use:

- use full-screen mode by default
- make all actions thumb-sized
- keep the toolbar sticky
- avoid any default side preview
- avoid requiring right-click-only interactions
- support long-press interactions for selection and targeting

## New backend API in Obsidian-Ops

## Source read endpoint

Add a direct source-load endpoint.

Suggested shape:

`GET /api/source?current_url_path=/foo/bar`

or

`GET /api/source?path=Projects/Example.md`

Response:

```json
{
  "path": "Projects/Example.md",
  "content": "# Example\n...",
  "sha256": "...",
  "modified_at": "..."
}
```

Behavior:

- if `path` is provided, treat it as authoritative after validation
- otherwise resolve from `current_url_path`
- use existing URL-to-vault-path resolution in the web app layer
- return a content hash for optimistic concurrency

## Source save endpoint

Add a direct whole-file save endpoint.

Suggested shape:

`PUT /api/source`

Request:

```json
{
  "path": "Projects/Example.md",
  "content": "full file content",
  "expected_sha256": "optional optimistic concurrency token",
  "refresh": true
}
```

Response:

```json
{
  "ok": true,
  "path": "Projects/Example.md",
  "bytes_written": 1234,
  "new_sha256": "...",
  "rebuilt": true,
  "warning": null
}
```

Behavior:

- validate vault-relative path
- verify hash if provided
- use atomic write through existing vault mechanisms
- trigger rebuild / refresh logic
- return conflict errors cleanly if file changed underneath the editor

## Optional autosave

I would **not** make autosave the first implementation.

For mobile and LLM-assisted editing, explicit save is safer.

If added later:

- use throttled draft-state persistence in the browser first
- only write to the vault on explicit save or a guarded autosave mode

## Recommended code placement

### Forge

Minimal or no backend change.

Possible changes:

- keep any overlay asset build wiring updated
- document the new editor mode and proxy expectations

### Obsidian-Ops

Primary code changes:

- overlay JS/CSS: add editor mode and mobile toolbar behavior
- FastAPI app: add `GET /api/source` and `PUT /api/source`
- vault integration: reuse existing atomic write and path validation
- rebuild wiring: refresh generated output after save
- history wiring: expose direct-edit undo/history cleanly in the editor mode

### Obsidian-Agent

No required code change for basic direct editing.

---

# Feature 2: section/item targeting for constrained LLM edits

## Revised v2 conclusion

This feature should be treated as an **Obsidian-Agent feature first**, not just a browser-overlay feature.

The browser should capture the user's targeting intent, but the agent should own the semantic interpretation of that target.

That is because Obsidian-Agent already has:

- the request model boundary
- prompt construction
- interface-specific routing
- heading/block tools
- tool dispatch

That is the exact layer where edit constraints should become enforceable.

## Why this changed from v1

In v1, I suggested adding section-aware edit tooling mostly in Obsidian-Ops.

After studying Obsidian-Agent, that is not the best split.

You **already have** semantic tools for precise edits:

- `read_heading(path, heading)`
- `write_heading(path, heading, content)`
- `read_block(path, block_id)`
- `write_block(path, block_id, content)`

That means the main missing pieces are now:

1. **browser targeting UX**
2. **anchor discovery / creation support**
3. **richer request payloads into Obsidian-Agent**
4. **interface-specific prompt/tool restrictions**

## Recommended interaction model

Use a three-tier targeting model.

### Tier 1: block-id targeting (best)

Primary target model for arbitrary paragraphs, list items, callouts, and blocks.

Flow:

- user long-presses or taps a margin handle on a block
- UI resolves or creates a stable Obsidian block ID (`^block-id`)
- browser sends `block_id` to Obsidian-Agent
- agent is instructed to operate only on that block unless the user expands scope

This is the most robust option for mobile and for repeated edits over time.

### Tier 2: heading targeting (good)

For larger sections:

- user taps a heading handle / margin chip
- browser sends heading text such as `## Roadmap`
- Obsidian-Agent uses `read_heading` / `write_heading`

This is ideal for section rewrites, appended subsections, and structured note maintenance.

### Tier 3: quoted selection targeting (fallback)

For raw text selections that do not yet map neatly to a heading/block:

- browser captures selected text and nearby context
- request includes quoted selection text
- agent prompt says to target only that quoted range

This should be the fallback, not the primary design, because text-only matching is less stable than heading/block anchors.

## Browser UX options

## Recommended primary UX

For mobile-first usage, I would implement:

### Long-press action sheet

On long-press in editor mode or rendered mode:

- `Edit this block with AI`
- `Edit this section with AI`
- `Reference this in prompt`
- `Insert below`
- `Add block anchor`

### Margin handles

On headings / blocks, show a subtle tappable gutter chip.

Examples:

- heading chip
- paragraph/list item dot
- callout handle

Tap behavior:

- single tap selects the target
- second tap opens actions
- multi-select supported via pinned selections

### Pinned scope bar

When one or more targets are selected, show a sticky scope bar:

- `1 block selected`
- `3 sections selected`
- `Clear`
- `Ask AI`

This is much better than relying purely on right-click context menus, especially on mobile.

## Required supporting work in Obsidian-Ops

Obsidian-Agent can already edit by heading and block, but the browser still needs a way to discover or create those anchors.

That support belongs in Obsidian-Ops because it owns raw vault mutation and parsing.

## New structure endpoint

Add a structure-discovery endpoint in Obsidian-Ops.

Suggested shape:

`GET /api/structure?path=Projects/Example.md`

Response:

```json
{
  "path": "Projects/Example.md",
  "headings": [
    {"heading": "# Example", "level": 1, "line_start": 1, "line_end": 20},
    {"heading": "## Tasks", "level": 2, "line_start": 21, "line_end": 40}
  ],
  "blocks": [
    {"block_id": "intro-1", "line_start": 2, "line_end": 5},
    {"block_id": "task-a", "line_start": 23, "line_end": 24}
  ]
}
```

Purpose:

- let the browser understand what can be targeted deterministically
- avoid brittle DOM-only targeting
- support margin handles and selection overlays

## New anchor-ensure endpoint

Add a minimal endpoint for assigning block IDs when needed.

Suggested shape:

`POST /api/anchors/ensure`

Request:

```json
{
  "path": "Projects/Example.md",
  "line_start": 23,
  "line_end": 24
}
```

Response:

```json
{
  "ok": true,
  "path": "Projects/Example.md",
  "block_id": "task-a",
  "changed": true
}
```

Purpose:

- persist a stable anchor into the markdown
- let later AI edits reuse the same target reliably

This is raw-file mutation and therefore belongs in Obsidian-Ops, not Obsidian-Agent.

## Required work in Obsidian-Agent

This is the major v2 shift.

Obsidian-Agent should own the **scoped edit contract**.

## Extend `ApplyRequest`

Today `ApplyRequest` only accepts:

- `instruction`
- `current_file`
- `interface_id`

For the web editor, extend it with optional structured scope fields.

Suggested additions:

```json
{
  "instruction": "Rewrite this as a concise action list",
  "current_file": "Projects/Example.md",
  "interface_id": "forge_web",
  "target_mode": "block",
  "target_block_id": "task-a",
  "target_heading": null,
  "selected_text": null,
  "surrounding_context": null,
  "allowed_write_scope": "target_only"
}
```

Recommended optional fields:

- `target_mode`: `file | heading | block | selection | multi`
- `target_heading`
- `target_block_id`
- `selected_text`
- `surrounding_context`
- `target_block_ids` for multi-select
- `allowed_write_scope`: `target_only | target_plus_frontmatter | unrestricted`
- `intent_mode`: `rewrite | summarize | insert_below | annotate | extract_tasks`

## Use `interface_id` as the first-class extension seam

This is already present in `obsidian-agent.app`, which is a strong signal that interface-specific behavior is intended.

Recommendation:

- keep current `command` interface behavior unchanged
- add a new interface such as `forge_web`
- map it to a handler that understands structured scope fields

That gives you a clean separation between:

- generic natural-language agent calls
- browser-constrained editor actions

## Prompt enrichment in `prompt.py`

The current system prompt only injects `current_file`.

For `forge_web`, build a richer scoped prompt.

Examples:

### Heading scope

- user is currently viewing `Projects/Example.md`
- only edit heading `## Tasks`
- prefer `read_heading` and `write_heading`
- do not modify other headings unless explicitly asked

### Block scope

- user is currently viewing `Projects/Example.md`
- only edit block `^task-a`
- prefer `read_block` and `write_block`
- do not rewrite the whole file unless the target cannot be updated safely

### Selection scope

- user selected the quoted text below
- treat that text as the exclusive edit target
- do not change unrelated content

## Tool restriction strategy

This is where Obsidian-Agent becomes especially valuable.

For constrained browser edits, do **not** always expose the full toolset.

Recommended interface-specific tool policy:

### `command` interface

Keep the current full toolset.

### `forge_web` interface with target-only constraints

Prefer a narrower toolset:

- `read_heading` / `write_heading`
- `read_block` / `write_block`
- optionally `get_frontmatter` / `update_frontmatter`
- only expose `read_file` / `write_file` when necessary as escape hatches

This is the strongest practical way to reduce scope drift.

## Implementation note

You do not necessarily need a second endpoint.

A clean v2 path is:

- keep `POST /api/apply`
- expand `ApplyRequest`
- add `interface_id="forge_web"`
- add handler-specific prompt shaping and tool exposure

If request complexity grows too much later, then introduce a dedicated structured endpoint such as `/api/apply_scoped`.

## Recommended code placement

### Forge

Browser-only work:

- selection UI
- gutter handles
- long-press actions
- pinned scope UI
- payload construction before sending to the agent

### Obsidian-Ops

Supporting raw capabilities:

- heading/block discovery endpoint
- block-anchor creation endpoint
- any future exact-span patch primitives
- path resolution from current page URL to vault file

### Obsidian-Agent

Primary semantic ownership:

- extend request model
- introduce `forge_web` interface handler
- enrich prompt with scope data
- narrow toolset by interface / scope
- enforce target-aware editing behavior

---

# Feature 3: creating new pages from the web UI

## Revised v2 conclusion

This should still be **deterministic first**, which means **Obsidian-Ops** should own the actual page creation pipeline.

However, unlike v1, I now recommend planning an **optional Obsidian-Agent assist layer** for semantic prefills and context-derived defaults.

The actual creation step should still not be delegated to the agent by default.

## Why deterministic creation belongs in Obsidian-Ops

The key concerns are not semantic; they are structural:

- correct target directory
- correct file naming rules
- template selection
- frontmatter defaults
- creating missing folders
- vault-safe writes
- predictable outputs for mobile quick-add flows

Obsidian-Agent explicitly does not own raw filesystem behavior, and its current toolset is not yet the right abstraction for template registries and deterministic page factories.

## Product UX

Add a `New` action in the editor toolbar and overlay menu.

Open a modal or sheet with page types such as:

- Project
- Task
- Topic
- Meeting Note
- Daily Note
- Blank Note

Each type maps to a deterministic template rule.

Examples:

- `Projects/{{slug}}.md`
- `Tasks/{{date}}-{{slug}}.md`
- `Topics/{{slug}}.md`
- `Meetings/{{date}}-{{slug}}.md`

## Template registry in Obsidian-Ops

Add a template registry owned by Obsidian-Ops.

Possible configuration sources:

- YAML config file
- JSON config file
- Python settings object
- vault-local templates directory

Recommended registry shape:

```yaml
templates:
  project:
    path_pattern: "Projects/{{slug}}.md"
    title_from: "name"
    frontmatter:
      type: project
      status: active
    body: |
      # {{title}}

      ## Summary

      ## Tasks

      ## Notes

  task:
    path_pattern: "Tasks/{{date}}-{{slug}}.md"
    frontmatter:
      type: task
      status: open
    body: |
      # {{title}}

      ## Context

      ## Next Steps
```

## Create-page endpoint in Obsidian-Ops

Suggested shape:

`POST /api/pages/create`

Request:

```json
{
  "template": "project",
  "title": "Website refresh",
  "slug": "website-refresh",
  "fields": {
    "status": "active",
    "owner": "me"
  },
  "open_after_create": true
}
```

Response:

```json
{
  "ok": true,
  "path": "Projects/website-refresh.md",
  "created": true,
  "rebuilt": true,
  "url": "/projects/website-refresh"
}
```

Behavior:

- resolve target path deterministically
- create folders if needed
- render template placeholders
- write file atomically
- rebuild
- return canonical vault path and resulting URL

## Context-aware quick-create

A very strong v2 enhancement is contextual creation from the current page.

Examples:

- `New task from this project`
- `New topic linked to this note`
- `New meeting note for this client`

That can still be deterministic if the browser passes context fields explicitly.

Suggested request additions:

```json
{
  "template": "task",
  "title": "Finalize mobile editor",
  "context": {
    "source_page": "Projects/Forge.md",
    "backlink": "[[Projects/Forge]]",
    "project": "Forge"
  }
}
```

## Where Obsidian-Agent can help here

This is the main place where agent participation is useful but should remain optional.

### Good uses of Obsidian-Agent

- suggest the right template based on instruction
- prefill frontmatter fields from the current note
- derive title / slug suggestions
- generate an initial outline after deterministic file creation

### Bad default use of Obsidian-Agent

- deciding the path on its own
- deciding the filename on its own
- directly creating pages with unconstrained whole-file write behavior from browser quick-add

That should remain deterministic.

## Recommended future agent tool

If you later want agent-driven creation, expose a **high-level template-aware tool** from Obsidian-Ops into Obsidian-Agent rather than telling the agent to improvise with `write_file`.

Recommended future tool:

- `create_note_from_template(template_key, title, fields)`

This preserves deterministic path/template behavior while still letting the agent participate.

## Recommended code placement

### Forge

Browser-only work:

- open modal / action sheet
- gather title/template/field input
- navigate to created page after success

### Obsidian-Ops

Primary ownership:

- template registry
- page creation endpoint
- folder creation
- frontmatter/body rendering
- rebuild and redirect metadata

### Obsidian-Agent

Optional secondary ownership:

- recommend template key
- prefill fields
- post-create refinement via explicit agent action
- later: call a high-level template creation tool if you expose one

---

# File-level integration recommendations

## Forge

Forge should stay intentionally thin.

Recommended changes:

- keep overlay injection and static asset serving as-is
- ensure proxy rules cleanly support new endpoints:
  - `/api/source`
  - `/api/structure`
  - `/api/anchors/ensure`
  - `/api/pages/create`
  - existing agent `/api/apply`
- document the mobile-first full-screen editor mode

In other words: **do not move business logic into Forge**.

## Obsidian-Ops

This repo should absorb most of the raw web/runtime work.

Recommended change areas:

### Browser overlay assets

Add or extend:

- editor-mode mount/unmount logic
- CodeMirror instance lifecycle
- mobile toolbar state
- target selection UI
- long-press interaction handling
- pinned scope UI
- `New` page flow UI

### FastAPI app layer

Add endpoints for:

- source read
- source save
- file structure discovery
- anchor ensure/create
- deterministic page creation

### Vault/runtime layer

Ensure / add primitives for:

- structure discovery
- stable block-id assignment
- deterministic template rendering and file creation
- any line/block span helpers needed by the browser

## Obsidian-Agent

This repo should absorb the scoped-agent behavior.

Recommended change areas:

### `models.py`

Extend `ApplyRequest` with optional structured scope fields.

### `app.py`

Add a `forge_web` interface handler using the existing `interface_handlers` seam.

### `prompt.py`

Introduce richer prompt construction for scoped browser edits.

### `tools.py`

Optionally split tool registration by interface / capability profile.

Example direction:

- full command toolset
- scoped editor toolset
- read-only inspect toolset

### `agent.py`

Pass the richer request context through to prompt/tool selection.
Potentially centralize tool policy per interface.

---

# Recommended implementation phases

## Phase 1: direct editor mode

Implement first:

- full-screen CodeMirror mode
- `GET /api/source`
- `PUT /api/source`
- explicit save/discard flow
- mobile toolbar

This delivers immediate value without touching agent semantics.

## Phase 2: scoped AI editing using existing heading/block tools

Implement next:

- structure discovery endpoint in Obsidian-Ops
- anchor ensure endpoint in Obsidian-Ops
- browser scope selection UI
- `forge_web` interface in Obsidian-Agent
- extended `ApplyRequest`
- prompt/tool restrictions for target-only edits

This is the most important v2 shift.

## Phase 3: deterministic templated page creation

Implement after the editor/scoping work:

- template registry
- create-page endpoint
- new-page modal / quick-create actions
- contextual creation from current page

## Phase 4: optional semantic assists

Later enhancements:

- agent-recommended template choice
- agent-generated initial outlines
- post-create refinement commands
- multi-target edits across pinned blocks/sections

---

# Risks and mitigations

## Risk: editing scope drifts outside user intent

### Mitigation

Use Obsidian-Agent interface-specific tool restriction and scope-aware prompts.
Prefer heading/block tools over whole-file tools.

## Risk: DOM-based selection does not map cleanly to markdown

### Mitigation

Do not rely only on DOM offsets.
Use Obsidian-Ops structure discovery and stable block IDs.

## Risk: direct editor saves conflict with agent edits or external changes

### Mitigation

Use optimistic concurrency hashes on source save.
Surface conflict resolution explicitly.

## Risk: templated page creation becomes agent-driven and inconsistent

### Mitigation

Keep page creation deterministic in Obsidian-Ops.
Only let the agent assist with prefills or post-create edits.

---

# Final recommendation

The best v2 architecture is:

- **Forge** remains the shell.
- **Obsidian-Ops** owns direct editor source I/O, structure discovery, anchor creation, rebuilds, and deterministic page creation.
- **Obsidian-Agent** owns the semantic constrained-edit contract for the browser, using its existing request model, `interface_id` seam, prompt construction, and heading/block tools.

So the most important update to the original report is this:

> The browser should capture edit intent, Obsidian-Ops should provide the raw targetable document structure, and Obsidian-Agent should enforce the LLM-facing scoped-edit behavior.

That is the cleanest split across the three repos and the one that best matches the code that already exists.
