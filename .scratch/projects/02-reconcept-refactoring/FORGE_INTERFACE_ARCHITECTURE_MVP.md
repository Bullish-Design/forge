# Most Simplified Viable Interface Spec

## Status

- Status: Proposed
- Target: Forge-hosted local interface for Obsidian Ops
- Audience: implementers of the overlay UI and local backend
- Bias: maximum simplicity, low interactivity, recovery over responsiveness

---

## 1. One-sentence summary

A single floating button opens one modal where the user types a natural-language request for the current page; the browser sends that request to a same-origin API endpoint, the local backend runs one operation at a time against the vault, rebuilds the site if files changed, and returns a summary plus refresh/undo actions.

---

## 2. Design goal

This spec intentionally chooses the **simplest useful interface**.

It optimizes for:

- low implementation complexity
- low UI complexity
- single-user local operation
- no need for real-time interaction
- easy recovery through Jujutsu
- minimal moving parts around Kiln/Forge

It does **not** optimize for:

- real-time collaboration
- rich in-browser editing
- multiple concurrent jobs
- multi-interface plugin systems
- chat-native interaction patterns

---

## 3. Product shape

The product has four practical pieces:

- **rendered site**
- **overlay UI**
- **local backend**
- **vault + Jujutsu**

```text
User browsing page
   └─ clicks floating button
        └─ modal opens
             └─ user types one request
                  └─ POST /api/run
                       └─ backend runs agent/tool loop
                            └─ files may change
                                 └─ jj commit
                                      └─ kiln rebuild
                                           └─ return result
                                                └─ user refreshes or undoes
```

Forge’s role is intentionally thin:

- host the rendered site
- serve injected overlay assets
- proxy `/api/*` to the local backend

The backend owns actual vault operations.

---

## 4. Core design decisions

### 4.1 One interface only

There is exactly one interaction surface in v0:

- one floating action button
- one modal
- one multiline input
- one result/progress area
- one refresh action
- one undo action

There are **no tabs**, **no mode switchers**, and **no interface registry**.

### 4.2 No separate chat mode

The interface is not split into command mode vs chat mode.

Everything is just a natural-language request.

If follow-up is needed, the same modal can accept another request after the first one completes.

### 4.3 The page is not turned into an editor

The rendered page remains a rendered page.

The UI does **not** convert the main content area into CodeMirror or contenteditable mode.

The modal is the only editing/request surface.

### 4.4 Prefer blocking request/response

The browser sends one request and waits for one response.

There is no job queue, no SSE, and no websocket requirement in the base version.

This is acceptable because:

- the system is single-user
- operations are local
- low responsiveness is acceptable
- implementation simplicity is more valuable than live progress

### 4.5 One active mutation at a time

The backend processes one mutation at a time.

Use a single global in-process lock for v0.

This is simpler than per-file concurrency and aligns better with:

- global rebuild behavior
- simple undo expectations
- single-user operation

---

## 5. User experience

### 5.1 Default page state

When the user is browsing the rendered vault site:

- a floating button is always visible in the bottom-right corner
- the rest of the page behaves like a normal Kiln-rendered site

### 5.2 Open interaction

When the user clicks the button:

- a modal opens
- the current page path is shown as context
- a textarea is focused
- the user sees a prompt such as: `What would you like to do?`

### 5.3 Submit request

The user types requests like:

- `clean up this note`
- `summarize this page into a new note`
- `find related notes and add links`
- `fetch this article and create a source note`

Then they click **Run**.

### 5.4 Waiting state

While the request is in flight:

- the modal shows a simple busy state
- the textarea may be disabled
- the user may see static text like `Running...`

No live token streaming or step-by-step progress is required.

### 5.5 Completion state

When the request completes, the modal shows:

- a short summary of what happened
- changed files, if useful
- a **Refresh** button
- an **Undo last change** button
- the textarea again for another request

### 5.6 Undo flow

If the user clicks **Undo last change**:

- the browser sends `POST /api/undo`
- the backend runs `jj undo`
- the backend triggers a rebuild
- the modal shows `Undo completed` or a clear failure message

---

## 6. UI specification

### 6.1 Floating button

Requirements:

- fixed position: bottom-right
- visible on every page
- simple label, e.g. `Ops`
- high z-index
- minimal styling

Non-goals:

- fancy animation
- unread badges
- multi-state button behavior

### 6.2 Modal

Requirements:

- centered or bottom-sheet modal
- title: `Obsidian Ops`
- visible current page path
- one textarea
- one Run button
- one Refresh button
- one Undo button
- one output/status area

Recommended fields:

- `Current page: /notes/foo/`
- textarea placeholder: `What would you like to do?`

### 6.3 Input control

Use a plain `<textarea>` in v0.

Do **not** use CodeMirror initially.

Reasons:

- lower JS/CSS complexity
- easier lifecycle handling on page changes
- enough for natural-language requests

### 6.4 Output area

The modal should contain a simple text area or block for:

- waiting text
- success summary
- failure message
- optional list of changed files

This output area does not need structured event rendering.

---

## 7. Browser behavior

### 7.1 Current page context

The browser sends:

- `location.pathname`

Optionally, if already known:

- a vault-relative file path

The browser does not need to capture:

- text selection
- cursor position
- DOM ranges
- highlighted block metadata

### 7.2 Request model

Primary request:

```json
{
  "instruction": "Find related notes and add a short Related section.",
  "current_url_path": "/projects/alpha/meeting-notes/"
}
```

### 7.3 Response model

Suggested response:

```json
{
  "summary": "Added a short Related section with links to 3 notes.",
  "changed_files": [
    "projects/alpha/meeting-notes.md"
  ],
  "created_files": [],
  "history_hint": "ops: Find related notes and add a short Related section"
}
```

### 7.4 Browser flow

1. User opens modal
2. User enters instruction
3. Browser disables input and shows `Running...`
4. Browser sends `POST /api/run`
5. Browser waits
6. Browser renders returned summary or error
7. User chooses refresh or undo

---

## 8. Backend specification

### 8.1 Backend stance

The backend is a thin local orchestration service.

It should:

- accept one generic natural-language request
- infer current file from URL path
- run one tool-using agent loop
- write files atomically
- finalize one Jujutsu change boundary
- rebuild with Kiln if files changed
- return one response

It should **not**:

- expose command-specific endpoints
- persist job metadata in a database
- maintain chat sessions
- run multiple mutations concurrently in v0

### 8.2 Minimal public API

Required:

- `POST /api/run`
- `POST /api/undo`
- `GET /api/history?path=...` (optional but recommended)
- `GET /api/health` (recommended)

Explicitly not required in v0:

- `/api/jobs`
- `/api/jobs/:id/stream`
- `/api/interfaces/*`
- `/api/chat`
- `/api/session`

### 8.3 Run endpoint

`POST /api/run`

Request body:

```json
{
  "instruction": "clean up this note",
  "current_url_path": "/notes/daily/2026-04-06/"
}
```

Behavior:

1. Acquire global mutation lock
2. Resolve current markdown file path from URL
3. Run agent/tool loop
4. If files changed:
   - write atomically
   - `jj commit -m ...`
   - `kiln generate`
   - re-inject overlay if needed
5. Return summary JSON

### 8.4 Undo endpoint

`POST /api/undo`

Behavior:

1. Acquire global mutation lock
2. Run `jj undo`
3. Rebuild site
4. Return success/failure summary

### 8.5 History endpoint

`GET /api/history?path=notes/foo.md`

Behavior:

- return recent Jujutsu-backed history lines for a file

This is useful for debugging and possible future UI affordances, but is not required for the core loop.

---

## 9. Runtime model

### 9.1 No queue in v0

The base version should not use:

- in-memory job queue
- worker pool
- background task scheduler
- SSE subscriber registry

A single blocking request/response model is simpler and sufficient.

### 9.2 Global lock

Use one global async or thread-safe lock around mutation operations.

This ensures:

- one operation at a time
- predictable undo semantics
- simple rebuild sequencing

### 9.3 Failure handling

#### Fail before write

Examples:

- current page path cannot be resolved
- model/tool failure before mutation
- invalid path
- fetch failure before write

Result:

- no file changes
- no Jujutsu commit
- return error response

#### Fail after write but before rebuild

Examples:

- file write succeeds
- Jujutsu commit succeeds
- Kiln rebuild fails

Result:

- vault changes remain durable
- error clearly explains that site output may be stale
- user can still retry rebuild or use undo

---

## 10. Agent/tool model

### 10.1 Interaction style

The backend should use one general-purpose natural-language agent loop.

There is no command registry.

### 10.2 Minimal tool set

Recommended:

- `read_file(path)`
- `write_file(path, content)`
- `list_files(glob="**/*.md")`
- `search_files(query, glob="**/*.md")`
- `fetch_url(url)`
- `get_file_history(path, limit=10)`

Undo can remain an app-level endpoint rather than an agent tool in the base UI.

### 10.3 Prompt posture

System rules should stay small and general:

- preserve YAML frontmatter unless asked to change it
- preserve wikilinks unless asked to change them
- prefer minimal edits
- do not delete content unless clearly intended
- summarize changes at the end

### 10.4 Result format

The backend should always return:

- `summary`
- `changed_files`
- `created_files`
- optional `history_hint`

---

## 11. Forge integration

### 11.1 Role of Forge

Forge should remain a host shell, not a business-logic layer.

Forge responsibilities:

- serve rendered pages
- inject or host overlay assets
- proxy `/api/*` to the local backend

### 11.2 Same-origin API pattern

The browser should call same-origin endpoints like:

- `POST /api/run`
- `POST /api/undo`

Forge forwards those to the local vault backend.

This is preferred because:

- no CORS complexity
- browser does not need to know backend port
- one trusted local entrypoint on Tailscale

### 11.3 Overlay hosting

Recommended assets:

- `/ops/ops.js`
- `/ops/ops.css`

These can be injected into generated HTML after each Kiln build.

---

## 12. Suggested file structure

```text
forge-or-ops/
  app.py
  agent.py
  tools.py
  history_jj.py
  rebuild.py
  inject.py
  page_context.py
  fs_atomic.py
  static/
    ops.js
    ops.css
```

No need in the base version for:

- queue.py
- jobs.py
- interfaces/
- chat_sessions.py
- websockets.py
- plugin registries

---

## 13. Acceptance criteria

The interface is correct when all of the following are true:

1. The user can browse the rendered vault normally.
2. A floating button appears on every page.
3. Clicking it opens one modal.
4. The modal shows the current page path.
5. The user can type one natural-language request.
6. Submitting sends one blocking request to the backend.
7. The backend can mutate files safely.
8. Successful changes are recorded in Jujutsu.
9. The site rebuilds after successful mutation.
10. The modal shows a short summary.
11. The user can refresh.
12. The user can undo confidently.

---

## 14. Explicit non-goals

Do not add these in the base version:

- tabbed interfaces
- chat mode vs command mode
- CodeMirror
- selection capture
- selection toolbar
- live DOM patching after edits
- SSE progress streaming
- websocket transport
- job queue
- per-file concurrency
- database-backed state
- command-specific public endpoints

---

## 15. Upgrade path

Only add complexity in this order if needed:

### Stage 1

Base version:

- one modal
- one textarea
- blocking `POST /api/run`
- global lock
- rebuild + refresh

### Stage 2

If waiting feels too opaque:

- add SSE progress to `POST /api/jobs` + stream endpoint
- still keep one interface only

### Stage 3

If input needs more power:

- replace textarea with CodeMirror
- keep same backend contract

### Stage 4

If true multi-mode interaction becomes necessary:

- add distinct interface types
- only after real product pressure appears

This order protects simplicity.

---

## 16. Final recommendation

Build the interface as the smallest useful loop:

**floating button → modal → textarea → POST /api/run → wait → summary → refresh or undo**

That is the most simplified viable interface.

It is compatible with:

- Forge as a thin host/proxy
- Kiln as renderer
- Jujutsu as durable history
- a local single-user Tailscale deployment

And it avoids premature complexity in exactly the areas most likely to sprawl:

- interface architecture
- transport architecture
- frontend editor complexity
- backend job orchestration
