# Assumptions — Production Overlay UI

## Context & Constraints

### Current State (Demo Overlay)
- **forge-overlay** package (v0.2.1) currently serves the demo UI
- Displays as a **small menu in bottom right corner** of the page
- Injects overlay assets (CSS/JS) into generated HTML
- Acts as a transparent API proxy to obsidian-agent backend
- Serves kiln-generated static content with minimal modifications

### Production Goals
- **Distinct from demo UI**: Leave demo overlay as-is; build new production overlay separately
- **Non-intrusive button**: Small button in corner (similar visual weight to current demo menu)
- **Expandable popup menu**: Click button → modal opens with agent interaction UI
- **LLM logging**: Show request/response logs for debugging
  - Logs initially hidden (expandable header)
  - Include token counts, timing, model name
  - Allow inspection of system prompt, user messages, assistant responses
- **Page reload capability**: Allow reload without leaving modal
- **Docker deployment**: Must work in production Docker container (not just dev)

### Scope Boundaries
- **NOT changing demo overlay**: Demo overlay stays as-is for backward compatibility
- **NOT rewriting forge-overlay**: Using it as-is; new UI is an additional layer/extension
- **NOT touching kiln rendering**: Production overlay is UX/debugging layer only
- **NOT implementing agent logic**: Only UI for interacting with existing obsidian-agent endpoints

### Architecture Assumptions
- **Single HTML/JS injection point**: Like demo, inject a script/stylesheet into page headers
- **Port configuration**: Will be served alongside overlay or as separate service (TBD in plan)
- **API endpoints**: Use same `/api/*` proxy path as demo (obsidian-agent backend)
- **State management**: Minimal — button state, modal state, maybe local session logging
- **No backend store**: Logs are ephemeral, cleared on page reload (browser storage only)

### User Scenarios
1. **Developer exploring agent behavior**: Opens modal, sees LLM call details, inspects logs
2. **Testing agent mutations**: Uses modal to trigger apply/undo, reloads page to verify
3. **Debugging edge cases**: Expands logs to see exact prompt/response without leaving page
4. **Production mode (docker)**: Needs same functionality but styled appropriately (not demo-like)

### Tech Stack Assumptions
- **Frontend**: Vanilla JS (or minimal framework) — no heavy deps
- **Styling**: Modern CSS (flexbox, grid, dark mode support)
- **Logging transport**: Browser `console.log()` + intercepted fetch logs
- **Compatibility**: Modern browsers (Chrome, Firefox, Safari last 2 versions)

## Success Criteria
- ✅ Small button UI (non-distracting)
- ✅ Expandable popup modal with agent interaction options
- ✅ Visible LLM logs (request/response, tokens, timing)
- ✅ Collapsible log sections (hidden by default, expandable)
- ✅ Page reload from modal (preserves modal state)
- ✅ Works in both dev (`forge dev`) and production (Docker) modes
- ✅ Demo overlay untouched

## Open Questions (To Resolve in Planning)
- Should production overlay extend forge-overlay or be a separate injectable?
- How to detect/capture LLM logs (HTTP intercept, monkey-patch, etc.)?
- Should logs persist across page reloads (sessionStorage)?
- UI styling: branded colors vs. minimal dark UI?
- Should modal include other tools (vault browser, sync status, etc.) or just agent?
