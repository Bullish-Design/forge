# QUEUE_REFACTOR_IMPLEMENTATION_GUIDE

## Goal
Migrate Forge from synchronous agent calls to queue/job-based workflows, now that:
- `obsidian-agent` provides async job APIs (`/v1/jobs*`)
- `forge-overlay` proxies both `/api/*` and `/v1/*`

This gives the UI visibility into job lifecycle (queued/running/succeeded/failed), resilience to proxy timeouts on long operations, and the ability to survive page reloads mid-operation.

## Scope
In scope:
- Production overlay UI behavior in this repo (`src/overlay/*`)
- Demo/harness scripts under `demo/`
- Docker validation under `docker/`
- Documentation updates describing new request flow

Out of scope:
- Agent-side queue internals
- Overlay repo internals (already refactored)
- Cancellation/durability/retry-idempotency policy work

---

## Reference: Actual API Contracts

These are the models implemented in `obsidian-agent` — all code must conform to them exactly.

### POST /v1/jobs (Submit Job)

**Request body (`JobSubmitRequest`):**
```json
{
  "operation": "apply",
  "payload": {
    "instruction": "Add a summary section",
    "current_file": "projects/forge-v2.md",
    "interface_id": null,
    "scope": null,
    "intent": null,
    "allowed_write_scope": "target_only"
  }
}
```
- `operation`: `"apply"` | `"undo"` (required)
- `payload`: required for `"apply"`, must be `null` or omitted for `"undo"`
- `payload.instruction`: string (required for apply)
- `payload.current_file`: string | null
- `payload.interface_id`: string | null
- `payload.scope`: string | null
- `payload.intent`: `"rewrite"` | `"summarize"` | `"insert_below"` | `"annotate"` | `"extract_tasks"` | null
- `payload.allowed_write_scope`: `"target_only"` | `"target_plus_frontmatter"` | `"unrestricted"` (default: `"target_only"`)

**Response (202 Accepted):**
```json
{
  "job_id": "abc123",
  "status": "queued",
  "created_at": "2026-05-07T12:00:00Z"
}
```

### GET /v1/jobs/{job_id} (Poll Job)

**Response (200):**
```json
{
  "id": "abc123",
  "operation": "apply",
  "status": "succeeded",
  "created_at": "2026-05-07T12:00:00Z",
  "started_at": "2026-05-07T12:00:01Z",
  "finished_at": "2026-05-07T12:00:05Z",
  "request": { "instruction": "...", "current_file": "..." },
  "result": {
    "ok": true,
    "updated": true,
    "summary": "Added summary section",
    "changed_files": ["projects/forge-v2.md"],
    "error": null,
    "warning": null
  },
  "error": null
}
```

- `status`: `"queued"` | `"running"` | `"succeeded"` | `"failed"`
- `result`: `OperationResult | null` (populated on terminal status)
- `error`: `string | null` (populated on `"failed"`)

### GET /v1/jobs (List Jobs)

**Query params:** `?limit=50` (1-200, default 50)

**Response (200):**
```json
{
  "jobs": [ /* array of JobResponse objects */ ]
}
```

### Overlay Proxy Error Mapping

The forge-overlay proxy maps transport failures:
- `httpx.TimeoutException` → HTTP 504, body `{"error": "upstream_timeout"}`
- `httpx.HTTPError` (other) → HTTP 502, body `{"error": "upstream_unavailable"}`
- All other upstream responses (including 4xx/5xx) pass through unchanged.

Proxy timeout: configurable (default 600s). Agent operation timeout: 120s.

---

## Detailed Task Breakdown (Execution Order)

1. Add `/v1/jobs*` stubs to `demo/tools/dummy_api_server.py`
2. Refactor `src/overlay/ops.js` for submit+poll flow
3. Add queue-related visual styles in `src/overlay/ops.css`
4. Update overlay docs in `src/overlay/README.md`
5. Update demo runner `demo/scripts/run_demo.py`
6. Update demo validator `demo/scripts/validate_full_stack.py`
7. Extend Docker validator `docker/validate.py`
8. Update demo docs (`demo/README.md`, `demo/DEMO_SCRIPT.md`)
9. Run full validation pass and fix regressions

---

## Step 1: Add `/v1/jobs*` Stubs to Dummy API Server

**File:** `demo/tools/dummy_api_server.py`

**Purpose:** Provide a deterministic local backend that simulates the job lifecycle so the UI can be developed and tested without the real agent running.

### 1.1 Add Job Data Model

Add these imports and the job model class after the existing `DemoState` class definition:

```python
import uuid
from datetime import datetime, timezone
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    operation: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    request: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    # Internal: when to transition to next state
    _transition_at: float = 0.0
```

### 1.2 Add Job Queue to DemoState

Add these fields to the `DemoState` dataclass:

```python
    jobs: list[Job] = field(default_factory=list)
    job_completion_delay_s: float = 2.0  # configurable simulated processing time
```

Add these methods to `DemoState`:

```python
    def submit_job(self, operation: str, payload: dict[str, Any] | None) -> Job:
        with self.lock:
            now = datetime.now(timezone.utc).isoformat()
            job = Job(
                id=str(uuid.uuid4()),
                operation=operation,
                status=JobStatus.QUEUED,
                created_at=now,
                request=payload or {},
                _transition_at=time.time() + 0.3,  # queued for 300ms
            )
            self.jobs.append(job)
            return job

    def get_job(self, job_id: str) -> Job | None:
        with self.lock:
            for job in self.jobs:
                if job.id == job_id:
                    self._advance_job(job)
                    return job
            return None

    def list_jobs(self, limit: int = 50) -> list[Job]:
        with self.lock:
            for job in self.jobs:
                self._advance_job(job)
            return list(reversed(self.jobs[-limit:]))

    def _advance_job(self, job: Job) -> None:
        """Advance job state machine based on elapsed time."""
        now = time.time()
        if job.status == JobStatus.QUEUED and now >= job._transition_at:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc).isoformat()
            job._transition_at = now + self.job_completion_delay_s

        if job.status == JobStatus.RUNNING and now >= job._transition_at:
            job.finished_at = datetime.now(timezone.utc).isoformat()
            # Check for failure trigger
            instruction = job.request.get("instruction", "")
            if "FAIL" in instruction:
                job.status = JobStatus.FAILED
                job.error = "Simulated failure triggered by FAIL keyword in instruction"
                job.result = {"ok": False, "updated": False, "summary": "", "changed_files": [], "error": job.error, "warning": None}
            else:
                # Actually perform the operation
                if job.operation == "apply":
                    result = self.apply(
                        instruction=instruction or "no instruction",
                        current_file=job.request.get("current_file"),
                    )
                elif job.operation == "undo":
                    result = self.undo()
                else:
                    result = {"ok": False, "error": f"unknown operation: {job.operation}"}
                job.status = JobStatus.SUCCEEDED if result.get("ok") else JobStatus.FAILED
                job.result = {
                    "ok": result.get("ok", False),
                    "updated": result.get("ok", False),
                    "summary": result.get("summary", ""),
                    "changed_files": result.get("changed_files", []),
                    "error": result.get("error"),
                    "warning": None,
                }
                if not result.get("ok"):
                    job.error = result.get("error", "operation failed")

    def _job_to_dict(self, job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "operation": job.operation,
            "status": job.status.value,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "request": job.request,
            "result": job.result,
            "error": job.error,
        }
```

### 1.3 Add HTTP Handlers for /v1/jobs

Add these route handlers in the `Handler` class. In `do_GET`:

```python
        # Add before the final 404 handler:
        if self.path.startswith("/v1/jobs/"):
            job_id = self.path.split("/v1/jobs/")[1].rstrip("/")
            job = self.state.get_job(job_id)
            if job is None:
                self._send_json({"error": f"job not found: {job_id}"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json(self.state._job_to_dict(job))
            return

        if self.path.startswith("/v1/jobs"):
            # Parse ?limit=N
            limit = 50
            if "?" in self.path:
                query = self.path.split("?", 1)[1]
                for part in query.split("&"):
                    if part.startswith("limit="):
                        try:
                            limit = max(1, min(200, int(part.split("=")[1])))
                        except ValueError:
                            pass
            jobs = self.state.list_jobs(limit=limit)
            self._send_json({"jobs": [self.state._job_to_dict(j) for j in jobs]})
            return
```

In `do_POST`:

```python
        # Add before the final 404 handler:
        if self.path.rstrip("/") == "/v1/jobs":
            try:
                payload = self._read_json()
                operation = payload.get("operation")
                if operation not in {"apply", "undo"}:
                    self._send_json({"error": "operation must be 'apply' or 'undo'"}, status=HTTPStatus.BAD_REQUEST)
                    return
                job_payload = payload.get("payload")
                if operation == "apply" and not job_payload:
                    self._send_json({"error": "payload required for apply operation"}, status=HTTPStatus.BAD_REQUEST)
                    return
                job = self.state.submit_job(operation, job_payload)
                self._send_json(
                    {"job_id": job.id, "status": job.status.value, "created_at": job.created_at},
                    status=HTTPStatus.ACCEPTED,
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
```

### 1.4 Add `--job-delay` CLI Argument

In `parse_args()`:

```python
    parser.add_argument("--job-delay", type=float, default=2.0, help="Simulated job processing time in seconds")
```

In `main()`:

```python
    state = DemoState(vault_dir=args.vault_dir, job_completion_delay_s=args.job_delay)
```

### 1.5 Add `_send_json` Support for 202

The existing `_send_json` method already accepts a `status` parameter so this works without changes.

### Step 1 Validation

Start the dummy server and run these curl commands:

```bash
# Start server
uv run demo/tools/dummy_api_server.py --vault-dir /tmp/test-vault --job-delay 2

# Create test vault file
mkdir -p /tmp/test-vault/projects
echo "# Test" > /tmp/test-vault/projects/forge-v2.md

# Submit apply job — expect 202 with job_id
curl -s -X POST http://127.0.0.1:18081/v1/jobs \
  -H "content-type: application/json" \
  -d '{"operation":"apply","payload":{"instruction":"Add a test section","current_file":"projects/forge-v2.md"}}' \
  | python3 -m json.tool
# Expected: {"job_id": "...", "status": "queued", "created_at": "..."}

# Poll immediately — expect "queued" or "running"
JOB_ID=<paste job_id from above>
curl -s http://127.0.0.1:18081/v1/jobs/$JOB_ID | python3 -m json.tool

# Wait 3s and poll again — expect "succeeded" with result
sleep 3
curl -s http://127.0.0.1:18081/v1/jobs/$JOB_ID | python3 -m json.tool
# Expected: status="succeeded", result.ok=true, result.changed_files=["projects/forge-v2.md"]

# Verify file was mutated
cat /tmp/test-vault/projects/forge-v2.md

# Submit undo job
curl -s -X POST http://127.0.0.1:18081/v1/jobs \
  -H "content-type: application/json" \
  -d '{"operation":"undo"}' \
  | python3 -m json.tool

# Wait and poll undo job
sleep 3
UNDO_ID=<paste job_id from undo response>
curl -s http://127.0.0.1:18081/v1/jobs/$UNDO_ID | python3 -m json.tool
# Expected: status="succeeded", result.summary="Reverted latest dummy update"

# Verify undo worked
cat /tmp/test-vault/projects/forge-v2.md

# Test failure trigger
curl -s -X POST http://127.0.0.1:18081/v1/jobs \
  -H "content-type: application/json" \
  -d '{"operation":"apply","payload":{"instruction":"FAIL this operation","current_file":"projects/forge-v2.md"}}' \
  | python3 -m json.tool
sleep 3
FAIL_ID=<paste job_id>
curl -s http://127.0.0.1:18081/v1/jobs/$FAIL_ID | python3 -m json.tool
# Expected: status="failed", error contains "FAIL keyword"

# Test job listing
curl -s "http://127.0.0.1:18081/v1/jobs?limit=10" | python3 -m json.tool
# Expected: {"jobs": [...]} with all submitted jobs

# Test validation errors
curl -s -X POST http://127.0.0.1:18081/v1/jobs \
  -H "content-type: application/json" \
  -d '{"operation":"invalid"}' -w "\n%{http_code}"
# Expected: 400

curl -s -X POST http://127.0.0.1:18081/v1/jobs \
  -H "content-type: application/json" \
  -d '{"operation":"apply"}' -w "\n%{http_code}"
# Expected: 400 (missing payload)
```

**All checks must pass before proceeding to Step 2.**

---

## Step 2: Refactor `src/overlay/ops.js`

**File:** `src/overlay/ops.js`

This is the most complex step. We will modify the file in logical sections.

### 2.1 Add Job Constants

Add these constants immediately after the existing state declarations (after line 16 in current file):

```javascript
  // ── Job Queue Constants ────────────────────────────
  const JOB_POLL_INITIAL_MS = 500;
  const JOB_POLL_MAX_MS = 3000;
  const JOB_POLL_BACKOFF = 2;
  const JOB_POLL_TIMEOUT_MS = 130000;
  const JOB_MAX_TRANSIENT_ERRORS = 3;

  // ── Job State ─────────────────────────────────────
  let activeJob = null; // { id, operation, status, created_at, started_at, finished_at, result, error }
  let pollAbortController = null;
```

### 2.2 Add Job Helper Functions

Add these helper functions after the existing `postJson` function (after line 406 in current file):

```javascript
  // ── Job API Helpers ────────────────────────────────
  function isTerminalStatus(status) {
    return status === "succeeded" || status === "failed";
  }

  async function submitJob(operation, payload) {
    const body = { operation };
    if (payload) body.payload = payload;
    const response = await fetch("/v1/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await response.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`Invalid JSON from /v1/jobs: ${text.slice(0, 200)}`);
    }
    if (response.status === 502) {
      throw new Error("upstream_unavailable");
    }
    if (response.status === 504) {
      throw new Error("upstream_timeout");
    }
    if (response.status !== 202 && response.status !== 200) {
      throw new Error(data.error || `Unexpected status ${response.status}`);
    }
    return data;
  }

  async function fetchJob(jobId, signal) {
    const response = await fetch(`/v1/jobs/${jobId}`, { signal });
    if (!response.ok) {
      throw new Error(`Poll failed: HTTP ${response.status}`);
    }
    const text = await response.text();
    try {
      return JSON.parse(text);
    } catch {
      throw new Error(`Invalid JSON from poll: ${text.slice(0, 200)}`);
    }
  }

  async function pollJobUntilTerminal(jobId) {
    const startTime = Date.now();
    let interval = JOB_POLL_INITIAL_MS;
    let consecutiveErrors = 0;

    pollAbortController = new AbortController();
    const signal = pollAbortController.signal;

    while (true) {
      if (signal.aborted) {
        throw new Error("Poll cancelled");
      }

      const elapsed = Date.now() - startTime;
      if (elapsed > JOB_POLL_TIMEOUT_MS) {
        throw new Error(`Job ${jobId} timed out after ${Math.round(elapsed / 1000)}s. Check job status manually.`);
      }

      await new Promise((resolve) => setTimeout(resolve, interval));

      try {
        const job = await fetchJob(jobId, signal);
        consecutiveErrors = 0;

        // Update active job state for UI rendering
        activeJob = job;
        renderJobStatus();

        if (isTerminalStatus(job.status)) {
          return job;
        }

        // Exponential backoff
        interval = Math.min(interval * JOB_POLL_BACKOFF, JOB_POLL_MAX_MS);
      } catch (err) {
        if (signal.aborted) throw err;
        consecutiveErrors++;
        if (consecutiveErrors >= JOB_MAX_TRANSIENT_ERRORS) {
          throw new Error(`Polling failed after ${consecutiveErrors} consecutive errors: ${err.message}`);
        }
        // On transient error, keep current interval and retry
      }
    }
  }

  function cancelActivePoll() {
    if (pollAbortController) {
      pollAbortController.abort();
      pollAbortController = null;
    }
  }
```

### 2.3 Add Job Status Rendering

Add this function after the job helpers:

```javascript
  // ── Job Status Rendering ───────────────────────────
  function renderJobStatus() {
    if (!activeJob) return;
    const elapsed = activeJob.started_at
      ? ((activeJob.finished_at ? new Date(activeJob.finished_at) : new Date()) - new Date(activeJob.started_at)) / 1000
      : 0;
    const elapsedStr = elapsed > 0 ? ` (${elapsed.toFixed(1)}s)` : "";

    let statusLine = `[${activeJob.status}] job:${activeJob.id.slice(0, 8)}${elapsedStr}`;

    if (activeJob.status === "succeeded" && activeJob.result) {
      const r = activeJob.result;
      const parts = [statusLine];
      if (r.summary) parts.push(r.summary);
      if (r.changed_files && r.changed_files.length > 0) {
        parts.push(`changed: ${r.changed_files.join(", ")}`);
      }
      if (r.warning) parts.push(`warning: ${r.warning}`);
      setOutput(parts.join("\n"));
    } else if (activeJob.status === "failed") {
      const errorMsg = (activeJob.result && activeJob.result.error) || activeJob.error || "Unknown error";
      setOutput(`${statusLine}\nError: ${errorMsg}`);
    } else {
      setOutput(statusLine);
    }
  }

  function setActionButtonsDisabled(disabled) {
    const sendBtn = document.getElementById("forge-send");
    const undoBtn = document.getElementById("forge-undo");
    if (sendBtn) sendBtn.disabled = disabled;
    if (undoBtn) undoBtn.disabled = disabled;
  }
```

### 2.4 Replace the Send Button Handler

Replace the existing send button event listener (lines 409-428) with:

```javascript
  document.getElementById("forge-send").addEventListener("click", async () => {
    const instruction = instructionEl.value.trim() || "Add a concise useful update for this note.";
    const currentFile = filePathEl.value.trim();
    setOutput("Submitting job...");
    setActionButtonsDisabled(true);

    try {
      // Submit the job
      const accepted = await submitJob("apply", { instruction, current_file: currentFile });
      activeJob = {
        id: accepted.job_id,
        operation: "apply",
        status: accepted.status,
        created_at: accepted.created_at,
        started_at: null,
        finished_at: null,
        result: null,
        error: null,
      };
      setOutput(`[queued] job:${accepted.job_id.slice(0, 8)} — polling for result...`);

      // Poll until terminal
      const finalJob = await pollJobUntilTerminal(accepted.job_id);
      activeJob = finalJob;
      renderJobStatus();
    } catch (err) {
      if (err.message === "upstream_unavailable") {
        setOutput(JSON.stringify({
          error: "upstream_unavailable",
          detail: "Overlay API proxy could not reach the agent. Verify agent is healthy and reachable.",
          attempted_current_file: currentFile,
        }, null, 2));
      } else if (err.message === "upstream_timeout") {
        setOutput(JSON.stringify({
          error: "upstream_timeout",
          detail: "Proxy timed out waiting for agent. Consider reducing prompt scope or increasing proxy timeout.",
          attempted_current_file: currentFile,
        }, null, 2));
      } else {
        setOutput("Error: " + err.message);
      }
    } finally {
      setActionButtonsDisabled(false);
      pollAbortController = null;
    }
  });
```

### 2.5 Replace the Undo Button Handler

Replace the existing undo button event listener (lines 430-438) with:

```javascript
  document.getElementById("forge-undo").addEventListener("click", async () => {
    setOutput("Submitting undo job...");
    setActionButtonsDisabled(true);

    try {
      const accepted = await submitJob("undo", null);
      activeJob = {
        id: accepted.job_id,
        operation: "undo",
        status: accepted.status,
        created_at: accepted.created_at,
        started_at: null,
        finished_at: null,
        result: null,
        error: null,
      };
      setOutput(`[queued] job:${accepted.job_id.slice(0, 8)} — polling for result...`);

      const finalJob = await pollJobUntilTerminal(accepted.job_id);
      activeJob = finalJob;
      renderJobStatus();
    } catch (err) {
      if (err.message === "upstream_unavailable") {
        setOutput(JSON.stringify({
          error: "upstream_unavailable",
          detail: "Overlay API proxy could not reach the agent for undo.",
        }, null, 2));
      } else if (err.message === "upstream_timeout") {
        setOutput(JSON.stringify({
          error: "upstream_timeout",
          detail: "Proxy timed out waiting for undo operation.",
        }, null, 2));
      } else {
        setOutput("Error: " + err.message);
      }
    } finally {
      setActionButtonsDisabled(false);
      pollAbortController = null;
    }
  });
```

### 2.6 Expand Fetch Intercept to Include `/v1/*`

Change line 182 from:

```javascript
    if (!url.includes("/api/")) {
      return originalFetch.apply(this, args);
    }
```

To:

```javascript
    if (!url.includes("/api/") && !url.includes("/v1/")) {
      return originalFetch.apply(this, args);
    }
```

### 2.7 Cancel Polling on Modal Close

Add to the `closeModal` function (add after `backdrop.classList.remove("open");`):

```javascript
    cancelActivePoll();
```

### 2.8 Full Resulting `ops.js` Structure

After all changes, the file structure should be:

```
(() => {
  // ── State ──────────────────────────────────────────
  // (existing modal/log state - unchanged)

  // ── Job Queue Constants ────────────────────────────
  // (new: JOB_POLL_INITIAL_MS, etc.)

  // ── Job State ─────────────────────────────────────
  // (new: activeJob, pollAbortController)

  // ── Log functions ──────────────────────────────────
  // (existing: loadPersistedLogs, persistLogs, addLog, renderLogs, etc. - unchanged)

  // ── Fetch Intercept ────────────────────────────────
  // (modified: filter now includes /v1/)

  // ── Trigger Button + Modal HTML ────────────────────
  // (existing - unchanged)

  // ── Log Viewer Toggle ──────────────────────────────
  // (existing - unchanged)

  // ── Current File Detection ─────────────────────────
  // (existing - unchanged)

  // ── API Helpers ────────────────────────────────────
  // (existing: setOutput, postJson - unchanged)

  // ── Job API Helpers ────────────────────────────────
  // (new: isTerminalStatus, submitJob, fetchJob, pollJobUntilTerminal, cancelActivePoll)

  // ── Job Status Rendering ───────────────────────────
  // (new: renderJobStatus, setActionButtonsDisabled)

  // ── Action Buttons ─────────────────────────────────
  // (modified: send and undo use submit+poll)

  // ── SSE Connection ─────────────────────────────────
  // (existing - unchanged)

  // ── Open / Close ───────────────────────────────────
  // (modified: closeModal calls cancelActivePoll)

  // ── Reload Button + Restore state ──────────────────
  // (existing - unchanged)
})();
```

### Step 2 Validation

1. Start the dummy server:
```bash
uv run demo/tools/dummy_api_server.py --vault-dir /tmp/test-vault --job-delay 2
```

2. Start the forge overlay pointing at the dummy server (or use the demo harness):
```bash
# From forge repo root
uv run demo/scripts/setup.py && uv run demo/scripts/start_stack.py
```

3. Open the overlay in browser, open dev tools Network tab.

4. **Test apply flow:**
   - Click Send
   - Verify: output shows `[queued] job:XXXXXXXX — polling for result...`
   - Verify: within ~3s, output changes to `[succeeded] job:XXXXXXXX (2.0s)` with summary
   - Verify: Network tab shows `POST /v1/jobs` (202) then multiple `GET /v1/jobs/{id}` calls
   - Verify: Logs section captures all `/v1/jobs` requests

5. **Test undo flow:**
   - Click Undo
   - Same lifecycle verification as above

6. **Test button disabling:**
   - Click Send
   - Immediately verify Send and Undo buttons are visually disabled and not clickable
   - After completion, verify buttons re-enable

7. **Test error handling:**
   - Set instruction to "FAIL this operation" and click Send
   - Verify: output shows `[failed]` with error message

8. **Test fetch intercept:**
   - Open Logs section in modal
   - Verify: both the POST /v1/jobs and GET /v1/jobs/* calls appear in logs
   - Verify: log entries show method, URL, status, duration

9. **Test modal close cancels polling:**
   - Set dummy server `--job-delay 10` (long delay)
   - Click Send
   - While showing "running", close the modal
   - Verify: no further network requests to /v1/jobs in Network tab

**All checks must pass before proceeding to Step 3.**

---

## Step 3: Add Queue Visual Styles in `ops.css`

**File:** `src/overlay/ops.css`

### 3.1 Add Job Status Chip Styles

Add the following after the existing `.forge-actions button` styles (after line 244):

```css
/* ── Job Status Indicators ───────────────────────── */
#forge-modal .forge-actions button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  border-color: #1e293b;
}

#forge-modal .forge-output[data-job-status="queued"] {
  border-color: #eab308;
}

#forge-modal .forge-output[data-job-status="running"] {
  border-color: #3b82f6;
}

#forge-modal .forge-output[data-job-status="succeeded"] {
  border-color: #10b981;
}

#forge-modal .forge-output[data-job-status="failed"] {
  border-color: #ef4444;
}
```

### 3.2 (Optional) Add Status Color to Output Text

If you want the output border to reflect job status, update the `renderJobStatus()` function in `ops.js` to also set a data attribute:

```javascript
  function renderJobStatus() {
    if (!activeJob) return;
    // Set data attribute for CSS styling
    outputEl.setAttribute("data-job-status", activeJob.status);
    // ... rest of existing renderJobStatus code
  }
```

And clear it in the button handlers before submitting:

```javascript
    outputEl.removeAttribute("data-job-status");
```

### Step 3 Validation

1. Open the overlay modal in browser.
2. Submit an apply job.
3. **Verify visual states:**
   - During `queued`: output box has yellow/amber border (`#eab308`)
   - During `running`: output box has blue border (`#3b82f6`)
   - On `succeeded`: output box has green border (`#10b981`)
   - On `failed`: output box has red border (`#ef4444`)
4. **Verify disabled state:**
   - While job is active, Send/Undo buttons appear visually dimmed (opacity 0.4)
   - Cursor shows `not-allowed` on hover

**All checks must pass before proceeding to Step 4.**

---

## Step 4: Update Overlay README

**File:** `src/overlay/README.md`

Replace the entire file with:

```markdown
# Production Overlay UI

This directory contains the production overlay assets injected by `forge-overlay`:

- `ops.js`
- `ops.css`

## Features

- Floating trigger button with unread API log badge.
- Modal UI for agent actions via async job queue (`/v1/jobs` submit + poll).
- Job lifecycle display: queued → running → succeeded/failed with elapsed time.
- Action button disabling during active job execution.
- Live API log capture via client-side `fetch` intercept for `/api/*` and `/v1/*`.
- Collapsible Global + This Page log groups.
- Per-request detail panels (request/response/error payloads).
- Model/token metadata badges when usage/model fields are present.
- SSE connection status (`/ops/events`).
- Reload button and modal-open persistence via `localStorage`.

## Request Flow

1. User clicks Send/Undo in overlay modal.
2. UI submits `POST /v1/jobs` with `{ operation, payload }`.
3. Agent returns `202 Accepted` with `job_id`.
4. UI polls `GET /v1/jobs/{job_id}` with exponential backoff (500ms → 1s → 2s → 3s cap).
5. On terminal status (`succeeded`/`failed`), UI renders result summary.
6. Buttons are disabled during active job; polling cancels on modal close.

## Error Handling

- **504 (upstream_timeout):** Proxy timed out reaching agent. Guidance shown to user.
- **502 (upstream_unavailable):** Agent unreachable. Guidance shown to user.
- **Job `failed` status:** Agent-reported error shown from `result.error` or top-level `error`.
- **Transient poll failures:** Tolerated up to 3 consecutive failures before declaring failure.

## Local Dev

`forge dev` auto-falls back to this directory when configured `overlay_dir`
does not contain `ops.js` + `ops.css`.

Recommended run:

```bash
devenv shell -- forge dev --config forge.yaml
```

For demo harness with production UI explicitly forced:

```bash
devenv shell -- uv run prod-demo
```

## Docker

Docker compose is wired to:

- `FORGE_OVERLAY_DIR=/app/src/overlay`

Validation includes explicit checks that production overlay assets are served:

```bash
uv run docker/validate.py
```
```

### Step 4 Validation

- Read the file and confirm it accurately describes the new job-based flow.
- Confirm no references to the old `/api/agent/apply` remain as the "primary" path.

---

## Step 5: Update Demo Runner

**File:** `demo/scripts/run_demo.py`

### 5.1 Add Job Helper Functions

Add these helper functions after the existing `http_put_json` function (after line 144):

```python
def submit_job(base_url: str, operation: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    """Submit a job via POST /v1/jobs and return the accepted response."""
    body: dict[str, object] = {"operation": operation}
    if payload is not None:
        body["payload"] = payload
    raw = http_post_json(f"{base_url}/v1/jobs", body)
    result = json.loads(raw.decode("utf-8")) if isinstance(raw, bytes) else raw
    if not result.get("job_id"):
        raise fail(f"job submit did not return job_id: {result}")
    return result


def poll_job(
    base_url: str,
    job_id: str,
    timeout_s: float = 130.0,
    backoff_base: float = 0.5,
    backoff_max: float = 3.0,
) -> dict[str, object]:
    """Poll GET /v1/jobs/{job_id} until terminal status with exponential backoff."""
    deadline = time.monotonic() + timeout_s
    interval = backoff_base

    while time.monotonic() < deadline:
        time.sleep(interval)
        try:
            raw = http_get(f"{base_url}/v1/jobs/{job_id}")
            result = json.loads(raw.decode("utf-8"))
        except Exception:
            interval = min(interval * 2, backoff_max)
            continue

        status = result.get("status", "")
        if status in ("succeeded", "failed"):
            return result

        interval = min(interval * 2, backoff_max)

    raise fail(f"job {job_id} did not reach terminal status within {timeout_s}s")
```

### 5.2 Replace Step 6 (Apply Through Overlay)

Replace the Step 6 block (starting at `step_header("6", "Run Deterministic Apply Through Overlay")`) with:

```python
    step_header("6", "Run Deterministic Apply Through Overlay (Job Queue)")
    api_base = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}"
    note_html = rendered_html_path("projects/forge-v2.md")
    apply_token = f"WALKTHROUGH_APPLY_{int(time.time())}"
    baseline_marker_count = count_substring(note_html, apply_token)
    apply_via = "job"
    fallback_original_content: str | None = None

    try:
        accepted = submit_job(
            api_base,
            "apply",
            {"instruction": f"Append exactly this line at end of file: {apply_token}", "current_file": "projects/forge-v2.md"},
        )
        log(f"Job submitted: {accepted['job_id']} (status: {accepted['status']})")
        final = poll_job(api_base, accepted["job_id"])
        log(f"Job completed: status={final['status']}")
        if final["status"] != "succeeded":
            raise RuntimeError(f"apply job failed: {final.get('error', final)}")
        apply_payload = final.get("result", final)
    except (urlerror.HTTPError, RuntimeError) as exc:
        log(f"Job queue apply failed ({exc}), falling back to vault route")
        apply_via = "vault"
        vault_api = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api"
        fallback_original_content = str(
            json.loads(http_get(f"{vault_api}/vault/files?path={urlparse.quote('projects/forge-v2.md')}").decode("utf-8")).get(
                "content", ""
            )
        )
        apply_payload = vault_append_token(vault_api, "projects/forge-v2.md", apply_token)

    print("Apply response:")
    print(json.dumps(apply_payload, indent=2, sort_keys=True))
    if not apply_payload.get("ok"):
        raise fail(f"apply request failed: {apply_payload}")
    if apply_via == "vault":
        print("Agent job queue unavailable; used deterministic vault-route fallback.")

    print("Waiting for rendered apply update...")
    if not wait_until(
        lambda: note_html.exists() and count_substring(note_html, apply_token) > baseline_marker_count,
        timeout_s=45,
    ):
        raise fail("apply marker not observed in rendered note")

    print(f"Apply completed. Refresh /projects/forge-v2 to see token: {apply_token}")
    pause_step("After confirming apply output in browser, press any key...")
```

### 5.3 Replace Step 7 (Undo Through Overlay)

Replace the Step 7 block with:

```python
    step_header("7", "Run Undo Through Overlay (Job Queue)")
    if apply_via == "job":
        accepted = submit_job(api_base, "undo")
        log(f"Undo job submitted: {accepted['job_id']} (status: {accepted['status']})")
        final = poll_job(api_base, accepted["job_id"])
        log(f"Undo job completed: status={final['status']}")
        undo_payload = final.get("result", final)
    else:
        vault_api = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}/api"
        undo_payload = vault_restore_content(vault_api, "projects/forge-v2.md", fallback_original_content or "")

    print("Undo response:")
    print(json.dumps(undo_payload, indent=2, sort_keys=True))
    if not undo_payload.get("ok"):
        raise fail(f"undo request failed: {undo_payload}")

    print("Waiting for rendered undo update...")
    if not wait_until(
        lambda: note_html.exists() and count_substring(note_html, apply_token) == baseline_marker_count,
        timeout_s=45,
    ):
        raise fail("undo marker removal not observed in rendered note")

    print("Undo completed. Refresh /projects/forge-v2 to confirm marker removal.")
    pause_step("After confirming undo output in browser, press any key...")
```

### Step 5 Validation

```bash
# Run the demo in auto-advance mode
AUTO_ADVANCE=1 uv run demo/scripts/run_demo.py

# Expected:
# - Step 6 shows "Job submitted: <id>" and "Job completed: status=succeeded"
# - Step 7 shows "Undo job submitted: <id>" and "Undo job completed: status=succeeded"
# - Apply token appears in rendered HTML, then disappears after undo
# - Script exits 0
```

If the real agent is not available, the script should fall back to the vault route and still pass.

**All checks must pass before proceeding to Step 6.**

---

## Step 6: Update Full-Stack Validator

**File:** `demo/scripts/validate_full_stack.py`

### 6.1 Add Job Helper Functions

Add these after the existing `http_put_json` function:

```python
def submit_job(base_url: str, operation: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    """Submit a job via POST /v1/jobs."""
    body: dict[str, object] = {"operation": operation}
    if payload is not None:
        body["payload"] = payload
    return http_post_json(f"{base_url}/v1/jobs", body)


def poll_job(base_url: str, job_id: str, timeout_s: float = 130.0) -> dict[str, object]:
    """Poll job until terminal with exponential backoff."""
    interval = 0.5
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(interval)
        try:
            result = http_get_json(f"{base_url}/v1/jobs/{job_id}")
        except Exception:
            interval = min(interval * 2, 3.0)
            continue
        if result.get("status") in ("succeeded", "failed"):
            return result
        interval = min(interval * 2, 3.0)
    raise fail(f"job {job_id} timed out after {timeout_s}s")
```

### 6.2 Replace the Apply/Undo Section in `main()`

Replace the apply/undo section (lines 168-203 in current file) with:

```python
        # ── Job Queue Apply/Undo ──────────────────────────
        apply_token = f"VALIDATION_APPLY_{int(time.time())}"
        apply_via = "job"
        fallback_original_content: str | None = None
        v1_base = f"http://{DEMO_OVERLAY_HOST}:{DEMO_OVERLAY_PORT}"

        try:
            accepted = submit_job(v1_base, "apply", {
                "instruction": f"Append exactly this line at end of file: {apply_token}",
                "current_file": "projects/forge-v2.md",
            })
            if not accepted.get("job_id"):
                raise RuntimeError(f"no job_id in response: {accepted}")
            log(f"apply job submitted: {accepted['job_id']}")

            final = poll_job(v1_base, accepted["job_id"])
            if final.get("status") != "succeeded":
                raise RuntimeError(f"apply job failed: {final.get('error', final)}")
            log(f"apply job succeeded: {final.get('result', {}).get('summary', '')}")
        except (urlerror.HTTPError, RuntimeError) as exc:
            log(f"job queue apply failed ({exc}), using vault fallback")
            apply_via = "vault"
            fallback_original_content = str(
                http_get_json(f"{api_base}/vault/files?path={urlparse.quote('projects/forge-v2.md')}").get("content", "")
            )
            apply_payload = _vault_append_token(api_base, "projects/forge-v2.md", apply_token)
            if not apply_payload.get("ok", False):
                raise fail(f"vault fallback apply failed: {apply_payload}")

        forge_note_html = rendered_html_path("projects/forge-v2.md")
        if not wait_until(lambda: apply_token in read_text(forge_note_html), timeout_s=90):
            raise fail("apply token not observed in rendered note")

        if apply_via == "job":
            undo_accepted = submit_job(v1_base, "undo")
            log(f"undo job submitted: {undo_accepted['job_id']}")
            undo_final = poll_job(v1_base, undo_accepted["job_id"])
            if undo_final.get("status") != "succeeded":
                raise fail(f"undo job failed: {undo_final.get('error', undo_final)}")
            log("undo job succeeded")
        else:
            undo_payload = _vault_restore_content(api_base, "projects/forge-v2.md", fallback_original_content or "")
            if not undo_payload.get("ok", False):
                raise fail(f"undo request failed: {undo_payload}")

        if not wait_until(lambda: apply_token not in read_text(forge_note_html), timeout_s=90):
            raise fail("undo did not remove apply token from rendered note")
```

### Step 6 Validation

```bash
# Run the full-stack validator
uv run demo/scripts/validate_full_stack.py

# Expected output includes:
# [validate] apply job submitted: <uuid>
# [validate] apply job succeeded: <summary>
# [validate] undo job submitted: <uuid>
# [validate] undo job succeeded
# [validate] full-stack demo harness validation passed
# Exit code: 0
```

**All checks must pass before proceeding to Step 7.**

---

## Step 7: Extend Docker Validator

**File:** `docker/validate.py`

### 7.1 Add Job Helper Functions

Add these after the existing `http_put_json` function:

```python
def submit_job(base_url: str, operation: str, payload: dict[str, object] | None = None, timeout: float = 30.0) -> dict[str, object]:
    """Submit a job via POST /v1/jobs."""
    body: dict[str, object] = {"operation": operation}
    if payload is not None:
        body["payload"] = payload
    return http_post_json(f"{base_url}/v1/jobs", body, timeout=timeout)


def poll_job(base_url: str, job_id: str, timeout_s: float = 130.0) -> dict[str, object]:
    """Poll job until terminal with exponential backoff."""
    interval = 0.5
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(interval)
        try:
            result = http_get_json(f"{base_url}/v1/jobs/{job_id}", timeout=10.0)
        except Exception:
            interval = min(interval * 2, 3.0)
            continue
        if result.get("status") in ("succeeded", "failed"):
            return result
        interval = min(interval * 2, 3.0)
    raise RuntimeError(f"job {job_id} timed out after {timeout_s}s")
```

### 7.2 Add Queue Validation Section

Add this after the existing "write -> rebuild -> undo flow" section (after the undo check around line 182), before the final success print:

```python
        print("[docker-validate] testing job queue apply -> poll -> undo flow...")
        job_path = "docker-job-validation.md"
        job_token = f"docker-job-token-{int(time.time())}"

        # Submit apply job
        accepted = submit_job(base, "apply", {
            "instruction": f"Create a new file with this content: # Job Test\n\n{job_token}",
            "current_file": job_path,
        })
        if not accepted.get("job_id"):
            raise RuntimeError(f"job submit failed: {accepted}")
        print(f"[docker-validate] apply job submitted: {accepted['job_id']}")

        # Poll to terminal
        final = poll_job(base, accepted["job_id"])
        if final.get("status") != "succeeded":
            raise RuntimeError(f"apply job did not succeed: {final}")
        print(f"[docker-validate] apply job succeeded")

        # Verify content rendered
        job_candidate_urls = [
            f"{base}/docker-job-validation",
            f"{base}/docker-job-validation/",
            f"{base}/docker-job-validation.html",
        ]
        ensure_contains_any(job_candidate_urls, job_token, timeout_s=120.0)
        print("[docker-validate] job apply token visible in rendered page")

        # Submit undo job
        undo_accepted = submit_job(base, "undo")
        print(f"[docker-validate] undo job submitted: {undo_accepted['job_id']}")
        undo_final = poll_job(base, undo_accepted["job_id"])
        if undo_final.get("status") != "succeeded":
            raise RuntimeError(f"undo job did not succeed: {undo_final}")
        print("[docker-validate] undo job succeeded")

        # Verify content removed
        def _job_token_gone() -> bool:
            for url in job_candidate_urls:
                try:
                    if job_token in http_get_text(url, timeout=5.0):
                        return False
                except Exception:
                    continue
            return True

        if not wait_until(_job_token_gone, timeout_s=120.0, interval_s=1.0):
            raise RuntimeError("job undo did not remove token from rendered content")
        print("[docker-validate] job undo verified — token removed")
```

### Step 7 Validation

```bash
# Run Docker validation (requires Docker running)
uv run docker/validate.py

# Expected output includes:
# [docker-validate] testing job queue apply -> poll -> undo flow...
# [docker-validate] apply job submitted: <uuid>
# [docker-validate] apply job succeeded
# [docker-validate] job apply token visible in rendered page
# [docker-validate] undo job submitted: <uuid>
# [docker-validate] undo job succeeded
# [docker-validate] job undo verified — token removed
# [docker-validate] docker validation passed
# Exit code: 0
```

**All checks must pass before proceeding to Step 8.**

---

## Step 8: Update Demo Documentation

### 8.1 Update `demo/README.md`

Find any references to `/api/agent/apply` or `/api/undo` and replace with the job queue description. Add a section explaining the new flow:

```markdown
### Job Queue Flow

The demo exercises the async job queue for apply/undo operations:

1. `POST /v1/jobs` with `{"operation": "apply", "payload": {...}}` → 202 Accepted
2. Poll `GET /v1/jobs/{job_id}` with exponential backoff until `succeeded` or `failed`
3. `POST /v1/jobs` with `{"operation": "undo"}` → 202 Accepted
4. Poll until terminal

The overlay UI shows job lifecycle (queued → running → succeeded/failed) with elapsed time.
```

### 8.2 Update `demo/DEMO_SCRIPT.md`

Update Step 6 and Step 7 talk track:

**Step 6** should reference:
- "Submit an apply job through the job queue"
- Expected operator action: "Run `POST /v1/jobs` with apply payload"
- Expected outcome: "Job transitions queued → running → succeeded, rendered content updates"

**Step 7** should reference:
- "Submit an undo job through the job queue"
- Expected operator action: "Run `POST /v1/jobs` with undo operation"
- Expected outcome: "Job succeeds, rendered content reverts"

### Step 8 Validation

- Read both files and confirm no remaining references to `/api/agent/apply` or `/api/undo` as the primary apply/undo mechanism.
- Confirm the job queue model is clearly explained for a new reader.

---

## Step 9: Final Validation Pass

Run the complete validation suite to confirm no regressions.

### 9.1 Unit-Level: Dummy Server

```bash
# Quick smoke test of job endpoints
uv run demo/tools/dummy_api_server.py --vault-dir /tmp/test-vault --job-delay 1 &
SERVER_PID=$!

mkdir -p /tmp/test-vault/projects
echo "# Test" > /tmp/test-vault/projects/forge-v2.md

# Submit + poll apply
RESULT=$(curl -s -X POST http://127.0.0.1:18081/v1/jobs \
  -H "content-type: application/json" \
  -d '{"operation":"apply","payload":{"instruction":"test","current_file":"projects/forge-v2.md"}}')
JOB_ID=$(echo $RESULT | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
sleep 2
STATUS=$(curl -s http://127.0.0.1:18081/v1/jobs/$JOB_ID | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
[ "$STATUS" = "succeeded" ] && echo "PASS: apply job" || echo "FAIL: apply job (got $STATUS)"

# Submit + poll undo
RESULT=$(curl -s -X POST http://127.0.0.1:18081/v1/jobs \
  -H "content-type: application/json" \
  -d '{"operation":"undo"}')
JOB_ID=$(echo $RESULT | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
sleep 2
STATUS=$(curl -s http://127.0.0.1:18081/v1/jobs/$JOB_ID | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
[ "$STATUS" = "succeeded" ] && echo "PASS: undo job" || echo "FAIL: undo job (got $STATUS)"

# List jobs
COUNT=$(curl -s "http://127.0.0.1:18081/v1/jobs?limit=10" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['jobs']))")
[ "$COUNT" -ge 2 ] && echo "PASS: job listing" || echo "FAIL: job listing (got $COUNT)"

kill $SERVER_PID
```

### 9.2 Demo Harness Validation

```bash
AUTO_ADVANCE=1 uv run demo/scripts/run_demo.py
echo "Exit code: $?"
# Must exit 0
```

### 9.3 Full-Stack Validation

```bash
uv run demo/scripts/validate_full_stack.py
echo "Exit code: $?"
# Must exit 0
```

### 9.4 Docker Validation

```bash
uv run docker/validate.py
echo "Exit code: $?"
# Must exit 0
```

### 9.5 Manual Browser Validation Checklist

- [ ] Open overlay modal, submit apply, observe status line: `[queued]` → `[running]` → `[succeeded]`
- [ ] Verify `job_id` (first 8 chars) and elapsed time displayed
- [ ] Verify output border color changes with status (yellow → blue → green)
- [ ] Verify logs section shows `POST /v1/jobs` and `GET /v1/jobs/*` entries
- [ ] Verify Send/Undo buttons are disabled during active job
- [ ] Submit undo, observe success and content rollback
- [ ] Set instruction to "FAIL test" and submit — verify `[failed]` status with error
- [ ] Close modal during active job — verify no continued polling in Network tab

### 9.6 Regression Checks

- [ ] Existing `/api/health` button still works (proxied through overlay)
- [ ] Log persistence across page reload still works
- [ ] SSE connection indicator still displays correctly
- [ ] File path detection still works on navigation
- [ ] Modal open/close state persists via localStorage

---

## Common Pitfalls

1. **Forgetting to handle the 202 status code.** The `submitJob` helper must accept both 200 and 202 as success — the agent returns 202.

2. **Not aborting polls on modal close.** Without AbortController cleanup, closed modals generate invisible network traffic and potential errors.

3. **Assuming intermediate states are always visible.** Fast jobs may go `queued → succeeded` in one poll cycle. Never assert that `running` was observed.

4. **Using the wrong base URL for `/v1/jobs`.** The path is at the root of the overlay server, not under `/api/`. Correct: `/v1/jobs`. Incorrect: `/api/v1/jobs`.

5. **Not handling `payload: null` for undo.** The agent requires `payload` to be absent or null for undo operations. Sending `payload: {}` will cause a validation error.

6. **Race condition in dummy server.** The `_advance_job` method performs the actual apply/undo operation on state transition. Make sure the lock is held properly and the vault file exists before the job advances.

---

## Definition of Done

Refactor is complete when:
- [ ] Forge UI uses `/v1/jobs` submit+poll for apply/undo
- [ ] Polling uses exponential backoff (500ms → 1s → 2s → 3s cap) with 130s hard timeout
- [ ] Queue status is visible during operation lifecycle (status line + colored border)
- [ ] Buttons disabled during active job
- [ ] Fetch intercept logs `/v1/*` in addition to `/api/*`
- [ ] Dummy API server supports `/v1/jobs*` for local dev
- [ ] Demo runner (`run_demo.py`) exercises job queue flow
- [ ] Full-stack validator (`validate_full_stack.py`) passes with job queue
- [ ] Docker validator (`docker/validate.py`) passes with job queue checks
- [ ] All documentation updated to describe job-based flow
- [ ] No references remain that assume synchronous `/api/agent/apply` as primary path
