# Production Overlay UI — Implementation Guide

This is a step-by-step guide to implement the production overlay UI. Each step includes exact code references, expected behavior, and verification checks. Complete each step fully and verify before moving to the next.

## Prerequisites

Before starting, make sure you understand the existing system:

1. Read `demo/overlay/ops.js` (80 lines) — the demo overlay JavaScript
2. Read `demo/overlay/ops.css` (87 lines) — the demo overlay styles
3. Read `PROD_UI_CONCEPT.md` in this project directory — the design spec you're implementing

**Key facts you need to know:**

- The forge-overlay server injects `<link rel="stylesheet" href="/ops/ops.css">` and `<script type="module" src="/ops/ops.js">` into every HTML page via ASGI middleware (`inject.py`)
- The server serves files from whatever directory `overlay_dir` points to in `forge.yaml`
- The files MUST be named `ops.js` and `ops.css` — the injection middleware hardcodes these paths
- The overlay server proxies `/api/*` requests to the obsidian-agent backend
- The overlay server provides SSE rebuild events at `/ops/events`
- You are creating TWO files: `src/overlay/ops.js` and `src/overlay/ops.css`
- You are NOT modifying any existing files

---

## Step 1: Create the Directory and Empty Files

Create the overlay directory and empty starter files.

```bash
mkdir -p src/overlay
touch src/overlay/ops.js src/overlay/ops.css
```

### Verification

```bash
ls -la src/overlay/
# Should show ops.js and ops.css (both 0 bytes)
```

---

## Step 2: Floating Trigger Button (CSS + JS)

Build the floating button that appears in the bottom-right corner. This is the entry point — when clicked, it will open the modal (wired in a later step).

### 2a: CSS for the trigger button

Write the following to `src/overlay/ops.css`:

```css
/* ── Reset ─────────────────────────────────────────── */
#forge-trigger,
#forge-backdrop,
#forge-modal,
#forge-modal * {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

/* ── Floating Trigger Button ──────────────────────── */
#forge-trigger {
  position: fixed;
  bottom: 16px;
  right: 16px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 1px solid #334155;
  background: rgba(15, 23, 42, 0.94);
  color: #e2e8f0;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  z-index: 100000;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(2, 6, 23, 0.4);
  transition: border-color 0.15s, box-shadow 0.15s;
}

#forge-trigger:hover {
  border-color: #60a5fa;
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.25);
}

#forge-trigger .forge-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  border-radius: 999px;
  background: #3b82f6;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
}

#forge-trigger .forge-badge:empty {
  display: none;
}
```

### 2b: JS for the trigger button

Write the following to `src/overlay/ops.js`:

```javascript
(() => {
  // ── Trigger Button ──────────────────────────────────
  const trigger = document.createElement("button");
  trigger.id = "forge-trigger";
  trigger.setAttribute("aria-label", "Open Forge overlay");
  trigger.innerHTML = `<span aria-hidden="true">\u2692</span><span class="forge-badge"></span>`;
  document.body.appendChild(trigger);

  trigger.addEventListener("click", () => {
    console.log("[forge-overlay] trigger clicked");
  });
})();
```

The `\u2692` character is the hammer-and-pick (⚒) unicode symbol. If it doesn't render well in the target browser, replace it with `\u2699` (⚙ gear).

### Verification

1. Set `overlay_dir: src/overlay` in your `forge.yaml` (or pass it via environment variable `FORGE_OVERLAY_DIR=src/overlay`)
2. Start the forge dev stack: `devenv shell -- forge dev`
3. Open the overlay URL in a browser (default: `http://127.0.0.1:8080`)
4. Confirm:
   - A small dark circular button appears in the bottom-right corner
   - The button has an icon (⚒ or ⚙)
   - Hovering the button shows a blue border glow
   - Clicking the button logs `[forge-overlay] trigger clicked` in the browser console
   - The button does NOT interfere with page content (it floats above it)
   - The button appears on top of all page content (z-index 100000)
5. Resize the browser to a narrow mobile width (~375px) — the button should still be visible and tappable

---

## Step 3: Backdrop and Modal Shell (CSS + JS)

Build the modal container: a semi-transparent backdrop with a centered modal panel. The modal starts hidden and is toggled by the trigger button.

### 3a: Append to ops.css

Add these rules after the trigger button styles:

```css
/* ── Backdrop ─────────────────────────────────────── */
#forge-backdrop {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 100001;
  background: rgba(0, 0, 0, 0.5);
  justify-content: center;
  align-items: center;
}

#forge-backdrop.open {
  display: flex;
}

/* ── Modal ────────────────────────────────────────── */
#forge-modal {
  width: 90vw;
  max-width: 480px;
  max-height: 80vh;
  border-radius: 12px;
  border: 1px solid #1f2937;
  background: rgba(15, 23, 42, 0.97);
  color: #e5e7eb;
  font-family: ui-monospace, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.4;
  box-shadow: 0 12px 30px rgba(2, 6, 23, 0.45);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

#forge-modal .forge-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid #334155;
  font-weight: 700;
  flex-shrink: 0;
}

#forge-modal .forge-header button {
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 18px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1;
}

#forge-modal .forge-header button:hover {
  color: #e2e8f0;
  background: rgba(255, 255, 255, 0.1);
}

#forge-modal .forge-body {
  padding: 12px;
  overflow-y: auto;
  flex: 1;
}

#forge-modal .forge-footer {
  padding: 8px 12px;
  border-top: 1px solid #334155;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  font-size: 11px;
  color: #94a3b8;
}

/* ── Mobile (<640px): bottom sheet ─────────────────── */
@media (max-width: 639px) {
  #forge-backdrop.open {
    align-items: flex-end;
  }

  #forge-modal {
    width: 100%;
    max-width: 100%;
    max-height: 85vh;
    border-radius: 12px 12px 0 0;
    border-bottom: none;
  }
}
```

### 3b: Update ops.js

Replace the entire IIFE content with:

```javascript
(() => {
  // ── State ───────────────────────────────────────────
  let modalOpen = localStorage.getItem("forge-modal-open") === "true";

  // ── Trigger Button ──────────────────────────────────
  const trigger = document.createElement("button");
  trigger.id = "forge-trigger";
  trigger.setAttribute("aria-label", "Open Forge overlay");
  trigger.innerHTML = `<span aria-hidden="true">\u2692</span><span class="forge-badge"></span>`;
  document.body.appendChild(trigger);

  // ── Backdrop + Modal ────────────────────────────────
  const backdrop = document.createElement("div");
  backdrop.id = "forge-backdrop";
  backdrop.innerHTML = `
    <div id="forge-modal" role="dialog" aria-label="Forge overlay">
      <div class="forge-header">
        <span>Forge</span>
        <button id="forge-close" aria-label="Close">\u2715</button>
      </div>
      <div class="forge-body">
        <p style="color:#94a3b8;">Modal body — content coming in next steps.</p>
      </div>
      <div class="forge-footer">
        <span id="forge-sse-status">SSE: connecting...</span>
        <button id="forge-reload">Reload Page</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

  // Prevent clicks inside the modal from closing via backdrop
  document.getElementById("forge-modal").addEventListener("click", (e) => {
    e.stopPropagation();
  });

  // ── Open / Close ────────────────────────────────────
  function openModal() {
    modalOpen = true;
    localStorage.setItem("forge-modal-open", "true");
    backdrop.classList.add("open");
    trigger.style.display = "none";
  }

  function closeModal() {
    modalOpen = false;
    localStorage.setItem("forge-modal-open", "false");
    backdrop.classList.remove("open");
    trigger.style.display = "flex";
  }

  trigger.addEventListener("click", openModal);
  backdrop.addEventListener("click", closeModal);
  document.getElementById("forge-close").addEventListener("click", closeModal);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modalOpen) closeModal();
  });

  // ── Reload Button ───────────────────────────────────
  document.getElementById("forge-reload").addEventListener("click", () => {
    location.reload();
  });

  // ── Restore state on load ───────────────────────────
  if (modalOpen) {
    openModal();
  }
})();
```

### Verification

1. Reload the page in the browser
2. Confirm:
   - The floating button appears (same as Step 2)
   - Clicking the button: the button disappears, a semi-transparent dark backdrop covers the page, and a centered dark modal panel appears with "Forge" header and placeholder body text
   - Clicking the close button (✕) in the modal header: the modal disappears, the floating button reappears
   - Clicking the backdrop (outside the modal): the modal closes
   - Pressing ESC: the modal closes
   - Clicking inside the modal body does NOT close the modal
   - Clicking "Reload Page" in the footer reloads the browser page
   - After reload: if the modal was open before reload, it re-opens automatically (localStorage persistence)
   - Close the modal, reload — the modal stays closed
3. Mobile test — resize browser to ~375px width:
   - The modal should appear anchored to the bottom of the screen (bottom sheet)
   - The modal should be full width with rounded top corners only
   - The modal body should be scrollable if content exceeds the viewport

---

## Step 4: Modal Body — File Path, Prompt Textarea, Action Buttons

Replace the placeholder modal body with the actual agent interaction controls.

### 4a: Append to ops.css

```css
/* ── Modal body sections ──────────────────────────── */
#forge-modal .forge-section {
  margin-bottom: 12px;
}

#forge-modal .forge-section-label {
  display: block;
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 4px;
}

/* File path row */
#forge-modal .forge-file-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

#forge-modal .forge-file-path {
  flex: 1;
  font-size: 12px;
  color: #e2e8f0;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 6px 8px;
  font-family: inherit;
}

#forge-modal .forge-file-path:read-only {
  border-color: transparent;
  background: transparent;
  cursor: default;
}

#forge-modal .forge-file-path:not(:read-only):focus {
  outline: none;
  border-color: #3b82f6;
}

#forge-modal .forge-edit-btn {
  background: none;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px 8px;
  font-size: 12px;
  min-height: 32px;
}

#forge-modal .forge-edit-btn:hover {
  border-color: #60a5fa;
  color: #e2e8f0;
}

/* Prompt textarea */
#forge-modal textarea {
  width: 100%;
  resize: vertical;
  min-height: 60px;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  font: inherit;
  padding: 8px;
}

#forge-modal textarea:focus {
  outline: none;
  border-color: #3b82f6;
}

/* Action buttons */
#forge-modal .forge-actions {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 8px;
}

#forge-modal .forge-actions button {
  border: 1px solid #334155;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  cursor: pointer;
  padding: 8px;
  font-size: 11px;
  font-family: inherit;
  min-height: 44px;
  transition: border-color 0.15s;
}

#forge-modal .forge-actions button:hover {
  border-color: #60a5fa;
}

#forge-modal .forge-actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

#forge-modal .forge-actions button.forge-primary {
  background: #1e3a5f;
  border-color: #3b82f6;
}

/* Response output */
#forge-modal .forge-output {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 8px;
  max-height: 200px;
  overflow: auto;
  font: inherit;
  font-size: 11px;
  color: #cbd5e1;
}

/* Footer reload button */
#forge-modal .forge-footer button {
  border: 1px solid #334155;
  border-radius: 6px;
  background: #0f172a;
  color: #e2e8f0;
  cursor: pointer;
  padding: 6px 12px;
  font-size: 11px;
  font-family: inherit;
  min-height: 32px;
}

#forge-modal .forge-footer button:hover {
  border-color: #60a5fa;
}
```

### 4b: Update the modal body HTML in ops.js

Replace the `backdrop.innerHTML` template with:

```javascript
  backdrop.innerHTML = `
    <div id="forge-modal" role="dialog" aria-label="Forge overlay">
      <div class="forge-header">
        <span>Forge</span>
        <button id="forge-close" aria-label="Close">\u2715</button>
      </div>
      <div class="forge-body">
        <div class="forge-file-row">
          <input id="forge-file-path" class="forge-file-path" type="text" readonly />
          <button id="forge-file-edit" class="forge-edit-btn" aria-label="Edit file path">\u270E</button>
        </div>

        <div class="forge-section">
          <label class="forge-section-label" for="forge-instruction">Prompt</label>
          <textarea id="forge-instruction" rows="3">Add a concise update with 2-3 actionable bullets for this note.</textarea>
        </div>

        <div class="forge-actions">
          <button id="forge-send" class="forge-primary">Send</button>
          <button id="forge-undo">Undo</button>
          <button id="forge-health">Health</button>
        </div>

        <div class="forge-section" style="margin-top:12px;">
          <pre id="forge-output" class="forge-output">Waiting for interaction...</pre>
        </div>
      </div>
      <div class="forge-footer">
        <span id="forge-sse-status">SSE: connecting...</span>
        <button id="forge-reload">Reload Page</button>
      </div>
    </div>
  `;
```

### 4c: Add current-file detection and file-path editing logic

Add this code inside the IIFE, after the `backdrop` is appended to `document.body` and before the open/close functions:

```javascript
  // ── Current File Detection ──────────────────────────
  function detectCurrentFile() {
    const p = window.location.pathname.replace(/^\//, "").replace(/\/$/, "");
    if (!p) return "index.md";
    return p.replace(/\.html$/, "") + ".md";
  }

  const filePathEl = document.getElementById("forge-file-path");
  const fileEditBtn = document.getElementById("forge-file-edit");
  filePathEl.value = detectCurrentFile();

  let fileEditing = false;
  fileEditBtn.addEventListener("click", () => {
    fileEditing = !fileEditing;
    filePathEl.readOnly = !fileEditing;
    fileEditBtn.textContent = fileEditing ? "\u2713" : "\u270E";
    if (fileEditing) filePathEl.focus();
  });
```

### 4d: Add API helper functions and button event handlers

Add this code after the file-path logic:

```javascript
  // ── API Helpers ─────────────────────────────────────
  const outputEl = document.getElementById("forge-output");
  const instructionEl = document.getElementById("forge-instruction");

  function setOutput(value) {
    outputEl.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  }

  async function postJson(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await response.text();
    try {
      return JSON.parse(text);
    } catch {
      return { status: response.status, body: text };
    }
  }

  // ── Action Buttons ──────────────────────────────────
  document.getElementById("forge-send").addEventListener("click", async () => {
    const instruction = instructionEl.value.trim() || "Add a concise useful update for this note.";
    const currentFile = filePathEl.value.trim();
    setOutput("Sending...");
    try {
      const data = await postJson("/api/agent/apply", { instruction, current_file: currentFile });
      setOutput(data);
    } catch (err) {
      setOutput("Error: " + err.message);
    }
  });

  document.getElementById("forge-undo").addEventListener("click", async () => {
    setOutput("Undoing...");
    try {
      const data = await postJson("/api/undo", {});
      setOutput(data);
    } catch (err) {
      setOutput("Error: " + err.message);
    }
  });

  document.getElementById("forge-health").addEventListener("click", async () => {
    setOutput("Checking...");
    try {
      const response = await fetch("/api/health");
      const data = await response.json();
      setOutput(data);
    } catch (err) {
      setOutput("Error: " + err.message);
    }
  });
```

### Verification

1. Reload the page and open the modal
2. Confirm the **file path** row:
   - Shows the auto-detected file path (e.g., `index.md` on the root page, `projects/forge-v2.md` on `/projects/forge-v2`)
   - The input is read-only by default (no visible border, transparent background)
   - Clicking the pencil (✎) button makes the input editable (border appears, focus is set)
   - Clicking again (now a checkmark ✓) makes it read-only again
3. Confirm the **prompt textarea**:
   - Contains default text: "Add a concise update with 2-3 actionable bullets for this note."
   - Text is editable, textarea is resizable vertically
4. Confirm the **action buttons**:
   - Three buttons in a row: "Send" (blue tint), "Undo", "Health"
   - "Health" button: click it — the response output area should show JSON from `/api/health` (or an error if the agent isn't running, which is fine)
   - "Send" button: click it — the response output shows "Sending..." then the agent response JSON
   - "Undo" button: click it — shows undo response
5. Confirm the **response output** area:
   - Shows formatted JSON from API responses
   - Scrollable when content overflows (test with a verbose response)
6. Mobile test (~375px): all elements remain usable, buttons are at least 44px tall, textarea is full width

---

## Step 5: SSE Connection

Wire up the Server-Sent Events connection for rebuild notifications, matching the demo overlay's behavior.

### 5a: Add SSE code in ops.js

Add this code inside the IIFE, after the action button handlers:

```javascript
  // ── SSE Connection ──────────────────────────────────
  const sseStatusEl = document.getElementById("forge-sse-status");
  let sseCount = 0;

  const source = new EventSource("/ops/events");
  source.onopen = () => {
    sseStatusEl.textContent = "SSE: connected";
  };
  source.onmessage = (event) => {
    sseCount += 1;
    sseStatusEl.textContent = `SSE: connected (${sseCount} events)`;
  };
  source.onerror = () => {
    sseStatusEl.textContent = "SSE: reconnecting...";
  };
```

### Verification

1. Reload the page and open the modal
2. Confirm:
   - Footer shows "SSE: connecting..." briefly, then "SSE: connected"
   - If kiln is running and you edit a vault file, the counter increments: "SSE: connected (1 events)", "(2 events)", etc.
   - If you disconnect the overlay server and reconnect, the status shows "SSE: reconnecting..." then "SSE: connected" again
3. The SSE connection should work regardless of whether the modal is open or closed (it runs in the background)

---

## Step 6: Fetch Intercept and Log Storage

This is the core logging feature. Monkey-patch `window.fetch` to capture all `/api/*` requests and responses, storing them in memory.

### 6a: Add fetch intercept at the TOP of the IIFE

This code MUST run before any other code that calls `fetch`. Place it immediately after the state declarations, before the trigger button creation:

```javascript
  // ── Log State ───────────────────────────────────────
  const logs = [];
  const MAX_LOGS = 50;
  let logIdCounter = 0;
  let unseenCount = 0;
  const badgeEl = () => trigger.querySelector(".forge-badge");

  function addLog(entry) {
    logs.unshift(entry); // newest first
    if (logs.length > MAX_LOGS) logs.pop();
    if (!modalOpen) {
      unseenCount++;
      const b = badgeEl();
      if (b) b.textContent = String(unseenCount);
    }
    renderLogs();
  }

  function renderLogs() {
    // placeholder — will be implemented in Step 7
  }

  // ── Fetch Intercept ─────────────────────────────────
  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const [resource, options] = args;
    const url = typeof resource === "string" ? resource : resource.url;

    if (!url.includes("/api/")) {
      return originalFetch.apply(this, args);
    }

    const entry = {
      id: ++logIdCounter,
      timestamp: Date.now(),
      method: (options && options.method) || "GET",
      url: url,
      request: null,
      response: null,
      duration_ms: 0,
      status: 0,
      error: null,
    };

    if (options && options.body) {
      try { entry.request = JSON.parse(options.body); } catch { entry.request = options.body; }
    }

    const start = performance.now();
    try {
      const response = await originalFetch.apply(this, args);
      entry.duration_ms = Math.round(performance.now() - start);
      entry.status = response.status;

      const clone = response.clone();
      clone.text().then((text) => {
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

### 6b: Clear badge when modal opens

In the `openModal()` function, add badge clearing:

```javascript
  function openModal() {
    modalOpen = true;
    localStorage.setItem("forge-modal-open", "true");
    backdrop.classList.add("open");
    trigger.style.display = "none";
    unseenCount = 0;
    const b = badgeEl();
    if (b) b.textContent = "";
  }
```

### Verification

1. Reload the page and keep the modal **closed**
2. Open browser DevTools console
3. Run: `fetch("/api/health")` in the console
4. Confirm:
   - A blue badge appears on the floating button showing "1"
   - Run another fetch: `fetch("/api/health")` — badge shows "2"
5. Open the modal:
   - The badge disappears (unseen count cleared)
6. With the modal open, click "Health" button:
   - The fetch should still work normally (response appears in output)
   - Check the console — no errors about fetch interception
7. Close the modal, click "Health" from DevTools again — badge increments

---

## Step 7: Log Viewer UI

Build the collapsible log viewer section in the modal body. Shows a list of captured API calls with expand/collapse for details.

### 7a: Append to ops.css

```css
/* ── Log Viewer ───────────────────────────────────── */
#forge-modal .forge-logs-header {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 6px 0;
  font-size: 12px;
  color: #94a3b8;
  user-select: none;
  margin-top: 4px;
  border: none;
  background: none;
  font-family: inherit;
  width: 100%;
  text-align: left;
}

#forge-modal .forge-logs-header:hover {
  color: #e2e8f0;
}

#forge-modal .forge-logs-header .forge-caret {
  transition: transform 0.15s;
  display: inline-block;
}

#forge-modal .forge-logs-header .forge-caret.open {
  transform: rotate(90deg);
}

#forge-modal .forge-logs-list {
  display: none;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
  max-height: 240px;
  overflow-y: auto;
}

#forge-modal .forge-logs-list.open {
  display: flex;
}

#forge-modal .forge-log-entry {
  border: 1px solid #1e293b;
  border-radius: 6px;
  background: #020617;
  font-size: 11px;
}

#forge-modal .forge-log-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  cursor: pointer;
  user-select: none;
}

#forge-modal .forge-log-summary:hover {
  background: rgba(255, 255, 255, 0.03);
}

#forge-modal .forge-log-method {
  font-weight: 700;
  color: #60a5fa;
}

#forge-modal .forge-log-url {
  flex: 1;
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

#forge-modal .forge-log-status {
  color: #10b981;
}

#forge-modal .forge-log-status.error {
  color: #ef4444;
}

#forge-modal .forge-log-duration {
  color: #94a3b8;
  white-space: nowrap;
}

#forge-modal .forge-log-detail {
  display: none;
  padding: 0 8px 8px;
  border-top: 1px solid #1e293b;
}

#forge-modal .forge-log-detail.open {
  display: block;
}

#forge-modal .forge-log-detail-label {
  font-size: 10px;
  color: #64748b;
  margin-top: 6px;
  margin-bottom: 2px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

#forge-modal .forge-log-detail pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  background: #0f172a;
  border-radius: 4px;
  padding: 6px;
  font: inherit;
  font-size: 10px;
  color: #cbd5e1;
  max-height: 150px;
  overflow: auto;
}
```

### 7b: Add log viewer HTML to modal body

In the `backdrop.innerHTML` template, add the logs section between the action buttons and the response output:

```html
        <div class="forge-section" style="margin-top:12px;">
          <button class="forge-logs-header" id="forge-logs-toggle">
            <span class="forge-caret" id="forge-logs-caret">\u25B8</span>
            <span>Logs (<span id="forge-logs-count">0</span>)</span>
          </button>
          <div class="forge-logs-list" id="forge-logs-list"></div>
        </div>
```

The complete `forge-body` section in the template should now be:

```html
      <div class="forge-body">
        <div class="forge-file-row">
          <input id="forge-file-path" class="forge-file-path" type="text" readonly />
          <button id="forge-file-edit" class="forge-edit-btn" aria-label="Edit file path">\u270E</button>
        </div>

        <div class="forge-section">
          <label class="forge-section-label" for="forge-instruction">Prompt</label>
          <textarea id="forge-instruction" rows="3">Add a concise update with 2-3 actionable bullets for this note.</textarea>
        </div>

        <div class="forge-actions">
          <button id="forge-send" class="forge-primary">Send</button>
          <button id="forge-undo">Undo</button>
          <button id="forge-health">Health</button>
        </div>

        <div class="forge-section" style="margin-top:12px;">
          <button class="forge-logs-header" id="forge-logs-toggle">
            <span class="forge-caret" id="forge-logs-caret">\u25B8</span>
            <span>Logs (<span id="forge-logs-count">0</span>)</span>
          </button>
          <div class="forge-logs-list" id="forge-logs-list"></div>
        </div>

        <div class="forge-section">
          <pre id="forge-output" class="forge-output">Waiting for interaction...</pre>
        </div>
      </div>
```

### 7c: Implement renderLogs() and log viewer toggle

Replace the placeholder `renderLogs()` function and add the logs toggle handler. Place this after the `addLog` function:

```javascript
  // Track which log entries are expanded
  const expandedLogIds = new Set();
  let logsExpanded = false;

  function renderLogs() {
    const listEl = document.getElementById("forge-logs-list");
    const countEl = document.getElementById("forge-logs-count");
    if (!listEl || !countEl) return;

    countEl.textContent = String(logs.length);

    listEl.innerHTML = logs.map((entry) => {
      const isExpanded = expandedLogIds.has(entry.id);
      const statusClass = entry.status >= 400 || entry.error ? "error" : "";
      const statusText = entry.error ? "ERR" : String(entry.status);
      const duration = entry.duration_ms > 0 ? (entry.duration_ms / 1000).toFixed(1) + "s" : "...";
      const shortUrl = entry.url.replace(/^\/api\//, "");

      let detailHtml = "";
      if (entry.request != null) {
        const reqStr = typeof entry.request === "string" ? entry.request : JSON.stringify(entry.request, null, 2);
        detailHtml += `<div class="forge-log-detail-label">Request</div><pre>${escapeHtml(reqStr)}</pre>`;
      }
      if (entry.response != null) {
        const resStr = typeof entry.response === "string" ? entry.response : JSON.stringify(entry.response, null, 2);
        detailHtml += `<div class="forge-log-detail-label">Response</div><pre>${escapeHtml(resStr)}</pre>`;
      }
      if (entry.error) {
        detailHtml += `<div class="forge-log-detail-label">Error</div><pre>${escapeHtml(entry.error)}</pre>`;
      }

      return `
        <div class="forge-log-entry" data-log-id="${entry.id}">
          <div class="forge-log-summary">
            <span class="forge-log-method">${entry.method}</span>
            <span class="forge-log-url">${escapeHtml(shortUrl)}</span>
            <span class="forge-log-status ${statusClass}">${statusText}</span>
            <span class="forge-log-duration">${duration}</span>
          </div>
          <div class="forge-log-detail ${isExpanded ? "open" : ""}">${detailHtml}</div>
        </div>
      `;
    }).join("");
  }

  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
```

Then add the event handlers after the DOM is built (after `document.body.appendChild(backdrop)`):

```javascript
  // ── Log Viewer Toggle ───────────────────────────────
  document.getElementById("forge-logs-toggle").addEventListener("click", () => {
    logsExpanded = !logsExpanded;
    document.getElementById("forge-logs-list").classList.toggle("open", logsExpanded);
    document.getElementById("forge-logs-caret").classList.toggle("open", logsExpanded);
  });

  // ── Log Entry Expand/Collapse (event delegation) ───
  document.getElementById("forge-logs-list").addEventListener("click", (e) => {
    const entry = e.target.closest(".forge-log-entry");
    if (!entry) return;
    const logId = Number(entry.dataset.logId);
    const detail = entry.querySelector(".forge-log-detail");
    if (!detail) return;
    if (expandedLogIds.has(logId)) {
      expandedLogIds.delete(logId);
      detail.classList.remove("open");
    } else {
      expandedLogIds.add(logId);
      detail.classList.add("open");
    }
  });
```

### Verification

1. Reload the page and open the modal
2. Confirm **logs section starts collapsed**:
   - You see "▸ Logs (0)" — the caret points right, no log entries visible
3. Click "Health" button — then check the logs:
   - Counter updates: "▸ Logs (1)"
   - Click the "▸ Logs (1)" header — it expands, caret rotates to "▾"
   - A log entry appears: `GET health 200 0.1s` (or similar)
4. Click the log entry:
   - It expands to show the response JSON
   - Click again — it collapses
5. Click "Send" button with default prompt:
   - A new log entry appears at the top: `POST agent/apply 200 2.3s` (or similar)
   - Expand it — shows both Request (with instruction and current_file) and Response JSON
6. Generate several API calls (health, send, undo) — confirm:
   - Newest entries appear at the top
   - The log count updates
   - Each entry can be individually expanded/collapsed
   - The log list scrolls if entries exceed 240px height
7. Close the modal, run `fetch("/api/health")` from DevTools:
   - Badge appears on trigger button
   - Open modal — badge clears, new log entry is visible
8. Mobile test: log entries should be readable and tappable at narrow widths

---

## Step 8: Final Assembly and Polish

At this point all features are implemented. This step is about assembling the final files cleanly and adding polish.

### 8a: Final ops.js structure

The complete file should follow this order inside the IIFE:

```
(() => {
  // 1. State declarations (modalOpen, logs, MAX_LOGS, etc.)
  // 2. Fetch intercept (MUST be before any DOM that triggers fetch)
  // 3. Log helpers (addLog, renderLogs, escapeHtml)
  // 4. Trigger button creation + append to body
  // 5. Backdrop + modal HTML creation + append to body
  // 6. Element references (filePathEl, outputEl, instructionEl, etc.)
  // 7. Current file detection + file edit toggle
  // 8. API helpers (setOutput, postJson)
  // 9. Action button handlers (send, undo, health)
  // 10. SSE connection
  // 11. Log viewer toggle + entry expand/collapse delegation
  // 12. Open/close modal functions
  // 13. Trigger/backdrop/close/ESC event listeners
  // 14. Reload button handler
  // 15. Restore modal state from localStorage
})();
```

### 8b: Verify the complete file has no duplicate element references

After assembling, search for any `getElementById` calls that reference elements before they exist in the DOM. All `getElementById` calls must come AFTER `document.body.appendChild(backdrop)`.

The fetch intercept and log state can be declared before DOM creation since they don't reference DOM elements (except `renderLogs`, which guards with `if (!listEl) return`).

### 8c: Final ops.css review

Verify the stylesheet has these sections in order:

```
1. Reset (box-sizing on forge elements)
2. Trigger button (#forge-trigger)
3. Badge (#forge-trigger .forge-badge)
4. Backdrop (#forge-backdrop)
5. Modal (#forge-modal)
6. Header (#forge-modal .forge-header)
7. Body (#forge-modal .forge-body)
8. Footer (#forge-modal .forge-footer)
9. File path row
10. Prompt textarea
11. Action buttons
12. Response output
13. Footer reload button
14. Log viewer (header, list, entries, details)
15. @media (max-width: 639px) responsive overrides
```

### Verification — Complete Feature Checklist

Run through every item. If any fails, fix before considering the implementation complete.

**Trigger button:**
- [ ] Appears bottom-right on page load (modal was previously closed)
- [ ] 44px circular, dark background, icon visible
- [ ] Hover shows blue border glow
- [ ] Click opens modal, button disappears
- [ ] Badge appears when API calls happen while modal is closed
- [ ] Badge clears when modal opens

**Modal — open/close:**
- [ ] Centered on desktop (≥640px) with semi-transparent backdrop
- [ ] Bottom sheet on mobile (<640px), full width, rounded top corners
- [ ] Close via: ✕ button, backdrop click, ESC key
- [ ] Closing shows trigger button again
- [ ] State persists across page reload (localStorage)
- [ ] Clicking inside modal does NOT close it

**File path:**
- [ ] Auto-detected from URL path (e.g., `/projects/foo` → `projects/foo.md`)
- [ ] Root page (`/`) shows `index.md`
- [ ] Read-only by default, editable after clicking pencil button
- [ ] Pencil toggles to checkmark when editing

**Prompt + Send:**
- [ ] Textarea with default prompt text, editable
- [ ] "Send" button POSTs to `/api/agent/apply` with instruction + current_file
- [ ] Response appears in output area as formatted JSON
- [ ] Shows "Sending..." while waiting

**Undo:**
- [ ] POSTs to `/api/undo`
- [ ] Response appears in output area

**Health:**
- [ ] GETs `/api/health`
- [ ] Response appears in output area

**Response output:**
- [ ] Shows formatted JSON
- [ ] Scrollable when content overflows
- [ ] Shows error messages on network failure

**SSE:**
- [ ] Footer shows connection status
- [ ] Event counter increments on vault file changes
- [ ] Reconnects automatically after disconnection

**Log viewer:**
- [ ] Starts collapsed, header shows count
- [ ] Click header to expand/collapse list
- [ ] Each API call creates a log entry (newest first)
- [ ] Entry shows: method, URL path, status code, duration
- [ ] Click entry to expand: shows request and response JSON
- [ ] Click again to collapse
- [ ] Capped at 50 entries (oldest dropped)
- [ ] Error responses show red status

**Responsive:**
- [ ] Desktop: centered modal, 480px max width, 80vh max height
- [ ] Mobile: bottom sheet, full width, 85vh max height
- [ ] All buttons at least 44px tall on mobile
- [ ] Textarea and output area full width on mobile
- [ ] No horizontal overflow on any screen size

**No side effects:**
- [ ] Demo overlay (`demo/overlay/`) is untouched
- [ ] No changes to any Python files
- [ ] No changes to forge-overlay package
- [ ] No new dependencies added
- [ ] The page's own JavaScript works normally (fetch intercept is transparent)

---

## Integration

Once all verification checks pass, the overlay is ready for use.

### For local development

Set `overlay_dir` in your `forge.yaml`:

```yaml
overlay_dir: src/overlay
```

Or via environment variable:

```bash
FORGE_OVERLAY_DIR=src/overlay forge dev
```

### For Docker

Copy the overlay files into the image and set the config:

```dockerfile
COPY src/overlay/ /app/overlay/
```

And in the container's `forge.yaml`:

```yaml
overlay_dir: /app/overlay
```

### Switching back to demo overlay

```yaml
overlay_dir: demo/overlay
```

No code changes needed in either direction.
