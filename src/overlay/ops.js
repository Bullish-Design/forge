(() => {
  let modalOpen = localStorage.getItem("forge-modal-open") === "true";

  const LOGS_STORAGE_KEY = "forge-overlay-logs-v1";
  const JOBS_STORAGE_KEY = "forge-overlay-jobs-v1";
  const logs = [];
  const MAX_LOGS = 50;
  let logIdCounter = 0;
  let unseenCount = 0;

  const expandedGlobalLogIds = new Set();
  const expandedPageLogIds = new Set();
  let logsExpanded = false;
  let globalLogsExpanded = false;
  let pageLogsExpanded = false;

  const JOB_POLL_INITIAL_MS = 500;
  const JOB_POLL_MAX_MS = 3000;
  const JOB_POLL_BACKOFF = 2;
  const JOB_POLL_TIMEOUT_MS = 130000;
  const JOB_MAX_TRANSIENT_ERRORS = 3;
  const MAX_JOBS = 30;

  let activeJob = null;
  let pollAbortController = null;
  let recentJobs = [];

  const badgeEl = () => document.querySelector("#forge-trigger .forge-badge");

  function loadPersistedLogs() {
    try {
      const raw = localStorage.getItem(LOGS_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return;
      const sliced = parsed.slice(0, MAX_LOGS);
      logs.splice(0, logs.length, ...sliced);
      for (const entry of logs) {
        if (entry && typeof entry.id === "number" && entry.id > logIdCounter) logIdCounter = entry.id;
      }
    } catch {}
  }

  function persistLogs() {
    try {
      localStorage.setItem(LOGS_STORAGE_KEY, JSON.stringify(logs.slice(0, MAX_LOGS)));
    } catch {}
  }

  function loadPersistedJobs() {
    try {
      const raw = localStorage.getItem(JOBS_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return;
      recentJobs = parsed.slice(0, MAX_JOBS);
      const unfinished = recentJobs.find((job) => !isTerminalStatus(job.status));
      if (unfinished) activeJob = unfinished;
    } catch {
      recentJobs = [];
    }
  }

  function persistJobs() {
    try {
      localStorage.setItem(JOBS_STORAGE_KEY, JSON.stringify(recentJobs.slice(0, MAX_JOBS)));
    } catch {}
  }

  function upsertJob(job) {
    const idx = recentJobs.findIndex((j) => j.id === job.id);
    if (idx >= 0) {
      recentJobs[idx] = { ...recentJobs[idx], ...job };
    } else {
      recentJobs.unshift(job);
      if (recentJobs.length > MAX_JOBS) recentJobs.length = MAX_JOBS;
    }
    persistJobs();
    renderJobStatus();
  }

  function addLog(entry) {
    logs.unshift(entry);
    if (logs.length > MAX_LOGS) logs.pop();
    persistLogs();
    if (!modalOpen) {
      unseenCount++;
      const b = badgeEl();
      if (b) b.textContent = String(unseenCount);
    }
    renderLogs();
  }

  function renderLogs() {
    const countEl = document.getElementById("forge-logs-count");
    const globalCountEl = document.getElementById("forge-logs-global-count");
    const pageCountEl = document.getElementById("forge-logs-page-count");
    const globalListEl = document.getElementById("forge-logs-global-list");
    const pageListEl = document.getElementById("forge-logs-page-list");
    if (!countEl || !globalCountEl || !pageCountEl || !globalListEl || !pageListEl) return;

    const currentFile = detectCurrentFile();
    const pageLogs = logs.filter((entry) => entry.page_file === currentFile);

    countEl.textContent = String(logs.length);
    globalCountEl.textContent = String(logs.length);
    pageCountEl.textContent = String(pageLogs.length);

    renderLogList(logs, globalListEl, expandedGlobalLogIds);
    renderLogList(pageLogs, pageListEl, expandedPageLogIds);
  }

  function renderLogList(entries, listEl, expandedSet) {
    listEl.innerHTML = entries
      .map((entry) => {
        const isExpanded = expandedSet.has(entry.id);
        const statusClass = entry.status >= 400 || entry.error ? "error" : "";
        const statusText = entry.error ? "ERR" : String(entry.status);
        const duration = entry.duration_ms > 0 ? (entry.duration_ms / 1000).toFixed(1) + "s" : "...";
        const shortUrl = entry.url.replace(/^\/(api|v1)\//, "");
        const meta = extractLogMeta(entry.response);
        const metaPieces = [];
        if (meta.model) metaPieces.push(`<span class="forge-log-meta-item">${escapeHtml(meta.model)}</span>`);
        if (meta.tokens) metaPieces.push(`<span class="forge-log-meta-item">${escapeHtml(meta.tokens)}</span>`);
        const metaHtml = metaPieces.length ? `<span class="forge-log-meta">${metaPieces.join("")}</span>` : "";

        let detailHtml = "";
        if (entry.request != null) {
          const reqStr = typeof entry.request === "string" ? entry.request : JSON.stringify(entry.request, null, 2);
          detailHtml += `<div class="forge-log-detail-label">Request</div><pre>${escapeHtml(reqStr)}</pre>`;
        }
        if (entry.response != null) {
          const resStr = typeof entry.response === "string" ? entry.response : JSON.stringify(entry.response, null, 2);
          detailHtml += `<div class="forge-log-detail-label">Response</div><pre>${escapeHtml(resStr)}</pre>`;
        }
        if (entry.error) detailHtml += `<div class="forge-log-detail-label">Error</div><pre>${escapeHtml(entry.error)}</pre>`;

        return `
        <div class="forge-log-entry" data-log-id="${entry.id}">
          <div class="forge-log-summary">
            <span class="forge-log-method">${entry.method}</span>
            <span class="forge-log-url">${escapeHtml(shortUrl)}</span>
            ${metaHtml}
            <span class="forge-log-status ${statusClass}">${statusText}</span>
            <span class="forge-log-duration">${duration}</span>
          </div>
          <div class="forge-log-detail ${isExpanded ? "open" : ""}">${detailHtml}</div>
        </div>
      `;
      })
      .join("");
  }

  function extractLogMeta(response) {
    if (!response || typeof response !== "object") return {};
    const model = findFirstString(response, ["model", "llm_model", "model_name"]);
    const usage = findUsageObject(response);
    const totalTokens = typeof usage?.total_tokens === "number" ? usage.total_tokens : typeof usage?.totalTokens === "number" ? usage.totalTokens : null;
    const inputTokens = typeof usage?.prompt_tokens === "number" ? usage.prompt_tokens : typeof usage?.input_tokens === "number" ? usage.input_tokens : null;
    const outputTokens = typeof usage?.completion_tokens === "number" ? usage.completion_tokens : typeof usage?.output_tokens === "number" ? usage.output_tokens : null;
    let tokens = null;
    if (totalTokens != null) tokens = `${totalTokens} tok`;
    else if (inputTokens != null || outputTokens != null) tokens = `${inputTokens != null ? String(inputTokens) : "?"}/${outputTokens != null ? String(outputTokens) : "?"} tok`;
    return { model, tokens };
  }

  function findUsageObject(value) {
    if (!value || typeof value !== "object") return null;
    if (value.usage && typeof value.usage === "object") return value.usage;
    if (value.metrics?.usage && typeof value.metrics.usage === "object") return value.metrics.usage;
    if (value.result?.usage && typeof value.result.usage === "object") return value.result.usage;
    return null;
  }

  function findFirstString(value, keys) {
    if (!value || typeof value !== "object") return null;
    for (const key of keys) {
      if (typeof value[key] === "string" && value[key].trim()) return value[key].trim();
    }
    if (value.result && typeof value.result === "object") {
      for (const key of keys) {
        if (typeof value.result[key] === "string" && value.result[key].trim()) return value.result[key].trim();
      }
    }
    return null;
  }

  function escapeHtml(str) {
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function isTerminalStatus(status) {
    return status === "succeeded" || status === "failed";
  }

  function updateActionButtons() {
    const busy = !!activeJob && !isTerminalStatus(activeJob.status);
    const sendBtn = document.getElementById("forge-send");
    const undoBtn = document.getElementById("forge-undo");
    if (sendBtn) sendBtn.disabled = busy;
    if (undoBtn) undoBtn.disabled = busy;
  }

  function renderJobStatus() {
    const statusEl = document.getElementById("forge-job-status");
    if (!statusEl) return;
    if (!activeJob) {
      statusEl.textContent = "No active job.";
      statusEl.className = "forge-job-status";
      updateActionButtons();
      return;
    }
    const cls = `forge-job-status ${activeJob.status || "queued"}`;
    statusEl.className = cls;
    const summary = activeJob.result?.summary || activeJob.error || activeJob.result?.error || "";
    statusEl.textContent = `Job ${activeJob.id} • ${activeJob.operation} • ${activeJob.status}${summary ? ` • ${summary}` : ""}`;
    updateActionButtons();
  }

  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const [resource, options] = args;
    const url = typeof resource === "string" ? resource : resource.url;

    if (!(url.includes("/api/") || url.includes("/v1/"))) return originalFetch.apply(this, args);

    const entry = {
      id: ++logIdCounter,
      timestamp: Date.now(),
      method: (options && options.method) || "GET",
      url,
      page_file: detectCurrentFile(),
      page_path: window.location.pathname,
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
        persistLogs();
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

  loadPersistedLogs();
  loadPersistedJobs();

  const trigger = document.createElement("button");
  trigger.id = "forge-trigger";
  trigger.setAttribute("aria-label", "Open Forge overlay");
  trigger.innerHTML = `<span aria-hidden="true">\u2692</span><span class="forge-badge"></span>`;
  document.body.appendChild(trigger);

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

        <div class="forge-section">
          <div id="forge-job-status" class="forge-job-status">No active job.</div>
        </div>

        <div class="forge-section" style="margin-top:12px;">
          <button class="forge-logs-header" id="forge-logs-toggle">
            <span class="forge-caret" id="forge-logs-caret">\u25B8</span>
            <span>Logs (<span id="forge-logs-count">0</span>)</span>
          </button>
          <div class="forge-logs-list" id="forge-logs-list">
            <button class="forge-sublogs-header" id="forge-logs-global-toggle">
              <span class="forge-caret" id="forge-logs-global-caret">\u25B8</span>
              <span>Global (<span id="forge-logs-global-count">0</span>)</span>
            </button>
            <div class="forge-sublogs-list" id="forge-logs-global-list"></div>
            <button class="forge-sublogs-header" id="forge-logs-page-toggle">
              <span class="forge-caret" id="forge-logs-page-caret">\u25B8</span>
              <span>This Page (<span id="forge-logs-page-count">0</span>)</span>
            </button>
            <div class="forge-sublogs-list" id="forge-logs-page-list"></div>
          </div>
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

  document.getElementById("forge-logs-toggle").addEventListener("click", () => {
    logsExpanded = !logsExpanded;
    document.getElementById("forge-logs-list").classList.toggle("open", logsExpanded);
    document.getElementById("forge-logs-caret").classList.toggle("open", logsExpanded);
  });

  document.getElementById("forge-logs-global-toggle").addEventListener("click", () => {
    globalLogsExpanded = !globalLogsExpanded;
    document.getElementById("forge-logs-global-list").classList.toggle("open", globalLogsExpanded);
    document.getElementById("forge-logs-global-caret").classList.toggle("open", globalLogsExpanded);
  });

  document.getElementById("forge-logs-page-toggle").addEventListener("click", () => {
    pageLogsExpanded = !pageLogsExpanded;
    document.getElementById("forge-logs-page-list").classList.toggle("open", pageLogsExpanded);
    document.getElementById("forge-logs-page-caret").classList.toggle("open", pageLogsExpanded);
  });

  function attachLogEntryToggle(listId, expandedSet) {
    const list = document.getElementById(listId);
    list.addEventListener("click", (e) => {
      const entry = e.target.closest(".forge-log-entry");
      if (!entry) return;
      const logId = Number(entry.dataset.logId);
      const detail = entry.querySelector(".forge-log-detail");
      if (!detail) return;
      if (expandedSet.has(logId)) {
        expandedSet.delete(logId);
        detail.classList.remove("open");
      } else {
        expandedSet.add(logId);
        detail.classList.add("open");
      }
    });
  }

  attachLogEntryToggle("forge-logs-global-list", expandedGlobalLogIds);
  attachLogEntryToggle("forge-logs-page-list", expandedPageLogIds);

  const syncCurrentFilePathAndLogs = () => {
    syncCurrentFilePath();
    renderLogs();
  };

  function detectCurrentFile() {
    const p = window.location.pathname.replace(/^\//, "").replace(/\/$/, "");
    if (!p) return "index.md";
    return p.replace(/\.html$/, "") + ".md";
  }

  const filePathEl = document.getElementById("forge-file-path");
  const fileEditBtn = document.getElementById("forge-file-edit");
  let fileEditing = false;
  function syncCurrentFilePath() {
    if (fileEditing) return;
    filePathEl.value = detectCurrentFile();
  }

  syncCurrentFilePathAndLogs();

  fileEditBtn.addEventListener("click", () => {
    fileEditing = !fileEditing;
    filePathEl.readOnly = !fileEditing;
    fileEditBtn.textContent = fileEditing ? "\u2713" : "\u270E";
    if (fileEditing) filePathEl.focus();
  });

  window.addEventListener("popstate", syncCurrentFilePathAndLogs);
  window.addEventListener("hashchange", syncCurrentFilePathAndLogs);
  const originalPushState = history.pushState;
  history.pushState = function (...args) {
    const result = originalPushState.apply(this, args);
    syncCurrentFilePathAndLogs();
    return result;
  };
  const originalReplaceState = history.replaceState;
  history.replaceState = function (...args) {
    const result = originalReplaceState.apply(this, args);
    syncCurrentFilePathAndLogs();
    return result;
  };

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
      return { status: response.status, data: JSON.parse(text) };
    } catch {
      return { status: response.status, data: { body: text } };
    }
  }

  async function submitJob(operation, payload) {
    const body = { operation };
    if (payload) body.payload = payload;
    const result = await postJson("/v1/jobs", body);
    if (result.status === 502 && result.data?.error === "upstream_unavailable") throw new Error("upstream_unavailable");
    if (result.status === 504 && result.data?.error === "upstream_timeout") throw new Error("upstream_timeout");
    if (result.status !== 202 && result.status !== 200) {
      throw new Error(result.data?.error || `submit failed (${result.status})`);
    }
    return result.data;
  }

  async function fetchJob(jobId, signal) {
    const response = await fetch(`/v1/jobs/${jobId}`, { signal });
    const text = await response.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`invalid job response (${response.status})`);
    }
    if (!response.ok) throw new Error(data?.error || `poll failed (${response.status})`);
    return data;
  }

  async function pollJobUntilTerminal(jobId) {
    const startTime = Date.now();
    let interval = JOB_POLL_INITIAL_MS;
    let consecutiveErrors = 0;

    pollAbortController = new AbortController();
    const signal = pollAbortController.signal;

    while (true) {
      if (signal.aborted) throw new Error("poll cancelled");
      if (Date.now() - startTime > JOB_POLL_TIMEOUT_MS) throw new Error(`Job ${jobId} timed out after ${Math.round((Date.now() - startTime) / 1000)}s`);

      await new Promise((resolve) => setTimeout(resolve, interval));
      try {
        const job = await fetchJob(jobId, signal);
        consecutiveErrors = 0;
        activeJob = job;
        upsertJob(job);
        if (isTerminalStatus(job.status)) return job;
        interval = Math.min(interval * JOB_POLL_BACKOFF, JOB_POLL_MAX_MS);
      } catch (err) {
        if (signal.aborted) throw err;
        consecutiveErrors += 1;
        if (consecutiveErrors >= JOB_MAX_TRANSIENT_ERRORS) throw new Error(`polling failed: ${err.message}`);
      }
    }
  }

  async function submitAndTrack(operation, payload) {
    const accepted = await submitJob(operation, payload);
    activeJob = {
      id: accepted.job_id,
      operation,
      status: accepted.status || "queued",
      created_at: accepted.created_at,
      request: payload || {},
      result: null,
      error: null,
    };
    upsertJob(activeJob);
    renderJobStatus();

    const finalJob = await pollJobUntilTerminal(accepted.job_id);
    activeJob = finalJob;
    upsertJob(finalJob);
    return finalJob;
  }

  document.getElementById("forge-send").addEventListener("click", async () => {
    const instruction = instructionEl.value.trim() || "Add a concise useful update for this note.";
    const currentFile = filePathEl.value.trim();
    setOutput("Submitting apply job...");
    try {
      const finalJob = await submitAndTrack("apply", { instruction, current_file: currentFile });
      if (finalJob.status === "succeeded") {
        setOutput(finalJob.result || finalJob);
      } else {
        setOutput({ error: finalJob.error || finalJob.result?.error || "job failed", job: finalJob });
      }
    } catch (err) {
      if (err.message === "upstream_timeout") {
        setOutput({ error: "upstream_timeout", detail: "Overlay proxy timed out waiting for upstream. Check overlay timeout or reduce prompt scope." });
      } else if (err.message === "upstream_unavailable") {
        setOutput({ error: "upstream_unavailable", detail: "Overlay proxy could not reach obsidian-agent upstream." });
      } else {
        setOutput("Error: " + err.message);
      }
    } finally {
      updateActionButtons();
    }
  });

  document.getElementById("forge-undo").addEventListener("click", async () => {
    setOutput("Submitting undo job...");
    try {
      const finalJob = await submitAndTrack("undo", null);
      if (finalJob.status === "succeeded") setOutput(finalJob.result || finalJob);
      else setOutput({ error: finalJob.error || finalJob.result?.error || "undo failed", job: finalJob });
    } catch (err) {
      if (err.message === "upstream_timeout") {
        setOutput({ error: "upstream_timeout", detail: "Overlay proxy timed out waiting for upstream during undo." });
      } else if (err.message === "upstream_unavailable") {
        setOutput({ error: "upstream_unavailable", detail: "Overlay proxy could not reach obsidian-agent upstream during undo." });
      } else {
        setOutput("Error: " + err.message);
      }
    } finally {
      updateActionButtons();
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

  document.getElementById("forge-modal").addEventListener("click", (e) => {
    e.stopPropagation();
  });

  function openModal() {
    syncCurrentFilePathAndLogs();
    modalOpen = true;
    localStorage.setItem("forge-modal-open", "true");
    backdrop.classList.add("open");
    trigger.style.display = "none";
    unseenCount = 0;
    const b = badgeEl();
    if (b) b.textContent = "";
    renderJobStatus();
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

  document.getElementById("forge-reload").addEventListener("click", () => {
    location.reload();
  });

  if (activeJob && !isTerminalStatus(activeJob.status)) {
    pollJobUntilTerminal(activeJob.id)
      .then((job) => {
        activeJob = job;
        upsertJob(job);
      })
      .catch(() => {});
  }

  renderJobStatus();
  if (modalOpen) openModal();
})();
