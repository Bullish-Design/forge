# ASSUMPTIONS

- Audience: a developer/operator running Forge in Docker for a private or homelab setup.
- Primary goal: run `forge dev` in a container and expose it through a Tailscale sidecar.
- Secondary goal: allow Ops-driven vault mutation through `/api/apply` and instant site rebuild.
- Vault and generated output must persist on host-mounted volumes.
- The runtime should support either:
  - OpenAI-compatible LLM backend (`OPS_LLM_BASE_URL` / `OPS_LLM_MODEL`), or
  - Anthropic API (`ANTHROPIC_API_KEY`).
- `jj` (Jujutsu CLI) is treated as a required runtime dependency for reliable Ops workflows.
- This task is analysis/reporting, not full implementation of Docker artifacts in repo root.
