# Design: Production Overlay UI (Task 1.2)

## Overview
The production overlay consists of three states:
1. **Minimized Button** - Small button in corner (6 pixels visible)
2. **Expanded Modal** - Full panel with agent tools and log viewer
3. **Log Details** - Expanded log entries with collapsible sections

## Design Principle
Minimal visual footprint when closed, comprehensive tools when open. Non-intrusive dark theme matching the demo overlay.

---

## Component 1: Minimized Button

### Purpose
Visual indicator that overlay is available. Clicking opens modal. Should be subtle and not interfere with page content.

### Dimensions
- **Base**: Small circle or tab (40px diameter for circle, 60px x 40px for tab)
- **Position**: Fixed, bottom-right corner (same as demo)
- **Z-index**: 100000

### Visual Design
```
┌─────────────────────────────────────────────────────────┐
│ Generated Page Content                                  │
│                                                         │
│                                    [⚙] ← Forge Button   │
│                                     (40px diameter)     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### States
- **Idle**: Dark background, icon/text (e.g., "⚙" or "Forge")
- **Hover**: Slightly brighter background, subtle glow
- **Active**: Indicator that modal is open

### CSS Classes
```
#forge-production-button
├─ .forge-minimized
├─ .forge-hovering
└─ .forge-active
```

### Interaction
- **Click**: Toggle modal open/closed
- **Keyboard**: ESC to close modal (not just button)

---

## Component 2: Modal/Panel

### Purpose
Main interface for agent interaction and log viewing. Opens when button is clicked.

### Dimensions
- **Width**: 400px (desktop) → 100vw - 32px (mobile)
- **Height**: Flexible (80vh max, scrollable content)
- **Position**: Fixed, bottom-right corner (same origin as button, but expands upward/leftward)

### Visual Design
```
┌────────────────────────────────────────────┐
│ Forge Overlay              [−] [⊡] [✕]    │ ← Header
├────────────────────────────────────────────┤
│                                            │
│ Agent Tools                                │
│ ┌──────────────────────────────────────┐  │
│ │ Current file: projects/forge-v2.md   │  │
│ │ [Health] [Apply] [Undo] [Reload]     │  │
│ └──────────────────────────────────────┘  │
│                                            │
│ LLM Logs                                   │
│ ┌──────────────────────────────────────┐  │
│ │ ▼ 1. Apply prompt (2025-04-27 14:32) │  │
│ │    Duration: 2.3s | Tokens: 245→512  │  │
│ │ ▼ 2. Previous call (2025-04-27 13:45)│  │
│ │    ...                               │  │
│ └──────────────────────────────────────┘  │
│                                            │
│ Response Output                            │
│ ┌──────────────────────────────────────┐  │
│ │ { "ok": true, "modified": [...] }    │  │
│ │                                      │  │
│ │ (scrollable, copyable text)          │  │
│ └──────────────────────────────────────┘  │
│                                            │
│ [Reload Page]                          │ ← Footer
└────────────────────────────────────────────┘
```

### Header
- **Title**: "Forge Overlay" or "Forge Tools"
- **Controls**:
  - Minimize button (hide logs, show only tools)
  - Maximize button (full screen or nothing if already wide)
  - Close button (X, closes modal)

### Agent Tools Section
- **Current file**: Display/input field for target file
- **Buttons**: Health check, Apply, Undo, Reload page
- **Layout**: Flexible grid (responsive on mobile)

### LLM Logs Section
- **Header**: "LLM Logs" with collapse toggle (default: collapsed)
- **List**: Chronological log entries (newest first)
- **Per-entry**:
  - Timestamp + operation (Apply, Health check, etc.)
  - Duration + token counts (compact, clickable to expand)
  - Status indicator (✓ success, ⚠ warning, ✕ error)

### Response Output Section
- **Header**: "Response" with collapse toggle (default: open if recent activity)
- **Content**: Pre-formatted JSON or text response
- **Interactions**: Copy-to-clipboard button

### Footer
- **Reload Page**: Button to refresh browser without closing modal
- **Status**: "Updates will appear here" or similar placeholder

### CSS Classes
```
#forge-production-modal
├─ .forge-modal-header
│  ├─ .forge-modal-title
│  └─ .forge-modal-controls
├─ .forge-modal-body
│  ├─ .forge-section (agent-tools)
│  │  ├─ .forge-file-input
│  │  └─ .forge-button-group
│  ├─ .forge-section (llm-logs)
│  │  ├─ .forge-logs-header
│  │  └─ .forge-logs-list
│  │     └─ .forge-log-entry (repeating)
│  │        ├─ .forge-log-header
│  │        ├─ .forge-log-details
│  │        └─ .forge-log-content (hidden, expandable)
│  └─ .forge-section (response)
│     ├─ .forge-response-header
│     └─ .forge-response-content
└─ .forge-modal-footer
```

---

## Component 3: Log Entry (Expandable)

### Purpose
Display individual LLM request/response with details.

### Visual Design (Collapsed)
```
▼ 1. Apply prompt (2025-04-27 14:32:15)
   ✓ 2.3s | 245 in, 512 out | model: claude-sonnet-4
```

### Visual Design (Expanded)
```
▽ 1. Apply prompt (2025-04-27 14:32:15)
   ✓ 2.3s | 245 in, 512 out | model: claude-sonnet-4

   Request:
   ┌──────────────────────────────────────────┐
   │ POST /api/agent/apply                    │
   │ {                                        │
   │   "instruction": "...",                  │
   │   "current_file": "projects/forge-v2.md" │
   │ }                                        │
   └──────────────────────────────────────────┘

   Response (collapsed):
   ▼ { "ok": true, "modified": [...] }
      [Expand]

   System Prompt:
   ▼ You are an expert note editor...
      [Expand]
```

### Interaction
- Click to expand/collapse
- Copy buttons for request/response/system prompt
- Syntax highlighting (optional, for code blocks)

### CSS Classes
```
.forge-log-entry
├─ .forge-log-header (clickable)
│  ├─ .forge-log-caret
│  ├─ .forge-log-title
│  └─ .forge-log-meta
├─ .forge-log-details (hidden by default, toggleable)
│  ├─ .forge-log-section (request)
│  ├─ .forge-log-section (response)
│  └─ .forge-log-section (system-prompt)
└─ .forge-log-collapsed-preview (shown when collapsed)
```

---

## Styling Conventions

### Color Palette
Inherit from demo overlay (dark slate theme):
- **Background**: #0f172a (slate-900)
- **Surface**: #020617 (slate-950, for code blocks)
- **Border**: #334155 (slate-700)
- **Text**: #e2e8f0 (slate-200)
- **Accent**: #3b82f6 (blue-500, for links/badges)
- **Success**: #10b981 (green-500, for ✓)
- **Error**: #ef4444 (red-500, for ✕)
- **Warning**: #f59e0b (amber-500, for ⚠)

### Typography
- **Font**: ui-monospace for code, system sans-serif for UI
- **Size**: 12px (body), 11px (small), 13px (header)
- **Weight**: 400 (normal), 700 (bold/headers)

### Spacing
- **Padding**: 12px (sections), 8px (elements), 6px (small)
- **Margin**: 8px (between rows), 0 (inside buttons)
- **Gap**: 6px (grid layouts)

### Borders & Shadows
- **Border**: 1px solid #334155 (subtle)
- **Border-radius**: 8px (standard), 999px (pills/badges)
- **Box-shadow**: 0 12px 30px rgba(2, 6, 23, 0.45) (modal)

### Interactive Elements
- **Buttons**: Dark background (#0f172a), slate border, hover → blue border
- **Textareas**: Dark background, slate border, focus → blue outline
- **Scrollbars**: Minimal, dark theme

---

## Implementation Notes

### State Management
- **Modal open/closed**: localStorage["forge-modal-open"] = true/false
- **Log entries**: In-memory array, cleared on page reload
- **Minimized/maximized**: Track in localStorage for persistence

### Performance Considerations
- **Log size**: Cap at 100 entries (FIFO, oldest removed)
- **Render**: Virtual scrolling for large log lists (optional)
- **Storage**: sessionStorage for logs, localStorage for preferences

### Accessibility
- **ARIA labels**: All buttons, form inputs
- **Keyboard**: Tab, Enter, ESC
- **Contrast**: Meets WCAG AA (dark text on dark background requires careful color choice)

### Mobile Responsiveness
- **Width**: 100vw - 32px on mobile (32px = 16px padding each side)
- **Height**: Flexible, with scrolling
- **Touch targets**: 44px minimum for buttons
- **Stacking**: Modal expands upward, not leftward, on narrow screens

---

## Files to Create
1. `production/ops-production.js` - Main overlay logic
2. `production/components/button.js` - Minimized button
3. `production/components/modal.js` - Modal panel
4. `production/components/logger.js` - Log capture + display
5. `production/ops-production.css` - All styling
6. `production/index.html` - (Optional, for testing standalone)

## Next Steps (Task 1.3)
Decide on log capture strategy:
- Option A: Monkey-patch fetch() to intercept `/api/agent/*` calls
- Option B: Inject logging into obsidian-agent responses (backend)
- Option C: Poll `/api/agent/status` for historical logs
