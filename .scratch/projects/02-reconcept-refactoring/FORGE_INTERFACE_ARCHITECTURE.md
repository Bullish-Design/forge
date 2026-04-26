# Forge-Based Multi-Interface Overlay Architecture

## 1. Document Status

- Status: Proposed architecture
- Product: Forge-based interface layer for Obsidian Ops
- Variant: Simplified local-first single-user architecture
- Audience:
  - maintainers of Forge integration
  - implementers of the browser overlay and local backend
  - future contributors extending UI modes beyond the initial command surface

---

## 2. Purpose

This document defines a refined interface architecture for building a **multi-interface operations shell** on top of the `Bullish-Design/forge` repository shape while staying aligned with the canonical simplified Obsidian Ops direction.

The goal is to preserve the strengths of the existing simplified product model:

- local-first deployment
- one trusted user on a secure Tailscale network
- direct interaction with a local vault runtime
- natural-language operations against markdown files
- durable recovery through Jujutsu

while improving the UI model from a single modal into a **generic, extensible interface shell**.

The proposed design keeps Forge thin. Forge remains the host and transport layer. The actual product value lives in an injected browser overlay and a small local backend.

---

## 3. Executive Summary

The recommended architecture is:

1. **Forge remains the host**
   - serve Kiln-rendered content
   - serve overlay assets
   - proxy `/api/*` requests to a local backend

2. **A persistent launcher lives in the bottom-right corner**
   - always visible
   - opens the operations shell
   - becomes the single durable affordance across all rendered pages

3. **The operations shell is generic**
   - one shared container
   - multiple interface modes inside it
   - bottom tab bar for switching between modes

4. **Command mode is the default first interface**
   - large CodeMirror-backed input area
   - current page context attached automatically
   - natural-language task submission

5. **Chat mode is a sibling interface, not a separate app**
   - same shell
   - same session context
   - conversation continues from command execution history

6. **Input flows through Forge to a local backend**
   - browser calls same-origin `/api/*`
   - Forge proxies to a localhost service on the vault machine
   - backend runs agent, tool loop, history, and rebuild flows

7. **Transport should be POST + SSE in v1**
   - POST for submissions
   - Server-Sent Events for streaming status and results
   - WebSockets deferred until bidirectional live sync is actually needed

This preserves the simplified architecture’s mental model while giving the UI room to grow.

---

## 4. Architectural Drivers

### 4.1 Keep Forge thin

Forge appears to be strongest when treated as a thin shell around Kiln development and site serving, with added overlay injection, static asset serving, and API proxying rather than as the place where all application logic should live.

### 4.2 Keep the user interaction model simple

The user should still feel like there is one obvious entry point:

- one launcher
- one shell
- one current context
- one stream of progress and results

The shell may host many interfaces, but the product should still feel singular.

### 4.3 Allow interface expansion without architecture churn

The first iteration may only need:

- Command
- Chat

But the shell should be able to support future interfaces such as:

- Diff
- Review
- Run log
- Search/jump
- Context inspector
- Template-driven actions

without redesigning the transport or layout.

### 4.4 Stay aligned with simplified Obsidian Ops canon

The canonical simplified direction says the product is local-first, thin, file-native, and centered around natural-language instructions, generic job submission, SSE progress, and Jujutsu-backed recovery. fileciteturn0file1L7-L13 fileciteturn0file2L31-L38

This proposal should extend that direction, not replace it.

### 4.5 Prefer same-origin simplicity

Because the system is intended for one user on a trusted Tailscale network, the architecture should optimize for:

- simple routing
- minimal auth complexity
- minimal CORS complexity
- clear debugging
- minimal moving parts

---

## 5. Top-Level System Shape

```text
Browser
  ├─ Kiln-rendered page
  ├─ persistent bottom-right launcher
  └─ injected operations shell
        ├─ Command interface
        ├─ Chat interface
        └─ future interfaces
             │
             │ same-origin /api/*
             ▼
Forge host layer
  ├─ serves rendered site
  ├─ serves overlay assets
  ├─ injects overlay into pages
  └─ reverse proxies /api/* to local backend
             │
             ▼
Local backend service
  ├─ session/context handling
  ├─ generic interface registry
  ├─ job submission endpoints
  ├─ SSE streaming endpoints
  ├─ agent + tool loop
  ├─ Jujutsu history/undo wrapper
  └─ Kiln rebuild orchestration
             │
             ├─ Obsidian vault
             ├─ Jujutsu workspace
             └─ generated site output
```

This preserves the simplified product’s browser → server → vault structure while replacing the single-modal UI surface with a generic interface shell. The simplified concept already centers the system on browser, server, and vault, with SSE updates and Jujutsu-backed recovery. fileciteturn0file0L28-L48

---

## 6. UX Model

## 6.1 Persistent launcher

A single floating button remains visible in the bottom-right corner of every page.

Responsibilities:

- open the shell
- indicate busy/running state
- optionally show unread result or failure badge state later
- remain stable across page navigations and swaps

This preserves the strongest aspect of the simplified concept: one obvious entry point from any page. fileciteturn0file0L55-L63

## 6.2 Operations shell

When activated, the launcher opens a shared shell.

Recommended shell forms:

- **desktop default:** right-side drawer
- **narrow screens:** bottom sheet
- **expanded mode:** near-fullscreen panel

The shell should not fully replace the rendered page DOM in v1. Instead, it should sit above it.

Why:

- avoids fighting with page navigation/rendering behavior
- preserves scroll position and reading context
- supports quick switching between interfaces
- makes it easier to add future interfaces without rewriting the page layout

## 6.3 Interface tabs

A bottom tab strip switches between registered interfaces.

Initial tabs:

- Command
- Chat

Possible future tabs:

- Diff
- Review
- Runs
- Context

These tabs should come from a registry, not be hardcoded as a one-off command/chat toggle.

## 6.4 Default behavior

When opened:

- shell focuses the **Command** interface by default
- current page path is captured automatically
- current selection, if present, is attached as optional context
- previous draft for that page/session may be restored

This keeps the interaction fast and page-aware, which matches the simplified product’s requirement that current page context be automatic. fileciteturn0file2L96-L104

---

## 7. Interface Model

## 7.1 Shared shell, pluggable interfaces

The shell should expose one host contract and allow individual interface modules to plug into it.

Example conceptual contract:

```ts
export type InterfacePlugin = {
  id: string
  label: string
  icon?: string
  mount(container: HTMLElement, ctx: InterfaceContext): void
  unmount?(): void
  serializeDraft?(): unknown
  restoreDraft?(draft: unknown): void
  onSelectionChange?(selection: PageSelection | null): void
}
```

This gives the system a stable abstraction boundary:

- shell owns layout and session wiring
- plugins own rendering and input semantics

## 7.2 Shared interface context

Every interface should receive a common context object.

```ts
export type InterfaceContext = {
  sessionId: string
  currentPagePath: string
  currentUrlPath: string
  currentSelection?: {
    text: string
    from?: number
    to?: number
  }
  api: ApiClient
  publishEvent: (event: ShellEvent) => void
}
```

This ensures that Command, Chat, and future interfaces all operate on the same current state.

## 7.3 Shared run history

The shell should maintain a session-level run timeline.

Benefits:

- Command can submit a task
- Chat can immediately discuss the result
- Diff can show what changed for the same run
- Review can show approval or undo affordances

This is more useful than separate disconnected UI surfaces.

---

## 8. Command Interface

## 8.1 Role

The Command interface is the primary work surface.

It should feel like:

- a large, focused editor
- natural-language first
- capable of holding longer structured prompts or multi-step requests
- contextualized by the current note/page

## 8.2 Editor choice

Use **CodeMirror** or an equivalent structured text editor.

Why CodeMirror is a good fit:

- robust multiline editing
- clean keyboard behavior
- future syntax highlighting for slash-commands or structured prompt blocks
- extensibility for chips, file refs, or context markers later

## 8.3 Recommended behavior

- auto-focus when Command tab opens
- `Cmd/Ctrl+Enter` submits
- draft preserved per page/session
- optional insertion of current selection into the editor
- optional page-context pill shown above editor

## 8.4 Submission contract

Command mode should submit to a generic endpoint, not a command-specific endpoint.

Example payload:

```json
{
  "interface_id": "command",
  "session_id": "sess_123",
  "page": {
    "url_path": "/projects/alpha/",
    "file_path": "Projects/Alpha.md"
  },
  "selection": {
    "text": "Selected text from page"
  },
  "input": {
    "text": "Clean up this note and add related links"
  }
}
```

That stays aligned with the canonical preference for generic job submission rather than command-specific public APIs. fileciteturn0file1L66-L77

---

## 9. Chat Interface

## 9.1 Role

Chat is not a separate app. It is a sibling interface inside the same shell.

Its purpose is to:

- continue conversation after a command run
- ask follow-up questions
- explain changes
- refine next actions
- expose an easier conversational surface than the larger command editor

## 9.2 Shared session continuity

Chat should inherit:

- current page context
- recent command history
- recent tool/result summaries
- same session id

This allows a seamless flow like:

1. Command: “Create a summary note from this page.”
2. Chat: “Why did you include that section?”
3. Chat: “Now shorten it.”

## 9.3 Rendering model

Keep it simple in v1:

- scrollable message list
- single composer input
- streaming assistant responses
- optional “Use current page” context indicator

---

## 10. Future Interface Candidates

The shell should support additional interfaces without transport redesign.

### 10.1 Diff

Shows:

- files changed
- markdown diff summary
- restore/undo action

This fits well with the simplified system’s emphasis on history, changes, restore, and undo. fileciteturn0file1L100-L111

### 10.2 Review

Shows:

- summary of pending or last-applied actions
- accept/undo/continue options
- likely next actions

### 10.3 Run log

Shows:

- readable job or run timeline
- tool-use summaries
- rebuild state
- errors

### 10.4 Context inspector

Shows:

- current page path
- extracted context
- selected text
- related files chosen by the backend

These can all be layered in later without changing the core shell contract.

---

## 11. Transport Architecture

## 11.1 Recommended request path

Use:

**Browser overlay → same-origin `/api/*` → Forge reverse proxy → localhost backend**

This is the recommended path because it:

- avoids CORS complexity
- keeps the browser unaware of backend port details
- keeps Forge as the single network entrypoint
- matches the existing simplified product posture of a small server around the rendered site and API routes. fileciteturn0file0L38-L48

## 11.2 Why not direct browser-to-backend calls

Avoid in v1:

- exposing a second browser-visible service port
- duplicating routing/configuration logic
- making the frontend reason about backend origin or connectivity

For a single-user secure local network, same-origin proxying is the cleanest choice.

## 11.3 API posture

Keep the public API generic and interface-aware.

Suggested endpoints:

- `GET /api/interfaces`
- `POST /api/interfaces/:id/submit`
- `POST /api/chat/message` or `POST /api/interfaces/chat/submit`
- `GET /api/runs/:run_id/events`
- `GET /api/session`
- `POST /api/session/context`
- `POST /api/undo`
- `GET /api/history`

This keeps the interface layer generic while still fitting the simplified API philosophy: small, generic, and progress-streamed. fileciteturn0file2L222-L245

---

## 12. Streaming Model

## 12.1 Recommendation: POST + SSE

Use:

- **POST** for request submission
- **SSE** for streaming progress and results

This is the best v1 tradeoff because it is:

- simple to implement
- easy to debug
- already aligned with the simplified Obsidian Ops design, which uses SSE as the canonical progress transport. fileciteturn0file1L35-L39 fileciteturn0file2L247-L252

## 12.2 Example event types

Recommended event families:

- `status`
- `tool`
- `message`
- `result`
- `error`
- `done`

Interfaces may render the same stream differently:

- Command shows structured progress
- Chat converts model output into message bubbles
- Run log shows raw timeline

## 12.3 Why not WebSockets first

Defer WebSockets until you need:

- bidirectional low-latency collaborative state
- simultaneous live editing and server push
- more complex shell synchronization

For one user on a secure local network, SSE is enough.

---

## 13. Session Model

## 13.1 Session purpose

The shell should maintain a lightweight session concept.

A session groups:

- current page context
- interface drafts
- recent runs
- recent outputs
- undo/history affordances

## 13.2 Recommended state shape

```ts
export type ShellState = {
  open: boolean
  expanded: boolean
  activeInterfaceId: string
  sessionId: string
  currentUrlPath: string
  currentFilePath?: string
  currentSelectionText?: string
  currentRunId?: string
}
```

## 13.3 Scope

In v1, session state can remain lightweight and primarily in-memory on the client, with only the backend state needed to support current runs and conversation continuity.

This remains compatible with the simplified architecture’s acceptance of in-memory runtime state for transient job/session handling. fileciteturn0file1L34-L39

---

## 14. Backend Architecture

## 14.1 Backend role

The local backend remains the real orchestration layer.

Responsibilities:

- resolve current page context
- accept interface submissions
- run agent/tool loops
- publish SSE events
- record history with Jujutsu
- trigger Kiln rebuilds
- expose undo/history

## 14.2 Interface-aware but not interface-owned

The backend should know which interface submitted an action, but it should not become tightly coupled to frontend implementation details.

Use an interface-aware request envelope instead of bespoke handler sprawl.

## 14.3 Preserve simplified core behaviors

The backend should still preserve the important simplified traits:

- natural-language operations
- generic tool-use agent loop
- in-memory job/runtime model for transient work
- Jujutsu as durable history layer
- coarse rebuilds after successful mutation

Those are canonical in the current simplified direction. fileciteturn0file2L37-L45 fileciteturn0file3L54-L63

---

## 15. Page Context and Selection Handling

## 15.1 Automatic page context

The backend should infer or receive the current markdown path for the rendered page automatically.

This remains a core requirement from the simplified architecture. fileciteturn0file2L96-L104

## 15.2 Selection as optional context, not primary UI

Do **not** build the product around a selection toolbar in v1.

Instead:

- selection is optional metadata attached to the current session or submission
- interfaces may choose to surface it
- the launcher and shell remain the primary product surface

This respects the canonical simplified non-goal of a selection-toolbar editing flow. fileciteturn0file1L31-L33

---

## 16. Browser Implementation Notes

## 16.1 Overlay strategy

The shell should be injected as lightweight assets served by Forge.

Recommended assets:

- `forge_ops.css`
- `forge_ops.js`

The overlay should:

- create and maintain the launcher
- create the shared shell container
- bind to page navigation/swaps
- register and mount interface plugins
- manage current session state
- speak to same-origin API endpoints

## 16.2 Navigation tolerance

Because Kiln-style rendered sites may use page swaps or partial navigations, the overlay should tolerate page replacement and rebind itself when necessary.

## 16.3 Progressive enhancement posture

The rendered site remains usable without the shell.

The shell is an enhancement layer, not a requirement for reading or navigation.

---

## 17. Component Boundaries

## 17.1 Forge host layer

Responsible for:

- site serving
- overlay asset serving
- HTML injection
- reverse proxying `/api/*`

## 17.2 Overlay shell

Responsible for:

- persistent launcher
- shell layout and expansion modes
- interface tabs
- session state
- stream subscription orchestration

## 17.3 Interface plugins

Responsible for:

- rendering mode-specific controls
- draft serialization/restoration
- formatting their submissions
- rendering events/results in interface-specific ways

## 17.4 Local backend

Responsible for:

- request validation
- page context resolution
- agent runtime
- tool execution
- history/undo
- rebuild flows
- SSE event publication

These boundaries keep the system understandable and extensible.

---

## 18. Recommended V1 Decisions

### 18.1 Build a shell, not a page takeover

Do not literally convert the whole page body into an input surface.

Instead, use a shell that can *feel* immersive when expanded.

### 18.2 Make Command the first-class default

Command mode should open first and feel like the primary product surface.

### 18.3 Keep Chat in the same shell

Do not split Chat into a separate route or app.

### 18.4 Keep transport same-origin and generic

Use Forge `/api/*` proxying to a localhost backend.

### 18.5 Use POST + SSE

This is the simplest robust first version.

### 18.6 Preserve simplified backend principles

Do not reintroduce:

- command-specific public API sprawl
- selection-toolbar UX as core behavior
- database-backed job systems
- a second durability layer parallel to Jujutsu

---

## 19. Risks and Tradeoffs

## 19.1 More UI flexibility means slightly more frontend complexity

Moving from a single modal to a shell with tabs and pluggable interfaces adds browser complexity.

Mitigation:

- keep the shell registry small
- keep initial interface count low
- avoid a heavyweight SPA router

## 19.2 Chat and Command can drift into separate products

If implemented carelessly, Command and Chat could behave like unrelated tools.

Mitigation:

- enforce shared session context
- share run history
- share current page context

## 19.3 Generic interfaces can encourage backend sprawl

If every interface invents its own endpoint family, the backend will drift.

Mitigation:

- standardize on a generic interface submission envelope
- centralize event streaming

---

## 20. Implementation Sequence

Recommended order:

1. Confirm Forge overlay injection and `/api/*` proxy wiring
2. Add persistent launcher asset
3. Build shell container and expansion behavior
4. Add interface registry
5. Implement Command plugin with CodeMirror
6. Add generic submit endpoint and SSE event stream
7. Implement Chat plugin sharing same session state
8. Add run history panel/state
9. Add optional Diff/Review interfaces later

This sequence gets the core user experience working early without overbuilding.

---

## 21. Final Recommendation

Build the Forge-based interface layer as a **generic multi-interface shell** with:

- one persistent launcher
- one shared shell container
- Command as the default interface
- Chat as a sibling interface
- future interfaces mounted via a registry
- same-origin `/api/*` calls through Forge’s proxy
- POST for submission
- SSE for progress and results
- a local backend that preserves the simplified Obsidian Ops model of generic intent submission, agent/tool execution, Jujutsu-backed recovery, and rebuild after successful mutation. fileciteturn0file0L74-L84 fileciteturn0file2L322-L327

In product terms, the recommended loop becomes:

**browse page → click persistent launcher → open shell → work in Command or Chat → stream progress/results → refresh, continue, or undo**

That is the cleanest evolution of the simplified product shape into a more extensible UI architecture.
