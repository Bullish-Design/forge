# PLAN

NO SUBAGENTS. ALL WORK IS PERFORMED DIRECTLY IN THIS SESSION.

## Steps

1. Study `.scratch/projects/06-forge-architecture-refactor/forge-architecture-refactor.md`.
2. Analyze current Forge integration points (`/api/*`, overlay UI payloads, proxy behavior, path resolution, rebuild/watch).
3. Analyze dependency boundaries in:
   - `/home/andrew/Documents/Projects/obsidian-agent`
   - `/home/andrew/Documents/Projects/obsidian-ops`
4. Identify what should stay in Forge vs move into dependency libraries.
5. Capture unresolved architectural choices and ask clarifying questions.
6. Write and finalize `ARCHITECTURE_REFACTOR_PLAN.md`.
7. Write a very detailed, intern-oriented `ARCHITECTURE_REFACTOR_GUIDE.md` with implementation steps and testing expectations per step.
8. Update project tracking/context files with final status.

## Acceptance Criteria

- A new numbered project directory exists under `.scratch/projects/`.
- Standard project files exist: `PROGRESS.md`, `CONTEXT.md`, `PLAN.md`, `DECISIONS.md`, `ASSUMPTIONS.md`, `ISSUES.md`.
- `ARCHITECTURE_REFACTOR_PLAN.md` exists in this directory and is finalized with explicit architecture decisions.
- `ARCHITECTURE_REFACTOR_GUIDE.md` exists in this directory and is detailed enough for a new intern to execute implementation and testing end-to-end.

NO SUBAGENTS. ALL WORK IS PERFORMED DIRECTLY IN THIS SESSION.
