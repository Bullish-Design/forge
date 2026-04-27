(() => {
  const overlay = document.createElement("aside");
  overlay.id = "forge-demo-overlay";
  overlay.innerHTML = `
    <header>Forge Overlay Demo</header>
    <div class="body">
      <div class="row">SSE events: <span id="forge-demo-count" class="badge">0</span></div>
      <div class="row" id="forge-demo-status">status: connecting...</div>
      <div class="row">
        <label for="forge-demo-instruction">Prompt</label>
        <textarea id="forge-demo-instruction" rows="4">Add a concise update with 2-3 actionable bullets for this note.</textarea>
      </div>
      <div class="actions">
        <button id="forge-demo-health">API health</button>
        <button id="forge-demo-apply">Apply prompt</button>
        <button id="forge-demo-undo">Undo</button>
      </div>
      <pre id="forge-demo-output">Waiting for interaction...</pre>
    </div>
  `;
  document.body.appendChild(overlay);

  const countEl = document.getElementById("forge-demo-count");
  const statusEl = document.getElementById("forge-demo-status");
  const outputEl = document.getElementById("forge-demo-output");
  const instructionEl = document.getElementById("forge-demo-instruction");

  let count = 0;

  const setOutput = (value) => {
    outputEl.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  };

  const source = new EventSource("/ops/events");
  source.onopen = () => {
    statusEl.textContent = "status: connected";
  };
  source.onmessage = (event) => {
    count += 1;
    countEl.textContent = String(count);
    setOutput({ event: "rebuild", payload: event.data });
  };
  source.onerror = () => {
    statusEl.textContent = "status: reconnecting...";
  };

  const postJson = async (path, payload) => {
    const response = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await response.text();
    try {
      return JSON.parse(text);
    } catch (_error) {
      return { status: response.status, body: text };
    }
  };

  document.getElementById("forge-demo-health").addEventListener("click", async () => {
    const response = await fetch("/api/health");
    const data = await response.json();
    setOutput(data);
  });

  document.getElementById("forge-demo-apply").addEventListener("click", async () => {
    const instruction = instructionEl.value.trim() || "Add a concise useful update for this note.";
    const data = await postJson("/api/agent/apply", {
      instruction,
      current_file: "projects/forge-v2.md",
    });
    setOutput(data);
  });

  document.getElementById("forge-demo-undo").addEventListener("click", async () => {
    const data = await postJson("/api/undo", {});
    setOutput(data);
  });
})();
