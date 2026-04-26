# ASSUMPTIONS

- Project type: code review.
- Primary goal: identify defects, regressions, risks, and missing tests.
- Scope: repository changes under review plus directly impacted files.
- Non-goals: feature expansion unrelated to findings.
- Constraints:
  - No subagents may be used.
  - Findings should be prioritized by severity.
  - Every finding should include concrete evidence (file/line/test behavior).
- Output expectations:
  - Findings first.
  - Open questions/assumptions second.
  - Change summary last.
