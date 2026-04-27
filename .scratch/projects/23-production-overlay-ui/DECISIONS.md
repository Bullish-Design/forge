# Decisions — Production Overlay UI

This file tracks key decisions made during the project, with rationale and which assumptions informed each decision.

## Decision Format
- **Title**: Brief description of the choice
- **Options considered**: A, B, C with trade-offs
- **Decision**: Which option was chosen
- **Rationale**: Why this option was chosen
- **Informed by**: Which assumptions shaped this decision
- **Date**: When the decision was made
- **Status**: pending/final

---

## Decision 1: Log Capture Strategy

### Title
Client-side fetch intercept for LLM log capture

### Options Considered
- **A**: Client-side fetch intercept (no backend changes, real-time, limited metadata)
- **B**: Backend response injection (requires obsidian-agent v0.4+, complete metadata, blocks on release)
- **C**: Status polling (requires new endpoint, ~1s latency, clean but complex)

### Decision
**Option A: Fetch Intercept**

### Rationale
- Unblocks immediate implementation (no backend dependencies)
- Captures complete request/response payloads for debugging
- Can gracefully upgrade if obsidian-agent later exposes metadata
- Non-intrusive (forge and demo overlay untouched)
- Ephemeral logging is good for privacy/security

### Trade-offs Accepted
- Won't have exact token counts without parsing
  - Workaround: Parse response for `usage` field if present, OR estimate from text length
- Won't have system prompt visible
  - Workaround: Show generic template or hardcode common prompts
- No intermediate LLM call steps (just final request/response)
  - This is acceptable for debugging main agent operations

### Migration Path
If obsidian-agent v0.4+ later adds:
- Response `_forge_logs` field → upgrade to Option B (better metadata)
- `/api/agent/status` endpoint → can optionally switch to Option C

### Informed By
- ASSUMPTIONS.md: Tech stack assumptions, production deployment requirements
- PLAN.md: Phase 2.5 log capture task

### Date
2026-04-27

### Status
Final

