(() => {
  // ── State ───────────────────────────────────────────
  let modalOpen = localStorage.getItem("forge-modal-open") === "true";
  // ── Log State ───────────────────────────────────────
  const logs = [];
  const MAX_LOGS = 50;
  let logIdCounter = 0;
  let unseenCount = 0;
  // Track which log entries are expanded
  const expandedLogIds = new Set();
  let logsExpanded = false;
  const badgeEl = () => document.querySelector("#forge-trigger .forge-badge");

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
    const listEl = document.getElementById("forge-logs-list");
    const countEl = document.getElementById("forge-logs-count");
    if (!listEl || !countEl) return;

    countEl.textContent = String(logs.length);

    listEl.innerHTML = logs
      .map((entry) => {
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
      })
      .join("");
  }

  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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
      try {
        entry.request = JSON.parse(options.body);
      } catch {
        entry.request = options.body;
      }
    }

    const start = performance.now();
    try {
      const response = await originalFetch.apply(this, args);
      entry.duration_ms = Math.round(performance.now() - start);
      entry.status = response.status;

      const clone = response.clone();
      clone.text().then((text) => {
        try {
          entry.response = JSON.parse(text);
        } catch {
          entry.response = text;
        }
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
      <div class="forge-footer">
        <span id="forge-sse-status">SSE: connecting...</span>
        <button id="forge-reload">Reload Page</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

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

  // ── SSE Connection ──────────────────────────────────
  const sseStatusEl = document.getElementById("forge-sse-status");
  let sseCount = 0;

  const source = new EventSource("/ops/events");
  source.onopen = () => {
    sseStatusEl.textContent = "SSE: connected";
  };
  source.onmessage = () => {
    sseCount += 1;
    sseStatusEl.textContent = `SSE: connected (${sseCount} events)`;
  };
  source.onerror = () => {
    sseStatusEl.textContent = "SSE: reconnecting...";
  };

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
    unseenCount = 0;
    const b = badgeEl();
    if (b) b.textContent = "";
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
