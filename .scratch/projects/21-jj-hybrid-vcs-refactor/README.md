# JJ Hybrid VCS Refactor

## Goal
Refactor Forge container runtime and vault sync to use Jujutsu (jj) as the in-app VCS, with GitHub sync via jj git bridge.

## Mode
Hybrid migration:
- auto-migrate safe existing `.git` vault states
- fall back to explicit/manual migration path for complex states

## Key Requirements
- jj primary VCS in vault
- bidirectional GitHub sync
- conflict handling: auto-create conflict branch/bookmark and continue
- GITHUB_TOKEN auth
- event-driven sync (with optional periodic fallback)
- bot identity default, overridable via env
