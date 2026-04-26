# CONTEXT

## Objective

Create a practical demo walkthrough and review the current Forge demo for reliability and clarity after architecture refactor.

## Current Demo Artifacts

- `demo/README.md`
- `demo/run_demo.sh`
- `devenv.nix` (`demo`, `demo-clean` scripts)
- `demo/vault` and `demo/runtime-vault`

## Current Architectural Reality

- Forge is now proxy-only for `/api/*` in `forge dev`.
- Runtime operations require a separate `obsidian-agent` process.
- Overlay payload contract is `instruction + current_file + interface_id`.
