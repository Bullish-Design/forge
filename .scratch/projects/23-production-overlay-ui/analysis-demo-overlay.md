# Analysis: Current Demo Overlay (Task 1.1)

## Summary
The current demo overlay is a simple, fixed-position aside element in the bottom-right corner showing agent interaction UI and rebuild notifications.

## Current Implementation

### Location
- **CSS**: `/demo/overlay/ops.css`
- **JS**: `/demo/overlay/ops.js`
- **Injection**: forge-overlay ASGI middleware injects `<link rel="stylesheet" href="/ops/ops.css">` + `<script type="module" src="/ops/ops.js"></script>` before `</head>`

### HTML Structure
```
<aside id="forge-demo-overlay">
  <header>Forge Overlay Demo</header>
  <div class="body">
    <div class="row">SSE events: <span id="forge-demo-count" class="badge">0</span></div>
    <div class="row" id="forge-demo-status">status: connecting...</div>
    <div class="row">
      <label for="forge-demo-instruction">Prompt</label>
      <textarea id="forge-demo-instruction" rows="4">...</textarea>
    </div>
    <div class="actions">
      <button id="forge-demo-health">API health</button>
      <button id="forge-demo-apply">Apply prompt</button>
      <button id="forge-demo-undo">Undo</button>
    </div>
    <pre id="forge-demo-output">Waiting for interaction...</pre>
  </div>
</aside>
```

### CSS Styling
- **Position**: Fixed, bottom-right corner (right: 16px, bottom: 16px)
- **Size**: 320px wide, responsive (max-width: calc(100vw - 32px))
- **Style**: Dark theme (slate-900/slate-800 colors), monospace font, subtle shadow
- **Z-index**: 100000 (very high, always on top)
- **Components**:
  - Header: bold, border-bottom separator
  - Body: rows with 8px margin
  - Textarea: 60px min-height, dark background, slate borders
  - Buttons: 3-column grid layout, hover effect (blue border)
  - Output: scrollable pre with dark background, max-height 140px

### JavaScript Functionality
1. **SSE Connection** (`/ops/events`)
   - Connects on page load
   - Displays connection status
   - Counts rebuild events

2. **API Health Button**
   - Calls `GET /api/health`
   - Displays JSON response in output pre

3. **Apply Prompt Button**
   - Gets textarea value or default prompt
   - Calls `POST /api/agent/apply` with instruction + current_file ("projects/forge-v2.md")
   - Displays JSON response

4. **Undo Button**
   - Calls `POST /api/undo`
   - Displays JSON response

5. **Output Display**
   - Centralizes all responses in pre element
   - Formats JSON with 2-space indentation
   - Handles non-JSON responses as status + body

## Integration Points

### forge-overlay Flow
1. **InjectMiddleware** (inject.py) - Inserts script/link tags before `</head>`
2. **Static route** (/ops/{path}) - Serves ops.js and ops.css from `config.overlay_dir`
3. **Proxy route** (/api/{path}) - Forwards to obsidian-agent backend
4. **SSE route** (/ops/events) - Broadcasts rebuild events via EventBroker

### Process Flow (forge dev)
```
forge dev
├─ start_overlay (config.overlay_dir → default "static/")
├─ start_agent
└─ start_kiln (--on-rebuild → POST /internal/rebuild)
    └─ kiln detects change
        └─ Sends webhook to /internal/rebuild
            └─ EventBroker publishes "rebuilt" event
                └─ SSE stream updates (SSE /ops/events)
                    └─ Browser receives, increments counter
```

## Current Demo Limitations (Not Bugs, By Design)
- No LLM log visibility (just final responses)
- No token count or timing info
- Output area is small (140px max-height)
- Single file hardcoded (projects/forge-v2.md)
- No page reload capability
- Minimal styling (no animations, transitions)

## Production Overlay Design Implications

### Reuse Opportunities
- **Injection pattern**: forge-overlay's inject pattern is clean; production overlay can use the same approach
- **Port structure**: `/ops/*` namespace is available for new assets
- **API proxy**: Same `/api/*` endpoints available
- **SSE events**: Can extend EventBroker to publish new event types

### Design Decisions for Production Overlay
1. **Different file location**: Use `static/production/` instead of `demo/overlay/` to keep separation
2. **ID namespacing**: Use `#forge-production-overlay` to avoid conflicts
3. **Component isolation**: Self-contained JS (IIFE) like demo, but with modular internal structure
4. **Asset serving**: Follow demo pattern of `/ops/production/{js,css}`
5. **Styling**: Dark theme consistent with demo, but more polished UI

### Open Questions (To Be Decided)
- Should production and demo overlays coexist or be mutually exclusive?
- If coexisting, how to avoid z-index/layout conflicts?
- Should production overlay extend EventBroker or implement separate logging?
- Should we create separate endpoints for production vs. demo (e.g., `/api/agent/apply` vs `/api/agent/apply-with-logs`)?

## File Checklist for Injection
The forge-overlay injection process requires:
1. ✅ ops.js file in overlay_dir
2. ✅ ops.css file in overlay_dir
3. ✅ `/ops/{path}` route serving files
4. ✅ InjectMiddleware inserting link/script before </head>
5. ✅ Browser processes injected script (no CSP conflicts)

## Recommendations for Phase 1.2 (UI Design)
Based on this analysis, the production overlay should:
1. Keep the fixed position pattern (bottom-right corner) but add a "minimized button" state
2. Expand to modal-like panel (not fixed position when open)
3. Reuse color scheme (dark slate theme)
4. Add collapsible sections for logs (hidden by default)
5. Add page reload button in the UI
6. Maintain monospace font for code/logs, sans-serif for UI labels
