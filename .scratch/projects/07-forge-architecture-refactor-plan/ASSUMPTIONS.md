# ASSUMPTIONS

- Goal architecture is a three-part split:
  - Forge = thin host/proxy + overlay UI bridge
  - `obsidian-agent` = LLM orchestration/API backend
  - `obsidian-ops` = vault/VCS primitives
- We can change both dependency libraries (`obsidian-agent`, `obsidian-ops`) as needed.
- Backward compatibility for current Forge overlay UX is desired unless explicitly dropped.
- JJ-backed commit/undo behavior remains part of expected mutation lifecycle.
- The final refactor plan should include:
  - boundary moves
  - API contracts
  - migration sequencing
  - test/validation gates
