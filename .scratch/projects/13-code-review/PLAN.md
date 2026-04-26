# PLAN

## Critical Rule (Must Follow)

NO SUBAGENTS. All analysis, file reading, test execution, and edits must be done directly in this session.

## Objective

Produce a high-quality code review report for the target change set.

## Steps

1. Define review scope (branch/commit/PR/files).
2. Gather diff and relevant context files.
3. Run targeted tests and checks for impacted areas.
4. Inspect code paths for correctness, edge cases, and regressions.
5. Validate error handling, backward compatibility, and config assumptions.
6. Record findings by severity with exact file references.
7. Record open questions and residual risks.
8. Produce final review summary with recommended next actions.

## Acceptance Criteria

- Findings are prioritized (high/medium/low).
- Each finding has actionable detail and file references.
- Test/check results are documented.
- Open questions and residual risks are explicit.

## Critical Rule (Reinforced)

NO SUBAGENTS. Continue all review work directly without delegation.
