# obsidian-agent Refactor Review

## Findings

### 1. Low: `current_file` validation rejects dangerous forms but does not canonicalize equivalent relative paths

The validator correctly rejects URLs, absolute paths, traversal, and backslashes, but it returns the input string after trimming rather than returning a canonical normalized relative path. Inputs like `./note.md` or repeated separators can still survive into logs, prompts, and context handling as alternate spellings of the same file.

References:

- [models.py](/home/andrew/Documents/Projects/obsidian-agent/src/obsidian_agent/models.py:23)
- [models.py](/home/andrew/Documents/Projects/obsidian-agent/src/obsidian_agent/models.py:48)

Why this matters:

- The guide pushed toward a stricter `current_file` contract.
- This is not a security issue and likely not a functional break today.
- It does leave room for inconsistent path representations across logs, prompts, and any future session/state features.

## Open Questions

1. Does the team want `current_file` to remain a validated-but-pass-through string, or should the API normalize equivalent forms into one canonical representation before use?

## Verification

Local verification completed:

- `devenv shell -- pytest -q` -> `122 passed`

Additional review notes:

- The architectural boundary fix is in place: the agent no longer shells out to `jj` directly during undo and instead delegates to `obsidian-ops`.
- The `current_file` contract is documented, invalid payloads are rejected deterministically, the tool surface was expanded to include the new stable frontmatter operations, and the artifact-based test workflow remains intact.
- I did not find a functional regression in the current agent loop, API handlers, or undo flow.

## Change Summary

The refactor is largely correct. The main remaining issue is dependency packaging strategy; the only other issue I found is low-severity contract polish around `current_file` normalization.
