# Plan

1. Define migration state machine and safety gates (`.git` -> jj bridge).
2. Replace git-sync sidecar logic with jj-native sync engine.
3. Implement event-driven sync trigger loop.
4. Add conflict handling automation (bookmark/branch creation).
5. Add migration tooling + manual fallback commands.
6. Wire compose/env/runtime docs.
7. Validate with integration tests and failure-path simulations.
