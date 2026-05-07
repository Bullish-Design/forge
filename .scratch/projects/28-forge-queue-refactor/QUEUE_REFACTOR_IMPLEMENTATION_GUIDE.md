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

## Target Request Model

### Old model (current Forge UI)
- `POST /api/agent/apply` and wait for immediate final `OperationResult`
- `POST /api/undo`/`/api/agent/undo` and wait for immediate final result

### New model (required)
1. Submit job:
- `POST /v1/jobs`
- body (apply):
  ```json
  {
    "operation": "apply",
    "payload": {
      "instruction": "...",
      "current_file": "...",
      "interface_id": "...",
      "scope": "...",
      "intent": "...",
      "allowed_write_scope": "target_only"
    }
  }
  ```
  (Only `instruction` is required in payload; other fields are optional pass-through.)
- body (undo):
  ```json
  { "operation": "undo" }
  ```

2. Receive accepted response:
- `202` with `{ "job_id": "...", "status": "queued", "created_at": "..." }`

3. Poll job status:
- `GET /v1/jobs/{job_id}` until terminal status:
  - `succeeded`
  - `failed`

4. Optional list/history:
- `GET /v1/jobs?limit=...`

## Actual Agent API Contracts (Reference)

These are the models implemented in `obsidian-agent` — the UI must conform to them.

**JobSubmitRequest:**
```
operation: "apply" | "undo"
payload: ApplyRequest | null   // required for "apply", null for "undo"
```

**ApplyRequest (payload for apply):**
```
instruction: str | null
current_file: str | null
interface_id: str | null
scope: EditScope | null
intent: "rewrite" | "summarize" | "insert_below" | "annotate" | "extract_tasks" | null
allowed_write_scope: "target_only" | "target_plus_frontmatter" | "unrestricted"  (default: "target_only")
```

**JobAcceptedResponse (202):**
```
job_id: str
status: "queued"
created_at: datetime
```

**JobResponse (GET /v1/jobs/{id}):**
```
id: str
operation: "apply" | "undo"
status: "queued" | "running" | "succeeded" | "failed"
created_at: datetime
started_at: datetime | null
finished_at: datetime | null
request: dict
result: OperationResult | null
error: str | null
```

**OperationResult (nested in result):**
```
ok: bool
updated: bool
summary: str
changed_files: list[str]
error: str | null
warning: str | null
```

**JobListResponse (GET /v1/jobs):**
```
jobs: list[JobResponse]
```

## Overlay Proxy Error Contracts (Reference)

The forge-overlay proxy maps transport failures as follows:
- `httpx.TimeoutException` → HTTP 504, body `{"error": "upstream_timeout"}`
- `httpx.HTTPError` (other) → HTTP 502, body `{"error": "upstream_unavailable"}`
- All other upstream responses (including 4xx/5xx) pass through unchanged.

Proxy timeout is configurable (default 600s); agent operation timeout is 120s.

## Files To Change

### 1) `demo/tools/dummy_api_server.py` (first — enables UI development)
Add `/v1/jobs*` stubs for deterministic local development and testing.

Required endpoints:
- `POST /v1/jobs` — accepts JobSubmitRequest, returns 202 with job_id
- `GET /v1/jobs/{job_id}` — returns JobResponse with simulated state transitions
- `GET /v1/jobs` — returns JobListResponse

Behavior:
- In-memory job store with configurable completion delay (e.g., 2s default).
- Deterministic state machine: `queued` (0-500ms) → `running` (delay) → `succeeded`.
- Support a `?fail=true` query param or special instruction to trigger `failed` state for testing.
- Return `OperationResult` with mock data on success.

### 2) `src/overlay/ops.js` (primary implementation)
This is the critical refactor file.

Required changes:
- Replace direct apply/undo calls with submit+poll workflow.
- Add job state tracking (in-memory for phase 1).
- Expand API logging interception to include `/v1/*`.
- Add robust error handling for proxy/transport failures.

Implementation plan:

1. Add constants/config:
- `JOB_POLL_INITIAL_MS = 500`
- `JOB_POLL_MAX_MS = 3000`
- `JOB_POLL_BACKOFF = 2` (multiplier)
- `JOB_POLL_TIMEOUT_MS = 130000` (slightly above agent's 120s operation timeout)

2. Add helpers:
- `submitJob(operation, payload?) -> JobAcceptedResponse`
  - Single helper for both apply and undo; pass-through all payload fields.
- `fetchJob(jobId) -> JobResponse`
- `pollJobUntilTerminal(jobId, options?) -> JobResponse`
- `isTerminalStatus(status) -> bool`

3. Add in-memory job tracker (phase 1):
- Track the current active job: `{ id, operation, status, created_at, started_at, finished_at, result, error }`
- No localStorage persistence in phase 1 — keep it simple.
- If a job is active, disable conflicting actions.

4. Wire send button:
- on click:
  - submit apply job via `submitJob("apply", { instruction, current_file })`
  - render immediate accepted state (show job_id, status: queued)
  - poll until terminal with exponential backoff
  - render final `result` or `error`
- disable send/undo globally while any job is active

5. Wire undo button:
- same submit+poll pattern via `submitJob("undo")`

6. Expand fetch intercept routing filter:
- currently logs only URLs containing `/api/`
- update to log both `/api/` and `/v1/`

7. Update error mapping in output messaging:
- Transport errors (from proxy):
  - `{"error": "upstream_timeout"}` (504) → show timeout-specific guidance
  - `{"error": "upstream_unavailable"}` (502) → show reachability guidance
- Job-level errors (from terminal poll):
  - `status == "failed"` → show `result.error` if present, else top-level `error`
- Transient poll failures:
  - Tolerate up to 3 consecutive fetch errors before declaring failure
  - On transient error, continue polling (do not reset backoff)

8. Job status rendering UX:
- Show concise lifecycle status line:
  - `queued` → `running` → `succeeded|failed`
- Include elapsed time and job_id
- Include final result summary / warning / changed_files
- Tolerate direct `queued → succeeded` (fast jobs) without error

### 3) `src/overlay/ops.css`
Add styles for queue/job elements:
- Job status chip classes (`queued`, `running`, `succeeded`, `failed`)
- Disabled-action state clarity while job active
- Elapsed time / job-id display

### 4) `src/overlay/README.md`
Update feature documentation:
- Replace "modal actions call `/api/agent/apply`" with job flow
- Document `/v1/jobs` submit/poll model
- Explain log capture now includes `/api/*` and `/v1/*`

### 5) `demo/scripts/run_demo.py`
Current script validates immediate apply/undo endpoints.

Required updates:
- Exercise queue model through overlay:
  - `POST /v1/jobs` apply
  - poll `GET /v1/jobs/{id}` to terminal
  - verify output mutation occurred
  - submit undo job and verify revert
- Keep health checks and existing demo setup behavior.

Add helper functions:
- `submit_job(base_url, operation, payload=None)`
- `poll_job(base_url, job_id, timeout_s=120, backoff_base=0.5, backoff_max=3.0)`

### 6) `demo/scripts/validate_full_stack.py`
Update integration assertions from direct apply result to job lifecycle verification.

Minimum assertions:
- apply job accepted (`202` + `job_id`)
- terminal `succeeded` and expected content mutation
- undo job terminal `succeeded`
- tolerate instant completion (no intermediate state required in assertions)

### 7) `docker/validate.py`
Extend Docker validation to queue endpoints.

Add checks:
- `POST /v1/jobs` apply returns `job_id`
- `GET /v1/jobs/{job_id}` reaches terminal
- verify resulting content in rendered page
- submit undo job and confirm content removed
- existing overlay asset checks remain

### 8) `demo/README.md` and `demo/DEMO_SCRIPT.md`
Update narrative and examples:
- Replace synchronous endpoint references with queue model
- Add operator explanation for `queued/running/succeeded/failed`

### 9) Any tests referencing legacy-only flow
Search/update tests in `tests/` and demo tests to align expected network calls.

## Polling Strategy

Use exponential backoff:
- Initial interval: `500ms`
- Backoff multiplier: `2x`
- Maximum interval: `3000ms`
- Hard timeout: `130s` (10s headroom above agent's 120s operation timeout)

Sequence: 500ms → 1000ms → 2000ms → 3000ms → 3000ms → ...

Polling loop behavior:
- Stop on terminal status (`succeeded` or `failed`)
- If timeout exceeded:
  - Show timeout message with job_id for manual follow-up
  - Do not retry — let user decide
- Tolerate transient fetch errors (network blips):
  - Allow up to 3 consecutive failures before declaring poll failure
  - On transient error, maintain current backoff interval and retry
- Clean up polling on modal close / page unload (AbortController)

## UI/UX Requirements

Minimum expected behavior:
- User sees immediate acknowledgement with `job_id`.
- User sees active status while work is in progress.
- Conflicting action buttons are disabled during active mutation.
- Logs include both submit and poll requests.

## Phased Delivery

### Phase 1 (this refactor)
- Job-only flow via `/v1/jobs` — no backward compatibility fallback.
- In-memory job tracking only (no localStorage persistence).
- Exponential backoff polling.
- Full error mapping for transport and job failures.
- Dummy server, demo scripts, and docker validation updated.

### Phase 2 (future, if needed)
- localStorage persistence for reload resilience.
- Resume polling of in-flight jobs on page load.
- Job history panel showing recent jobs from `GET /v1/jobs?limit=N`.

## Validation Plan

### Unit/Component-Level
- `ops.js` helper behavior:
  - submit payload correctness (all ApplyRequest fields passed through)
  - terminal-status detection
  - exponential backoff timing
  - transient error tolerance

### Demo Validation
- `run_demo.py` and `validate_full_stack.py` pass using `/v1/jobs` flow against dummy server and real agent.

### Docker Validation
- `uv run docker/validate.py` passes with queue checks added.

### Manual Validation Checklist
- [ ] Open overlay modal, submit apply, observe queued/running/succeeded.
- [ ] Observe `job_id` displayed and logs containing `/v1/jobs` calls.
- [ ] Submit undo, observe success and content rollback.
- [ ] Trigger proxy timeout scenario and verify user-facing timeout message.
- [ ] Trigger upstream down scenario and verify unavailable message.
- [ ] Verify buttons disabled during active job.

## Detailed Task Breakdown (Execution Order)

1. Add `/v1/jobs*` stubs to `demo/tools/dummy_api_server.py`.
2. Refactor `src/overlay/ops.js` for submit+poll flow (develop against dummy server).
3. Add queue-related visual styles in `src/overlay/ops.css`.
4. Update overlay docs in `src/overlay/README.md`.
5. Update demo runner `demo/scripts/run_demo.py`.
6. Update demo validator `demo/scripts/validate_full_stack.py`.
7. Extend Docker validator `docker/validate.py`.
8. Update demo docs (`demo/README.md`, `demo/DEMO_SCRIPT.md`).
9. Run tests + demo + docker validation and fix regressions.

## Risks and Mitigations

1. Risk: fast-completing jobs skip visible `running` state.
- Mitigation: UI tolerates direct `queued → succeeded` and still renders success. No assertion on intermediate states.

2. Risk: polling spam or stuck loops.
- Mitigation: exponential backoff (caps at 3s) + hard timeout (130s) + AbortController cleanup on modal close/unload.

3. Risk: inconsistent endpoint usage across scripts.
- Mitigation: centralize demo helper methods for submit/poll and reuse everywhere.

4. Risk: confusion between transport failure and job failure.
- Mitigation: separate messaging — proxy errors (504/502) show connectivity guidance; job `failed` shows operation-specific error from agent.

5. Risk: agent not updated (returns 404 on `/v1/jobs`).
- Mitigation: hard requirement — agent must be updated. No fallback code. Document minimum agent version in README.

## Definition of Done

Refactor is complete when:
- Forge UI uses `/v1/jobs` submit+poll for apply/undo.
- Polling uses exponential backoff with hard timeout.
- Queue status is visible during operation lifecycle.
- Demo and docker validators verify queue workflow end-to-end.
- Dummy API server supports `/v1/jobs*` for local development.
- Docs consistently describe job-based flow.
- No references remain that assume synchronous `/api/agent/apply` as primary path.
