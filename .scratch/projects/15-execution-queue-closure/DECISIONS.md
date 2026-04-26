# DECISIONS

## D-001: Prioritize demo restoration before deeper refactors

- Rationale: Broken demo blocks onboarding, validation, and stakeholder confidence.
- Consequence: Milestone M1 is treated as the release blocker and starts first.

## D-002: Separate architecture-risk work from frontend cleanup

- Rationale: Core correctness and maintainability issues (BuildContext/globals/CLI flag globals) carry higher risk than presentation-layer deduplication.
- Consequence: M2 executes before M3/M4.

## D-003: Run M3 and M4 in parallel after M2

- Rationale: Theme/config cleanup and JS/CSS consolidation are mostly independent.
- Consequence: Shorter overall cycle time with reduced merge contention.

## D-004: Keep a dedicated sign-off milestone

- Rationale: Project `13` remains formally incomplete and needs explicit closure.
- Consequence: M5 is required for documentation, test evidence, and final review completion.
