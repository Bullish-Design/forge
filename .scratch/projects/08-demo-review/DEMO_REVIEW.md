# DEMO_REVIEW

## Summary

The current Forge demo is not aligned with the post-refactor architecture and is currently broken in default usage. The highest-priority fixes are to rewire demo startup for the two-process model and refresh docs so users can successfully run and validate the demo.

## Findings

### 1) Critical: `devenv shell -- demo` fails immediately

Evidence:
- command: `devenv shell -- demo`
- observed error: `unknown flag: --ops-llm-base-url`

Cause:
- `demo/run_demo.sh` still passes removed Forge flags:
  - `--ops-llm-base-url`
  - `--ops-llm-model`
  - `--ops-api-key`

Impact:
- Primary demo path is unusable.

### 2) High: Demo workflow still assumes old single-process behavior

Evidence:
- `demo/README.md` says demo command runs Forge with default OpenAI-compatible ops backend behavior.
- Current architecture requires external backend process (`obsidian-agent`) and Forge proxying.

Impact:
- New users follow outdated instructions and hit failures or unclear 5xx behavior.

### 3) High: No preflight checks for backend reachability

Evidence:
- no explicit check that `http://127.0.0.1:8081/api/health` is up before launching demo UX.

Impact:
- Users can reach UI but all overlay operations fail without obvious setup guidance.

### 4) Medium: Demo reset/setup doesn’t validate JJ/runtime expectations

Evidence:
- `demo-clean` resets runtime vault but does not verify JJ health or expected workspace state.

Impact:
- Undo/commit demos can fail with environment-dependent errors.

### 5) Medium: Demo script lacks structured “what to demonstrate” sequence

Evidence:
- current docs explain startup only; no guided progression for proving core capabilities.

Impact:
- inconsistent demos, weak confidence signal for stakeholders.

## Recommended Improvements (Priority Order)

1. Fix `demo/run_demo.sh` for proxy-only architecture.
   - Remove obsolete `--ops-*` Forge flags.
   - Add required `--proxy-backend` targeting local agent.
2. Add a unified two-process launcher.
   - Option A: one orchestrator script that starts agent + forge and handles shutdown.
   - Option B: explicit `demo-agent` and `demo-forge` scripts with clear docs.
3. Update `demo/README.md` to match the new architecture.
   - Include exact commands for both processes.
   - Include health-check and negative-check commands.
4. Add preflight diagnostics to demo commands.
   - verify backend health
   - verify LLM env/config presence
   - verify `jj` availability
5. Add deterministic demo scenarios and expected outcomes.
   - apply flow, refresh validation, undo flow, contract-negative checks.
6. Add lightweight artifact capture for demos.
   - optional log outputs and before/after file snapshot pointers.

## Fast Follow Implementation Scope

Minimal patch set to restore value quickly:

- `demo/run_demo.sh`: rework flags and backend assumptions
- `devenv.nix`: update `demo` helper scripts for two-process orchestration
- `demo/README.md`: replace startup and validation instructions

## Success Criteria For Improved Demo

- `devenv shell -- demo` (or equivalent documented flow) succeeds on a fresh checkout.
- Overlay apply + undo works end-to-end against live agent backend.
- Docs include exact expected responses for health and contract-negative checks.
- Demo can be run by a new contributor without tribal knowledge.
