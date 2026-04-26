# DECISIONS

1. Use a named Docker volume (`forge-vault`) for runtime vault storage.
- Rationale: avoids bind mount performance penalties on Docker Desktop Windows paths.

2. Use explicit sync scripts instead of shutdown hooks.
- Rationale: export-on-exit hooks are not reliable for crash/kill/restart paths.

3. Keep `VAULT_PATH` in `.env` as the host sync source/target.
- Rationale: preserves simple user configuration while decoupling runtime storage from host bind mounts.
