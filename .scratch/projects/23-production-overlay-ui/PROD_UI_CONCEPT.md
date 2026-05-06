# Production Overlay UI — Concept & Recommendation

## Senior Review of Intern's Plan

The intern did solid design work in Phase 1. The analysis of the demo overlay, log capture options, and UI wireframes are thorough. But there are architectural issues and unnecessary complexities that would cause problems in implementation.

### What the Intern Got Right

1. **Log capture strategy (Option A)** — Fetch intercept is the correct choice. No backend dependencies, can start immediately, and the migration path to richer metadata later is clean.

2. **UI concept** — Button-to-modal interaction model is good. The dark slate theme reuse is sensible.

3. **Component breakdown** — Identifying button, modal, log viewer, and agent tools as distinct concerns is reasonable for design, even if the implementation shouldn't be split across files.

### Problems with the Intern's Plan

**Problem 1: Over-engineered file structure**

The intern planned 6 JavaScript files: `button.js`, `modal.js`, `logger.js`, `ops-production.js`, `ops-production.css`, `index.html`. The demo overlay is 80 lines of JS and 87 lines of CSS — two files total. There's no bundler, no module system, no build step. The injection middleware hardcodes:

```
<link rel="stylesheet" href="/ops/ops.css">
<script type="module" src="/ops/ops.js">
```

Multiple files means either:
- A build step to bundle them (complexity for no gain), or
- Multiple script tags injected (requires modifying inject.py — out of scope), or
- Dynamic imports from ops.js (fragile, CORS issues, path resolution problems)

The production overlay should be **two files**: `ops.js` and `ops.css`, just like the demo.

**Problem 2: Source directory in the wrong place**

The intern created `/src/forge_overlay_production/` — a Python source directory for what is purely a frontend bundle. This is vanilla JS + CSS that gets served as static files.

Correct location: **`src/overlay/`** — sits alongside other source code but is clearly a standalone frontend asset directory, not a Python package.

**Problem 3: No clear integration path**

The plan mentions "Integrate with `forge dev` command" as a Phase 3 task but doesn't explain the mechanism. The integration is trivial and already solved: `forge.yaml` has `overlay_dir` which points at the directory containing `ops.js` and `ops.css`. To switch between demo and production:

```yaml
# Demo mode
overlay_dir: demo/overlay

# Production mode
overlay_dir: src/overlay
```

No code changes to forge-overlay, inject.py, or processes.py needed.

**Problem 4: Unnecessary complexity in the modal design**

Minimize/maximize buttons, multiple collapsible sections, virtual scrolling, sessionStorage/localStorage split — over-designed for a debugging tool.

**Problem 5: `current_file` is hardcoded**

The demo overlay hardcodes `"projects/forge-v2.md"` as the target file. The intern's design includes a file input field, which is good, but the plan doesn't address how to detect the current page's corresponding vault file.

**Problem 6: Modal positioning**

The intern's design anchors the panel to the bottom-right corner (like the demo). A centered modal is better — it's the standard pattern for modal dialogs, works equally well on desktop and mobile, and avoids the panel getting cramped against a screen edge on narrow viewports.

---

## My Recommendation: Evolutionary Approach

Instead of building from scratch with 6 files and a complex component architecture, **evolve the demo overlay into the production overlay** in a single `ops.js` + `ops.css` pair.

### Core Insight

The demo overlay already does 90% of what we need:
- SSE connection for rebuild events
- Health check, apply, undo API calls
- JSON response display
- Dark theme, z-index layering

The production overlay adds:
- Floating button → centered modal toggle
- Fetch intercept logging (wrap existing `fetch` calls)
- Current file detection (derive from URL path)
- Page reload button
- Responsive layout (desktop + mobile)

### Architecture

```
src/overlay/
├── ops.js    (~250-350 lines, single IIFE)
└── ops.css   (~250-300 lines)
```

No build step. No modules. No bundler. Works with the existing injection middleware unchanged.

### UI Layout

#### Floating Button (closed state)

Fixed bottom-right corner. Small, circular, unobtrusive. Visible on all screen sizes.

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│                  Page Content                       │
│                                                     │
│                                                     │
│                                                 [⚙] │  ← 44px circle, fixed
└─────────────────────────────────────────────────────┘
```

- 44px diameter (meets mobile touch target minimum)
- `position: fixed; bottom: 16px; right: 16px`
- Dark background, subtle border, gear or anvil icon
- Badge indicator when new log entries arrive while closed

#### Modal (open state) — Desktop (≥640px)

Centered overlay with backdrop. Standard modal pattern.

```
┌─────────────────────────────────────────────────────┐
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│ ░░░░┌──────────────────────────────────────┐░░░░░░░ │
│ ░░░░│ Forge                            [✕] │░░░░░░░ │
│ ░░░░├──────────────────────────────────────┤░░░░░░░ │
│ ░░░░│                                      │░░░░░░░ │
│ ░░░░│ File: projects/forge-v2.md       [✎] │░░░░░░░ │
│ ░░░░│                                      │░░░░░░░ │
│ ░░░░│ ┌──────────────────────────────┐     │░░░░░░░ │
│ ░░░░│ │ Add a concise update...      │     │░░░░░░░ │
│ ░░░░│ │                              │     │░░░░░░░ │
│ ░░░░│ └──────────────────────────────┘     │░░░░░░░ │
│ ░░░░│ [Send] [Undo] [Health]               │░░░░░░░ │
│ ░░░░│                                      │░░░░░░░ │
│ ░░░░│ ▸ Logs (3)                           │░░░░░░░ │
│ ░░░░│                                      │░░░░░░░ │
│ ░░░░│ Response                             │░░░░░░░ │
│ ░░░░│ ┌──────────────────────────────┐     │░░░░░░░ │
│ ░░░░│ │ { "ok": true, ... }          │     │░░░░░░░ │
│ ░░░░│ └──────────────────────────────┘     │░░░░░░░ │
│ ░░░░│                                      │░░░░░░░ │
│ ░░░░│ SSE: connected (3 events)            │░░░░░░░ │
│ ░░░░│                     [Reload Page]    │░░░░░░░ │
│ ░░░░└──────────────────────────────────────┘░░░░░░░ │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
└─────────────────────────────────────────────────────┘
  ░ = semi-transparent backdrop
```

- Modal: `max-width: 480px; width: 90vw; max-height: 80vh`
- Centered: `position: fixed; inset: 0; margin: auto` (with flexbox centering on the backdrop)
- Scrollable body, fixed header/footer
- Backdrop click or ESC closes modal

#### Modal (open state) — Mobile (<640px)

Full-width sheet rising from bottom. Native-feeling on phones.

```
┌──────────────────────────┐
│ ░░░░░░░░░░░░░░░░░░░░░░░░ │
│ ░░░░░░░░░░░░░░░░░░░░░░░░ │
│ ░░░░░░░░░░░░░░░░░░░░░░░░ │
├──────────────────────────┤
│ Forge                [✕] │
├──────────────────────────┤
│ File: projects/for.. [✎] │
│                          │
│ ┌──────────────────────┐ │
│ │ Add a concise upda.. │ │
│ │                      │ │
│ └──────────────────────┘ │
│ [Send] [Undo] [Health]   │
│                          │
│ ▸ Logs (3)               │
│                          │
│ Response                 │
│ ┌──────────────────────┐ │
│ │ { "ok": true, ... }  │ │
│ └──────────────────────┘ │
│                          │
│ SSE: connected           │
│            [Reload Page] │
└──────────────────────────┘
```

- `width: 100%; max-height: 85vh; border-radius: 12px 12px 0 0`
- Anchored to bottom: `align-self: flex-end` within the backdrop flex container
- No side margins on mobile — full bleed

### Implementation Design

#### ops.js Structure

```javascript
(() => {
  // ── State ──────────────────────────────────────────
  const state = {
    open: localStorage.getItem('forge-panel-open') === 'true',
    logs: [],
    maxLogs: 50,
    logsExpanded: false,
    expandedLogIds: new Set(),
    unseenLogs: 0,
  };

  // ── Fetch Intercept ────────────────────────────────
  // Wrap window.fetch to capture /api/* calls
  // Clone response, measure duration, store in state.logs
  // Cap at state.maxLogs entries (FIFO)
  // Increment state.unseenLogs when modal is closed

  // ── Current File Detection ─────────────────────────
  // Derive vault path from current URL:
  //   /projects/forge-v2  →  projects/forge-v2.md
  //   /                   →  index.md
  // Allow manual override via input field

  // ── DOM Construction ───────────────────────────────
  // 1. Trigger button (fixed, bottom-right, 44px circle)
  // 2. Backdrop (fixed, full viewport, semi-transparent)
  // 3. Modal (centered on backdrop via flexbox)
  //    - Header: "Forge" + close button
  //    - Body (scrollable):
  //      - File path display + edit toggle
  //      - Prompt textarea (instruction to send to agent)
  //      - Action buttons: send (apply), undo, health
  //      - Logs section: collapsible, reverse-chronological
  //      - Response output: pre block
  //      - SSE status line
  //    - Footer: reload page button

  // ── API Helpers ────────────────────────────────────
  // Same as demo: postJson(), health check, apply, undo
  // Routed through the fetch intercept automatically

  // ── SSE Connection ─────────────────────────────────
  // Same as demo: EventSource to /ops/events

  // ── Event Handlers ─────────────────────────────────
  // Button click → open modal, clear unseenLogs
  // Backdrop click → close modal
  // ESC key → close modal
  // Close button → close modal
  // Log entry click → expand/collapse details
  // Reload button → location.reload() (panel state persists via localStorage)
})();
```

#### Key Differences from Demo

| Aspect | Demo | Production |
|--------|------|------------|
| **Visibility** | Always visible side panel | Hidden behind floating button |
| **Modal style** | Fixed bottom-right panel | Centered modal with backdrop |
| **Panel size** | 320px fixed width | 480px max, responsive |
| **Mobile** | Cramped at 320px | Full-width bottom sheet |
| **Prompt input** | Textarea, hardcoded default | Textarea with send button, same default |
| **File target** | Hardcoded `projects/forge-v2.md` | Auto-detected from URL, editable |
| **Logging** | None | Fetch intercept captures all `/api/*` calls |
| **Log display** | Just last response in `<pre>` | Scrollable log list with expand/collapse |
| **Reload** | Not available | Button in footer |
| **State persistence** | None | Panel open/closed in localStorage |

#### Fetch Intercept Implementation

```javascript
const originalFetch = window.fetch;
let logId = 0;

window.fetch = async function (...args) {
  const [resource, options] = args;
  const url = typeof resource === 'string' ? resource : resource.url;

  if (!url.includes('/api/')) {
    return originalFetch.apply(this, args);
  }

  const entry = {
    id: ++logId,
    timestamp: Date.now(),
    method: options?.method || 'GET',
    url,
    request: null,
    response: null,
    duration_ms: 0,
    status: 0,
    error: null,
  };

  // Capture request body
  if (options?.body) {
    try { entry.request = JSON.parse(options.body); } catch { entry.request = options.body; }
  }

  const start = performance.now();
  try {
    const response = await originalFetch.apply(this, args);
    entry.duration_ms = Math.round(performance.now() - start);
    entry.status = response.status;

    // Clone and capture response body
    const clone = response.clone();
    clone.text().then(text => {
      try { entry.response = JSON.parse(text); } catch { entry.response = text; }
      renderLogs();
    });

    addLog(entry);
    return response;
  } catch (err) {
    entry.duration_ms = Math.round(performance.now() - start);
    entry.error = err.message;
    addLog(entry);
    throw err;
  }
};
```

This is transparent — all existing API calls (health, apply, undo) automatically get logged without any changes to the call sites.

#### Current File Detection

```javascript
function detectCurrentFile() {
  const path = window.location.pathname.replace(/^\//, '').replace(/\/$/, '');
  if (!path) return 'index.md';
  return path.replace(/\.html$/, '') + '.md';
}
```

This works because kiln generates `projects/forge-v2.html` from `projects/forge-v2.md`, and the overlay server serves it at `/projects/forge-v2` (clean URLs via static_handler.py). The mapping is 1:1.

#### Log Entry Display

Collapsed (one line per log):
```
POST /api/agent/apply  200  1.2s
```

Expanded (shows full request/response):
```
POST /api/agent/apply  200  1.2s
─── Request ───
{
  "instruction": "Add a concise update...",
  "current_file": "projects/forge-v2.md"
}
─── Response ───
{
  "ok": true,
  "modified": [...]
}
```

Click to toggle. Copy buttons for request/response bodies.

### Responsive Behavior

#### Breakpoints

Single breakpoint at **640px** (standard mobile/desktop split).

#### Desktop (≥640px)
- Modal: `max-width: 480px; width: 90vw; max-height: 80vh`
- Centered in viewport via flex centering on backdrop
- `border-radius: 12px` all corners
- Backdrop: `rgba(0, 0, 0, 0.5)`

#### Mobile (<640px)
- Modal: `width: 100%; max-height: 85vh`
- Anchored to bottom of viewport (bottom sheet pattern)
- `border-radius: 12px 12px 0 0` (rounded top only)
- Action buttons stack to 2-column grid if needed
- Textarea and pre elements go full width

#### Touch Considerations
- All interactive elements: minimum 44px touch target
- Floating button: 44px diameter (already meets minimum)
- Action buttons: `min-height: 44px`
- Sufficient spacing between tap targets (8px gaps)
- No hover-dependent interactions (hover enhances but isn't required)

### CSS Architecture

```css
/* Floating trigger button */
#forge-trigger { /* fixed, bottom-right, 44px circle */ }
#forge-trigger .badge { /* unseen log count indicator */ }

/* Backdrop + modal container */
#forge-backdrop { /* fixed, inset 0, flex centering */ }

/* Modal */
#forge-modal { /* max-width, max-height, overflow hidden */ }
#forge-modal .header { /* sticky header with title + close */ }
#forge-modal .body { /* overflow-y auto, padding */ }
#forge-modal .footer { /* sticky footer with reload */ }

/* Agent tools */
#forge-modal .file-path { /* editable file display */ }
#forge-modal .actions { /* button grid */ }

/* Log viewer */
#forge-modal .logs-toggle { /* collapsible header */ }
#forge-modal .log-entry { /* clickable row */ }
#forge-modal .log-detail { /* expanded request/response */ }

/* Response output */
#forge-modal .output { /* scrollable pre block */ }

/* Responsive */
@media (max-width: 639px) {
  #forge-backdrop { align-items: flex-end; }
  #forge-modal { width: 100%; border-radius: 12px 12px 0 0; max-height: 85vh; }
}
```

All selectors scoped under `#forge-trigger`, `#forge-backdrop`, or `#forge-modal` to avoid any collision with the host page's styles.

### Integration

**Zero code changes needed.** The forge-overlay injection middleware already serves whatever is in `overlay_dir`. To use the production overlay:

```yaml
# forge.yaml
overlay_dir: src/overlay
```

For Docker: copy `src/overlay/` into the image and set the config. No Dockerfile changes beyond the COPY directive.

For `forge dev`: either change `forge.yaml` manually, or add a `--production` flag to the CLI that sets `overlay_dir` to `src/overlay` (one line change in commands.py, strictly optional).

### Implementation Order

1. **Create `src/overlay/ops.css`** (~250 lines)
   - Floating button styles (44px circle, fixed bottom-right)
   - Backdrop styles (full viewport, semi-transparent)
   - Modal styles (centered desktop, bottom-sheet mobile)
   - Log entry styles (collapsed/expanded states)
   - Responsive breakpoint at 640px
   - Transitions (modal appear/disappear, button hover)

2. **Create `src/overlay/ops.js`** (~300 lines)
   - Fetch intercept + log storage
   - DOM construction (button + backdrop + modal)
   - Current file detection
   - API helpers (reuse demo pattern)
   - SSE connection
   - Event handlers (open/close, expand/collapse, reload)
   - Log rendering

3. **Test with `forge dev`** by setting `overlay_dir: src/overlay` in forge.yaml

That's 2 files, ~550 lines total, no build step, no new dependencies, no changes to any existing code.

### What NOT to Do

- Don't split JS into multiple module files
- Don't add a build/bundle step
- Don't modify inject.py, app.py, or any forge-overlay code
- Don't add localStorage for anything beyond panel open/closed state
- Don't implement virtual scrolling (50 capped log entries don't need it)
- Don't add minimize/maximize buttons (open or closed is enough)

---

## Summary

The intern's design documents are good reference material for UI specifics (color palette, spacing, component states). But the implementation plan is over-engineered. The production overlay is the demo overlay with a better interaction model (floating button → centered modal), logging, and responsive design. Two files in `src/overlay/`, ~550 lines, zero infrastructure changes.
