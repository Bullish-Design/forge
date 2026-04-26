# FORGE_FEATURE_ADDITION.md

## Purpose

This report proposes a concrete implementation plan for three Forge feature additions:

1. Full-screen CodeMirror editing mode for direct page editing from the web UI, optimized for mobile.
2. Precise section/item targeting so the user can constrain LLM edits to explicit content.
3. New-page creation from the web UI using deterministic templates and paths.

The goal is to place each change in the library where it fits best, minimizing architectural drift and reusing the code that already exists.

---

## What I studied

### Forge

Forge is the outer web server wrapper around Kiln. Its role is to:

- inject overlay assets into rendered HTML
- serve overlay static assets under `/ops/*`
- proxy `/api/*` to a separate backend
- continue delegating page rendering and static site serving to Kiln

That means Forge should stay thin. It should mostly continue acting as the transport/container for UI assets and API forwarding.

### Obsidian-Ops

Obsidian-Ops is where the application behavior already lives. It currently contains:

- a FastAPI app
- overlay injection into generated HTML
- static serving for `/ops`
- page-path resolution from URL to vault file
- a rebuild pipeline
- job queue + SSE progress streaming
- an agent runtime with tool-calling
- atomic file reads/writes, vault path validation, locking, undo/history

This is the right place for almost all of the new behavior.

### Obsidian-Agent

I was not able to directly inspect the Bullish-Design `obsidian-agent` repository in this session, so I am not basing any file-level implementation claims on that codebase.

My recommendation is therefore grounded mainly in Forge + Obsidian-Ops.

---

## Architectural conclusion

### Best placement by library

#### Forge

Keep Forge focused on:

- `/ops/*` static asset serving
- `/api/*` reverse proxying
- HTML overlay injection during dev serving
- optional packaging/build convenience

#### Obsidian-Ops

Put nearly all feature logic here:

- editor mode UI behavior
- editor fetch/save endpoints
- section reference data structures and APIs
- page creation/template APIs
- agent request model expansion
- section-aware tools for precise edits
- rebuild + re-injection after direct edits

#### Obsidian-Agent

Only involve this repo later if you want the same interaction primitives inside native Obsidian.
For the browser UX described here, it is not the best first integration target.

---

## Existing seams in the current codebase

These are the seams the proposed work should build on.

### In Forge

Forge already documents the split clearly:

- `--overlay-dir` serves overlay assets at `/ops/*`
- `--inject-overlay` injects CSS/JS tags into HTML
- `--proxy-backend` forwards `/api/*`

That means new browser-side functionality can remain an overlay concern without changing Kiln itself.

### In Obsidian-Ops

Useful existing behavior already in place:

- `inject.py` injects `/ops/ops.css` and `/ops/ops.js` into site HTML.
- `app.py` mounts `/ops` and the generated site.
- `app.py` resolves current page URLs to vault file paths before creating agent jobs.
- `app.py` exposes SSE job streaming, undo, and history.
- `tools.py` already supports whole-file `read_file`, `write_file`, `list_files`, `search_files`, `fetch_url`, `undo_last_change`, and `get_file_history`.
- `ToolRuntime.write_file()` already uses vault-path validation, locking, and atomic writes.
- `agent.py` already builds a system prompt around the current file and uses OpenAI-style tool calling.

This is exactly the foundation needed for the three features.

---

# Feature 1: Full-screen CodeMirror editor mode

## Product goal

Switch the page from rendered-site interaction into a full editor mode, not split view.
The editor should feel native on mobile and send the full markdown content back to the server when saving.

## Recommendation

Implement this primarily in **Obsidian-Ops**, with Forge unchanged except for continuing to serve and inject the overlay assets.

## Why Obsidian-Ops is the right home

- It already owns `/ops/ops.js` and `/ops/ops.css` via static serving.
- It already knows how to resolve a page URL back to a vault file.
- It already owns safe file writing.
- It already handles rebuild + injection after changes.
- It already has undo/history infrastructure.

## UX shape

### Mode switch

Add a prominent overlay action such as:

- `Edit page`
- `Done`
- `Save`
- `Save & refresh`
- `Discard`

When activated:

- the rendered page is hidden
- the overlay becomes a full-screen CodeMirror editor
- the source markdown for the current page is loaded into the editor
- on mobile, the top bar stays compact and sticky

### Mobile-first behavior

- full-screen editor only, no side-by-side preview
- large touch targets for save/cancel/selection actions
- sticky action bar
- minimized chrome
- optional keyboard shortcut support on desktop, but not required for mobile

## Backend additions

### New read endpoint

Add a direct source-read endpoint in `obsidian_ops.app`.

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

Rules:

- prefer explicit `path` when present
- otherwise resolve via existing `current_url_path -> vault path` logic
- validate vault-relative path with existing safety logic

### New save endpoint

Add a direct save endpoint in `obsidian_ops.app`.

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
  "changed_files": ["Projects/Example.md"],
  "rebuilt": true,
  "new_sha256": "..."
}
```

### Server implementation strategy

Inside `obsidian_ops.app`:

1. Resolve path.
2. Validate it against vault root.
3. Read current content and compare hash if `expected_sha256` was supplied.
4. Write with the existing `ToolRuntime.write_file()` path or a thin internal helper that reuses the same atomic-write logic.
5. Trigger rebuild.
6. Re-run overlay injection.
7. Return the new hash.

### Important design note

Do **not** send direct source-edit saves through the agent job queue.

Direct editing is deterministic. It should use a dedicated API route, not the LLM path. The agent path should stay for assisted edits, not manual saves.

## Frontend additions

### Where to implement

In the overlay JS/CSS currently injected by Obsidian-Ops.

Suggested additions:

- `editor-mode.ts` or `editor-mode.js`
- `source-api.ts` or `source-api.js`
- `editor-toolbar.ts` or `editor-toolbar.js`
- `ops.css` updates for full-screen layout

### Editor lifecycle

1. User taps `Edit page`.
2. Overlay resolves current file via existing page context.
3. Frontend fetches source content.
4. CodeMirror instance is mounted into a full-screen container.
5. Save sends full content.
6. Success exits editor mode and reloads page.

### Suggested editor capabilities for v1

- markdown syntax highlighting
- line wrapping
- bracket matching
- search
- undo/redo inside editor
- dirty-state badge
- save/discard confirmation

### Suggested capabilities for v2

- heading outline drawer
- quick jump to sections
- local autosave draft in `localStorage`
- optional vim/emacs keymaps on desktop only

## Data model additions

Add source request/response models in `models.py`, for example:

- `SourceReadResponse`
- `SourceWriteRequest`
- `SourceWriteResponse`

## Risks

### Conflict risk

A file may change between read and save.

Mitigation:

- include `expected_sha256`
- reject stale saves with 409
- offer `Reload` or `Force save`

### Rebuild latency

Saving requires rebuild + injection.

Mitigation:

- keep direct writes synchronous for correctness first
- later add a lightweight `save -> optimistic toast -> background rebuild` mode if needed

### Mobile keyboard friction

Mitigation:

- minimal toolbar
- avoid extra modal layers while editing
- preserve scroll/selection on save failure

## Acceptance criteria

- A user can open any rendered page and enter full-screen source edit mode.
- The full markdown source loads correctly.
- Save writes the full file back into the vault.
- The rebuilt page reflects the change after save.
- Undo/history continue to work.
- Mobile layout is usable without split view.

---

# Feature 2: Precise section/item references for LLM edits

## Product goal

Let the user indicate exactly what content the LLM should edit, without forcing the model to infer the target from a broad page prompt.

## Recommendation

This should be split across:

- **Obsidian-Ops overlay UI** for selection/reference capture
- **Obsidian-Ops API/models** for request payload expansion
- **Obsidian-Ops tools + agent prompting** for actual section-constrained edits

Forge does not need feature logic here.

## Guiding principle

Do not rely only on “the current file” as agent context.
That is too coarse.

The current code already gives the agent the selected file path. The next step is to give it **explicit target scope metadata**.

## Recommended progression

### Stage 1: Selection-based constraints

Fastest useful version.

#### UX

When the user selects text in rendered mode or editor mode, show a floating action menu:

- `Ask agent about selection`
- `Rewrite selection`
- `Replace selection`
- `Insert below`
- `Create task from selection`

#### Payload shape

Extend the job request model with optional fields such as:

```json
{
  "instruction": "Rewrite this section more concisely",
  "current_file_path": "Projects/Example.md",
  "current_url_path": "/projects/example",
  "selection_text": "...",
  "selection_context_before": "...",
  "selection_context_after": "...",
  "selection_start_line": 42,
  "selection_end_line": 57,
  "edit_intent": "replace_selection"
}
```

#### Why this works well now

Because the current tools are whole-file oriented. A selection payload improves agent precision immediately, even before section-aware write tools exist.

## Stage 2: Block references / anchors

This is the more robust long-term version.

### Why anchors matter

Selection text alone is brittle when:

- the same text appears multiple times
- formatting changes slightly
- another process edits the file between selection and execution

### Best long-term anchor strategy

Use stable markdown block identifiers or deterministic block anchors.

Options:

#### Option A: Obsidian block IDs

Use native Obsidian-style block references when present.

Pros:

- compatible with Obsidian concepts
- readable in source

Cons:

- not every paragraph/list item has one already

#### Option B: Managed HTML comments

Example:

```md
<!-- forge:block id=abc123 -->
## Project status
...
```

Pros:

- fully controlled by Forge/Ops
- can anchor headings, paragraphs, list items, callouts

Cons:

- adds markup noise to source

#### Option C: Ephemeral DOM-only mapping

Do not use as the main strategy.

Pros:

- no source mutation

Cons:

- fragile across rebuilds and markdown changes
- hard to align reliably with future edits

### Recommendation

Use a hybrid path:

- v1: selection text + context
- v2: stable heading/list/block anchors for precise edits

## UI options for targeting sections

### Best practical set

#### 1. Text selection menu

Best first version.

#### 2. Margin handles on block hover

Show a small touch-friendly dot/button next to headings, paragraphs, list items, and callouts.
Tap it to pin that block as context.

#### 3. Right-click / long-press menu

Useful as a secondary entry point, especially on desktop.
On mobile, long-press should open the same action sheet used for selection.

### Recommended UI model

Use all three, but prioritize them like this:

1. selection menu
2. margin handles
3. right-click / long-press fallback

## Backend/API additions

### Extend `JobRequest`

Add fields like:

- `selection_text: str | None`
- `selection_context_before: str | None`
- `selection_context_after: str | None`
- `selection_start_line: int | None`
- `selection_end_line: int | None`
- `anchor_ids: list[str] | None`
- `edit_intent: Literal[...] | None`
- `target_mode: Literal["selection", "anchors", "file"] | None`

### Update agent system prompt construction

In `agent.py`, extend the system/user message construction so the model sees a structured target scope, for example:

- current file path
- selected text
- line range
- explicit instruction to edit only the target span unless told otherwise

This is much better than burying all targeting detail inside the raw user instruction.

## Tooling changes

### Short-term

Keep existing tools and improve the prompt.

The agent can:

- read the file
- locate the selection text
- rewrite narrowly
- write back the full file

### Long-term

Add section-aware tools to `tools.py`, such as:

- `read_section(path, anchor_id)`
- `replace_section(path, anchor_id, content)`
- `insert_after_section(path, anchor_id, content)`
- `list_sections(path)`
- `pinpoint_selection(path, text, start_line, end_line)`

These make the LLM safer and more reliable because the operation becomes structured instead of inferred.

## Suggested implementation order

### Phase 1

- extend `JobRequest`
- capture selection in overlay UI
- pass selection/context to agent
- prompt the model to keep edits inside that range

### Phase 2

- add parser/anchor extraction
- expose `list_sections`
- add `replace_section` and `insert_after_section`
- switch UI from raw selection targeting to stable anchored targeting where possible

## Acceptance criteria

- User can highlight text and invoke an agent action scoped to that content.
- Agent requests include structured target metadata.
- The model is instructed to keep edits local.
- Multi-section targeting is supported in a later phase with pinned blocks.
- Anchor-based editing is available for headings/blocks in a later phase.

---

# Feature 3: New-page creation from the web UI

## Product goal

Create new notes/pages directly from the web UI, using templates and deterministic target paths.

## Recommendation

Implement this almost entirely in **Obsidian-Ops**.

Forge only needs to continue serving the overlay and proxying API calls.

## Why deterministic creation matters

Do not make page creation depend on open-ended LLM inference.
A user asking for a new page usually wants:

- the correct folder
- the correct filename
- the correct frontmatter/body template
- the page to appear immediately in the vault/site

This should be a direct API operation first. The agent can still help fill content later.

## UX shape

Add a `New` action in the overlay.

When pressed, show a modal or sheet with page types such as:

- Project
- Task
- Topic
- Meeting note
- Daily note
- Blank page

Each type should define:

- label
- target path pattern
- template body
- optional required fields

## Recommended configuration model

Add template/page-type configuration to Obsidian-Ops settings.

Example concept:

```yaml
page_templates:
  - type: project
    label: Project
    path_template: "Projects/{{ slug }}/index.md"
    title_template: "{{ title }}"
    content_template: |
      ---
      type: project
      status: active
      tags: [project]
      ---

      # {{ title }}

      ## Goal

      ## Next actions

      ## Notes

  - type: task
    label: Task
    path_template: "Tasks/{{ date }}-{{ slug }}.md"
    content_template: |
      ---
      type: task
      status: open
      ---

      - [ ] {{ title }}
```

## API additions

### Template discovery endpoint

`GET /api/templates`

Returns the available page types and required fields.

### Note creation endpoint

`POST /api/pages`

Request:

```json
{
  "template_type": "project",
  "title": "New Website",
  "fields": {
    "status": "active"
  },
  "parent_path": "optional",
  "open_after_create": true
}
```

Response:

```json
{
  "ok": true,
  "path": "Projects/new-website/index.md",
  "url": "/projects/new-website/",
  "rebuilt": true
}
```

## Server behavior

Inside Obsidian-Ops:

1. Load configured template definition.
2. Render path and content placeholders.
3. Ensure parent directories exist.
4. Validate resulting path stays inside vault root.
5. Create file atomically.
6. Rebuild and inject overlay.
7. Return vault path + site URL.

## Contextual creation options

These are high-value follow-ons.

### From current page

Examples:

- `New task linked to this project`
- `New child topic under this note`
- `New meeting note for this client`

The UI can pre-fill fields from the current page context.

### From selected text

Examples:

- `Create task from selection`
- `Create topic from selection`
- `Extract into new note`

This combines well with feature 2.

## Tooling changes

### Direct API first

As with manual save, page creation should not initially be an LLM job.

### Optional agent tools later

Add tools such as:

- `create_file_from_template(template_type, title, fields)`
- `create_folder(path)`
- `extract_selection_to_new_note(...)`

This gives the model structured primitives for note creation later.

## Acceptance criteria

- User can create a new page from the browser.
- Page uses configured template and path rules.
- The file lands in the correct folder.
- The site rebuilds and opens the new page.
- Contextual variants can pre-fill fields later.

---

# Detailed file-by-file recommendation

## Forge

### Keep unchanged or lightly touched

#### `README.md` / docs

Add documentation for:

- direct source editing support through the Ops backend
- required `/api/source`, `/api/pages`, `/api/templates` backend routes
- mobile-focused editor mode

#### overlay packaging / dev configs

Only update if needed so Forge's `--overlay-dir` points at the expanded Obsidian-Ops overlay assets.

### Do not move app logic here

Avoid putting editor save logic, templating logic, or section-aware agent logic into Forge.
That would duplicate what Obsidian-Ops already owns.

## Obsidian-Ops

### `src/obsidian_ops/app.py`

Add or extend:

- `GET /api/source`
- `PUT /api/source`
- `GET /api/templates`
- `POST /api/pages`
- optional `GET /api/sections`

Also extend `/api/jobs` to accept structured scope metadata.

### `src/obsidian_ops/models.py`

Add models for:

- source read/write request/response
- template/page creation request/response
- richer `JobRequest` scope metadata
- section descriptors if anchor-based operations are added

### `src/obsidian_ops/tools.py`

Keep existing whole-file tools.
Add optional structured tools later:

- `read_section`
- `replace_section`
- `insert_after_section`
- `create_file_from_template`
- `list_sections`

### `src/obsidian_ops/agent.py`

Extend prompt construction and tool schema usage so the model understands:

- exact selection scope
- anchor IDs when present
- target edit mode
- whether it must stay local vs create a new note

### `src/obsidian_ops/inject.py`

Likely unchanged except for ensuring the editor assets continue to load through `/ops/ops.js` and `/ops/ops.css`.

### `src/obsidian_ops/static/ops.js` and `ops.css`

This is where the visible UX belongs.

Add:

- full-screen CodeMirror mode
- save/discard toolbar
- selection action menu
- margin block handles
- template/new-page modal
- source load/save API calls

If the JS grows, split it into modules and bundle it for the static output.

### `src/obsidian_ops/page_context.py`

Extend if needed so page-to-note resolution can also support:

- reverse mapping after page creation
- section metadata lookup
- cleaner current-page context for the overlay

### `src/obsidian_ops/rebuild.py`

No major conceptual changes.
It remains the post-save and post-create rebuild hook.

---

# Recommended implementation roadmap

## Milestone 1: Manual source editing

Deliverables:

- full-screen CodeMirror mode
- `GET /api/source`
- `PUT /api/source`
- save/discard flow
- optimistic concurrency token
- rebuild + reload

Why first:

- largest user-visible gain
- minimal LLM complexity
- best mobile payoff

## Milestone 2: Selection-scoped agent actions

Deliverables:

- selection UI
- expanded `JobRequest`
- agent prompt support for selection-only edits
- actions like rewrite/replace/insert-below

Why second:

- significantly improves edit precision
- reuses existing agent + whole-file write flow

## Milestone 3: Template-based page creation

Deliverables:

- templates config
- `GET /api/templates`
- `POST /api/pages`
- contextual create flows

Why third:

- deterministic and straightforward once direct write endpoints exist

## Milestone 4: Anchor-aware editing tools

Deliverables:

- block anchor extraction
- block pinning UI
- section APIs/tools
- more reliable targeted edits

Why fourth:

- highest precision
- most engineering complexity

---

# Strong opinions / design calls

## 1. Do not default to split view

Given your mobile-first requirement, the correct default is a **full editor takeover**.
Rendered view and source view should be separate modes.

## 2. Do not route manual saves through the LLM queue

Manual edits should be direct API writes.
The LLM path is for assisted edits.

## 3. Put behavior in Obsidian-Ops, not Forge

Forge is the shell.
Obsidian-Ops is the application.
Preserve that boundary.

## 4. Selection metadata should become a first-class request field

Do not rely on “the current file” alone.
Use structured scope data.

## 5. Page creation should be deterministic first, agent-assisted second

Template rules beat open-ended file placement guesses.

---

# Minimal viable schema additions

## `JobRequest`

Suggested expansion:

```python
class JobRequest(BaseModel):
    instruction: str
    current_file_path: str | None = None
    current_url_path: str | None = None
    target_mode: str | None = None
    edit_intent: str | None = None
    selection_text: str | None = None
    selection_context_before: str | None = None
    selection_context_after: str | None = None
    selection_start_line: int | None = None
    selection_end_line: int | None = None
    anchor_ids: list[str] | None = None
```
```

## Source API

```python
class SourceReadResponse(BaseModel):
    path: str
    content: str
    sha256: str
    modified_at: str | None = None

class SourceWriteRequest(BaseModel):
    path: str
    content: str
    expected_sha256: str | None = None
    refresh: bool = True

class SourceWriteResponse(BaseModel):
    ok: bool
    path: str
    bytes_written: int
    rebuilt: bool
    new_sha256: str
```
```

## Page creation API

```python
class CreatePageRequest(BaseModel):
    template_type: str
    title: str
    fields: dict[str, Any] = {}
    parent_path: str | None = None
    open_after_create: bool = True

class CreatePageResponse(BaseModel):
    ok: bool
    path: str
    url: str
    rebuilt: bool
```
```

---

# Final recommendation

If you want the cleanest implementation with the least architectural friction:

- keep **Forge** as the proxy + injector + asset shell
- implement all three features mainly in **Obsidian-Ops**
- treat **manual editing** and **page creation** as direct API flows
- treat **LLM-assisted editing** as a second path that gains precision from structured selection/anchor metadata

The best first slice is:

1. full-screen CodeMirror mode
2. direct source read/save endpoints
3. selection-scoped agent actions
4. templated page creation

That sequence gives you the biggest usability gain quickly, especially on mobile, while staying aligned with the code that already exists.

---

## Source basis

Repos reviewed:

- Forge: https://github.com/Bullish-Design/forge
- Obsidian-Ops: https://github.com/Bullish-Design/obsidian-ops
- Obsidian-Agent: https://github.com/Bullish-Design/obsidian-agent

Observed implementation basis:

- Forge README and repo structure
- Obsidian-Ops `app.py`
- Obsidian-Ops `tools.py`
- Obsidian-Ops `agent.py`
- Obsidian-Ops `inject.py`
