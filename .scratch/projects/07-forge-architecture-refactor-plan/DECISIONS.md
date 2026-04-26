# DECISIONS

## D-001: Use this directory as the refactor-planning workspace

- Path: `.scratch/projects/07-forge-architecture-refactor-plan/`
- Reason: keep analysis artifacts and the final plan isolated from previous draft reviews.

## D-002: Immediate API cutover to `current_file`

- `current_url_path` compatibility bridge is not required.
- Frontend and backend can change together in one cutover.

## D-003: Commit/undo ownership moved to obsidian-ops API surface

- Agent should use `obsidian-ops` VCS APIs only.
- No raw JJ orchestration should remain outside `obsidian-ops`.

## D-004: Work may be phased as needed

- Implementation can be broken into practical milestones.

## D-005: URL-to-file ownership stays in Forge

- Forge will emit `current_file` page context to the overlay frontend.
- Backend libraries remain independent from Forge route-resolution logic.

## D-006: v1 runtime topology is two-process

- Run `forge` + `obsidian-agent` in v1.
- Keep `obsidian-ops` as a library dependency in v1; standalone server mode remains optional for later phases.

## D-007: Create a detailed implementation guide for intern execution

- Added `ARCHITECTURE_REFACTOR_GUIDE.md` as the primary step-by-step execution guide.
- Guide includes per-step testing and verification requirements.
