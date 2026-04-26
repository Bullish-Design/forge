# DECISIONS

1. Treat "the library" as Forge itself (the repository's primary system), not an external dependency.
2. Cover both dimensions of Forge:
   - static site generator behavior
   - Forge-specific runtime extensions (overlay injection and `/api` proxying)
3. Include both setup tracks:
   - minimal local instance (Forge only)
   - full editing stack instance (Forge + obsidian-agent, especially Docker flow)
4. Base claims on implementation files where possible, using docs as secondary support.

