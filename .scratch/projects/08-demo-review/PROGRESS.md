# PROGRESS

## Status

- [x] Created new numbered project template directory.
- [x] Reviewed current demo scripts/docs and runtime behavior.
- [x] Confirmed current `demo` command failure after architecture cutover.
- [x] Wrote `DEMO_SCRIPT.md` for two-process demo walkthrough.
- [x] Wrote `DEMO_REVIEW.md` with prioritized improvement recommendations.

## Evidence

- `devenv shell -- demo` currently fails with:
  - `Error: unknown flag: --ops-llm-base-url`
- Failure source:
  - `demo/run_demo.sh` still passes `--ops-llm-base-url`, `--ops-llm-model`, `--ops-api-key` to `forge dev`.
- `forge dev` now expects proxy-based backend integration (`--proxy-backend`) for runtime API behavior.
