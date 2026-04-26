# forge

Python orchestrator for Forge v2.

## Demo Harness Validation

Run the full real-world demo harness validation (dummy LLM backend, real localhost stack):

```bash
devenv shell -- uv run demo/scripts/validate_full_stack.py
# equivalent entrypoint:
devenv shell -- uv run forge-demo-validate
```

See [demo/README.md](demo/README.md) for details.

For the real vLLM-backed free-explore UI demo:

```bash
devenv shell -- uv run forge-demo-run-free-explore
```

For Docker + Tailscale + agent-native jj sync setup, see:

```bash
docker/README.md
```
