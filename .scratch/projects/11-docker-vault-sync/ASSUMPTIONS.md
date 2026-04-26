# ASSUMPTIONS

- User prefers container-local vault storage for performance.
- Host sync can be explicit (import/export commands) rather than implicit shutdown hooks.
- `VAULT_PATH` remains the user-configured host filesystem path.
