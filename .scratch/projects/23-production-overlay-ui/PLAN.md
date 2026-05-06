# Implementation Plan — Production Overlay UI

## Overview
Build a production-ready overlay UI that provides agent interaction and LLM logging capabilities. Distinct from the demo overlay; leaves demo untouched. Deliverable is a reusable JS/CSS bundle injectable into any forge-served page.

## Phase 1: Design & Analysis (UI/UX)

### 1.1 Study Current Demo Overlay
- **Goal**: Understand current overlay structure, injection pattern, styling approach
- **Approach**: Examine forge-overlay package code (in venv or source)
- **Deliverable**: Diagram of injection pattern, CSS structure, event flow
- **Owner**: -
- **Blocked by**: -

### 1.2 Design Production UI Components
- **Goal**: Wireframe the button, modal, log viewer
- **Scope**:
  - Button: small corner placement, icon/label, hover state
  - Modal: header (title, close), body (log viewer + agent tools), footer (reload button)
  - Log viewer: list of requests, collapsible headers per request, copyable response
- **Deliverable**: ASCII mockups or design doc with CSS classes/structure
- **Owner**: -
- **Blocked by**: 1.1

### 1.3 Design Log Capture Strategy
- **Goal**: Determine how to intercept LLM request/response data
- **Options**:
  - (A) Monkey-patch `fetch()` globally to intercept `/api/agent/*` calls
  - (B) Custom logging injected into obsidian-agent responses (backend)
  - (C) Parse `/api/agent/status` responses for historical logs
- **Decision needed**: Pick (A), (B), or (C) + rationale
- **Deliverable**: Log capture design doc
- **Owner**: -
- **Blocked by**: -

## Phase 2: Core Implementation (Frontend Bundle)

### 2.1 Create Project Structure
- **Goal**: Set up new frontend project directory
- **Deliverable**: `/src/forge_overlay_production/` with `index.html`, `button.js`, `modal.js`, `logger.js`, `styles.css`
- **Owner**: -
- **Blocked by**: -

### 2.2 Implement Button Component
- **Goal**: Small clickable corner button that toggles modal
- **Scope**:
  - HTML: Single root element, icon or text label
  - CSS: positioning, hover/active states, small footprint
  - JS: toggle modal visibility, persist state (localStorage)
- **Deliverable**: Functional button with toggle
- **Owner**: -
- **Blocked by**: 2.1

### 2.3 Implement Modal Component
- **Goal**: Popup container with header, body, footer
- **Scope**:
  - HTML: semantic structure (dialog or div role="dialog")
  - CSS: centered, responsive, dark mode support, shadow/backdrop
  - JS: open/close, clickoutside to close, ESC key
- **Deliverable**: Functional modal (content TBD)
- **Owner**: -
- **Blocked by**: 2.1

### 2.4 Implement Log Viewer Component
- **Goal**: Display captured LLM request/response logs
- **Scope**:
  - HTML: log list, collapsible sections per request
  - CSS: readable code formatting, syntax highlighting (optional)
  - JS: render log data, toggle visibility, copy-to-clipboard
- **Deliverable**: Log viewer that renders mock log data
- **Owner**: -
- **Blocked by**: 2.3

### 2.5 Implement Log Capture (fetch intercept)
- **Goal**: Capture `/api/agent/*` calls and parse LLM logs
- **Scope**:
  - Monkey-patch global `fetch()` to log API calls
  - Parse response for token count, model, timing
  - Store in in-memory log array
  - Update log viewer when new calls arrive
- **Deliverable**: Working log capture + viewer
- **Owner**: -
- **Blocked by**: 2.4

### 2.6 Implement Agent Tools in Modal
- **Goal**: Quick-action buttons for common agent operations
- **Scope**:
  - Buttons: apply/undo, reload page, sync status
  - Handlers: POST to `/api/agent/apply`, `/api/agent/undo`, etc.
  - Feedback: show result modals or toast notifications
- **Deliverable**: Functional agent tools
- **Owner**: -
- **Blocked by**: 2.3

### 2.7 Implement Page Reload
- **Goal**: Allow reload from modal without closing UI
- **Scope**:
  - Button in modal footer that calls `location.reload()`
  - Preserve modal state if possible (localStorage)
- **Deliverable**: Working reload button
- **Owner**: -
- **Blocked by**: 2.3

### 2.8 Build Injection Bundle
- **Goal**: Package button + modal + logger as single injectable script/style
- **Deliverable**: `bundle.js` and `bundle.css` that inject full UI on load
- **Owner**: -
- **Blocked by**: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7

## Phase 3: Integration & Deployment

### 3.1 Integrate with `forge dev` Command
- **Goal**: Inject production overlay into dev mode alongside demo overlay
- **Approach**: Modify processes.py `start_overlay()` to include production bundle
- **Deliverable**: Updated overlay startup to serve both demo + production overlays
- **Owner**: -
- **Blocked by**: 2.8

### 3.2 Docker Integration
- **Goal**: Ensure production overlay is baked into docker build
- **Approach**: Copy bundle files into Docker image, inject into forge config
- **Deliverable**: Updated Dockerfile to include production overlay bundle
- **Owner**: -
- **Blocked by**: 2.8

### 3.3 Testing & Validation
- **Goal**: Verify functionality in both dev and docker modes
- **Scope**:
  - Button appears and toggles modal
  - Logs capture real API calls
  - Log viewer displays correctly
  - Agent tools (apply/undo) work
  - Page reload works from modal
  - No visual conflicts with demo overlay
- **Deliverable**: Test plan + validated screenshot/demo
- **Owner**: -
- **Blocked by**: 3.1, 3.2

### 3.4 Documentation
- **Goal**: Document production overlay usage and customization
- **Deliverable**: README with setup, usage, styling customization
- **Owner**: -
- **Blocked by**: 3.3

## Success Criteria
- ✅ Production overlay button and modal functional
- ✅ LLM logs captured and displayed
- ✅ Agent tools (apply/undo) callable from modal
- ✅ Page reload works from modal
- ✅ Works in `forge dev` mode
- ✅ Works in Docker production build
- ✅ Demo overlay untouched
- ✅ No visual conflicts
- ✅ Documented and ready for use

## Dependencies
- forge-overlay (existing) — we're building alongside, not replacing
- obsidian-agent API endpoints — standard `/api/*` routes
