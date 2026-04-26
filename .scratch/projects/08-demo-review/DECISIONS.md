# DECISIONS

## D-001: Demo script should target two-process runtime

The walkthrough uses:
1. `obsidian-agent` on `127.0.0.1:8081`
2. `forge dev` on `127.0.0.1:8080` with `--proxy-backend`

## D-002: Include explicit validation and failure diagnostics

`DEMO_SCRIPT.md` includes preflight checks and API-level smoke tests before browser steps.

## D-003: Review should prioritize reliability over polish

Top recommendations focus on fixing broken command paths and preventing silent configuration mistakes.
