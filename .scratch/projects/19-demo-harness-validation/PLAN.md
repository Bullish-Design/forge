# Plan

## Goal
Validate the full v2 stack behavior via a repeatable demo harness, using a local dummy LLM API to avoid external dependencies.

## Execution Order
1. Define runtime layout and deterministic seed data
2. Implement `setup.sh` and `cleanup.sh`
3. Implement dummy API server with deterministic apply/undo behavior
4. Implement stack startup harness (`dummy-api` -> `forge-overlay` -> `kiln dev --no-serve --on-rebuild`)
5. Implement full validation script to assert:
   - site render + overlay injection
   - kiln incremental rebuild behavior
   - webhook -> overlay path health
   - SSE rebuilt event delivery
   - `/api/*` proxy to dummy API
   - apply/undo mutation cycle with real rebuild output changes
6. Wire validation command into repo docs and optional pytest integration
7. Run and record real validation evidence

## Success Criteria
- One command performs full-stack validation and exits non-zero on any regression
- Setup/cleanup always restore a known-good baseline
- No external LLM provider credentials required
- Validation exercises real subprocesses and localhost HTTP behavior
