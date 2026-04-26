# obsidian-ops Refactor Review

## Findings

### 1. Low: the dev environment still depends on a manual dependency sync step for full-suite reliability

The repo now documents `devenv shell -- uv sync --extra dev`, but `devenv` itself does not enforce or automatically perform that sync. The shell prints a reminder, and the full suite passes once the environment is populated, but a fresh development environment can still regress to missing server dependencies until the user performs the manual sync step.

References:

- [devenv.nix](/home/andrew/Documents/Projects/obsidian-ops/devenv.nix:45)
- [devenv.nix](/home/andrew/Documents/Projects/obsidian-ops/devenv.nix:53)
- [README.md](/home/andrew/Documents/Projects/obsidian-ops/README.md:61)
- [README.md](/home/andrew/Documents/Projects/obsidian-ops/README.md:64)

Why this matters:

- The refactor guide required the default repo workflow to support full-suite validation reliably.
- The current setup is workable, but it is still stateful: success depends on prior local environment preparation.
- That is acceptable for an internal repo if intentional, but it should not be described as a fully self-contained default environment.

## Open Questions

1. Should `devenv` be treated only as a shell/tool bootstrapper, or is the goal that a fresh `devenv shell -- pytest -q` works without requiring a separate `uv sync --extra dev` step?

## Verification

Local verification completed:

- `devenv shell -- pytest -q` -> passed

Additional review notes:

- The guide-driven changes are otherwise in place: deep frontmatter merge support exists, the higher-level `undo_last_change()` VCS lifecycle exists, server models are typed, glob behavior is documented as vault-relative-path matching, and the README is substantially improved.
- I did not find a correctness bug in the main vault/content/VCS code paths from the current implementation.

## Change Summary

The refactor materially improved the repo. The main remaining issues are packaging and environment polish rather than core vault behavior.
