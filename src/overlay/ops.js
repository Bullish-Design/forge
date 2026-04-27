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
  document.body.appendChild(backdrop);

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
