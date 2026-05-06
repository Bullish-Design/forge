# OBSIDIAN_AGENT_QUEUE_REFACTOR_CONCEPT

## Purpose
Define the core queue refactor needed in `obsidian-agent` so mutation operations are serialized, durable, and inspectable.

## Responsibility Boundary
- `obsidian-agent` is the system of record for operation ordering, locking, and job outcomes.
- Agent must provide stable job lifecycle APIs for clients.

## What Needs To Change
1. Authoritative job model
- Introduce job entity with fields like:
  - `job_id`, `type`, `created_at`, `started_at`, `finished_at`
  - `status` (`queued`, `running`, `succeeded`, `failed`, `canceled`)
  - request payload metadata (`current_file`, instruction hash/preview)
  - result summary and structured errors

2. Execution queue
- Single-writer mutation queue for apply/undo-like operations (or explicit concurrency classes).
- Deterministic processing order with clear idempotency/retry policy.
- Concurrency guard centralization (replace ad-hoc "another operation is running" behavior).

3. API contract
- Add async-first endpoints, e.g.:
  - submit job -> returns `job_id`
  - fetch job status/result
  - list recent jobs
  - optional cancel endpoint
- Keep compatibility layer or transitional behavior for existing synchronous clients.

4. Persistence and recovery
- Decide persistence scope:
  - in-memory (minimal), or
  - durable local store (recommended for reload/restart resilience).
- On process restart, recover or mark orphaned/running jobs consistently.

5. VCS + side effects integration
- Ensure queue lifecycle captures commit/sync outcomes without losing primary content mutation status.
- Separate mutation success from post-mutation warnings (e.g., commit/sync failures).

6. Telemetry and diagnostics
- Structured logs keyed by `job_id`.
- Explicit error categories (LLM failure, tool failure, VCS failure, timeout, validation).

## Non-Goals
- UI-specific rendering concerns.
- Overlay-specific transport behavior.

## Integration Points
- `forge-overlay` proxies these endpoints.
- `forge` UI/demo consumes job APIs for queue display and interaction.
