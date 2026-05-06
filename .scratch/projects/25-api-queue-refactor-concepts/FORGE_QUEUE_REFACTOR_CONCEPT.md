# FORGE_QUEUE_REFACTOR_CONCEPT

## Purpose
Define what this `forge` repo should change to support durable, user-visible queued API interactions without making `forge` the source of truth for mutation ordering.

## Responsibility Boundary
- `forge` owns orchestration and demo UX wiring.
- `forge` should **not** become the authoritative mutation queue.
- Authoritative queueing/serialization belongs in `obsidian-agent`.

## What Needs To Change
1. Overlay UI request model in `src/overlay/ops.js`
- Replace direct "fire-and-forget" apply calls with job-based submission semantics.
- Keep a UI-level queue view for operator clarity (queued/running/done/failed).
- Persist local queue display state across reloads (localStorage/session), but treat it as presentation state only.

2. API interaction flow
- Submit work to async agent endpoint (via overlay proxy), receive `job_id`.
- Poll or stream job status updates and render state transitions in UI.
- Add explicit handling for interrupted navigation/reload so jobs can be rehydrated by `job_id`.

3. UX safeguards
- Disable conflicting actions while a job is running when applicable.
- Expose retry for failed jobs and clear/cleanup controls for stale local entries.
- Distinguish transport failures from job execution failures in output/logs.

4. Demo harness updates
- Update demo walkthrough/validation scripts to validate queue behavior:
  - multiple queued submissions
  - status progression
  - reload recovery
  - deterministic completion ordering assumptions

## Non-Goals
- Implementing persistent cross-client locking in forge UI.
- Owning queue arbitration in browser code.

## Integration Points
- Depends on `forge-overlay` proxy support for new job/status routes.
- Depends on `obsidian-agent` queue/job lifecycle APIs.
