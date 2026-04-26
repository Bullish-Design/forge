# M3 Bootstrap Execution Checklist

Date: 2026-04-25 (revised)
Owner: `forge` workspace

M1 is accepted on kiln-fork v0.10.3. This checklist focuses on M3 (Python `forge` orchestrator) implementation.

---

## Prerequisites (all met)

| Component | Version | Status |
|---|---|---|
| `kiln-fork` | v0.10.3 | All tests passing, `--no-serve` and `--on-rebuild` validated |
| `forge-overlay` | 0.2.1 | 67 tests, ~99% coverage |
| `obsidian-ops` | 0.5.0 | Passing, ~95% coverage |
| `obsidian-agent` | 0.2.0 | 202 tests passing |

---

## Track A: M1 Follow-ups (non-blocking, defer)

### A1. Upstream PR (IGNORE - DO NOT UPSTREAM THESE CHANGES)

Goal: upstream only the two dev flags and webhook callback logic.

```bash
cd /home/andrew/Documents/Projects/kiln-fork
git remote -v  # Ensure upstream is present

# Create a PR branch on your fork from upstream main
git checkout -b upstream-pr-no-serve-on-rebuild upstream/main

# Cherry-pick only the relevant flag commits
git log --oneline v0.9.5..v0.10.3 -- internal/cli/commands.go internal/cli/dev.go
# then: git cherry-pick <sha1> <sha2> ...

devenv shell -- go test ./...
git push -u origin upstream-pr-no-serve-on-rebuild
```

Then open PR: `Bullish-Design/kiln-fork:upstream-pr-no-serve-on-rebuild` → `otaleghani/kiln:main`.

---

## Track B: M3 Implementation (`forge` orchestrator)

### B1. Create M3 branch

```bash
cd /home/andrew/Documents/Projects/forge
git fetch --all
git checkout -b m3-orchestrator-bootstrap
git push -u origin m3-orchestrator-bootstrap
```

### B2. Scaffold package and command entrypoint

Target structure:

```text
src/forge_cli/
  __init__.py
  __main__.py
  config.py
  processes.py
  commands.py
tests/
  test_config.py
  test_commands.py
forge.yaml.example
```

Implement first with minimal functionality:
- `forge dev` command exists and prints intended startup order
- config loads defaults from `forge.yaml` + env override placeholders

Commit:

```bash
cd /home/andrew/Documents/Projects/forge
git add src tests pyproject.toml forge.yaml.example
git commit -m "feat(m3): scaffold forge_cli package and base commands"
git push
```

### B3. Implement config model (`forge.yaml` + `FORGE_*`)

Add in `config.py`:
- vault/output/overlay dirs
- overlay port/host
- agent port/model env mapping
- kiln binary path, theme/font/lang/site-name
- derived:
  - `agent_url` (default `http://127.0.0.1:8081`)
  - `overlay_url` (default `http://127.0.0.1:8080`)
  - `on_rebuild_url` (derived: `{overlay_url}/internal/rebuild`)

Add tests for default + env override behavior.

Validate + commit:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- pytest -q

git add src/forge_cli/config.py tests/test_config.py forge.yaml.example
git commit -m "feat(m3): add forge config schema with derived urls"
git push
```

### B4. Implement process manager and health gate

Add in `processes.py`:
- subprocess start wrappers for:
  - `forge-overlay` (first — must listen before kiln fires first webhook)
  - `obsidian-agent` (second — health-gated)
  - `kiln dev --no-serve --on-rebuild <url>` (last — starts building immediately)
- `wait_for_http()` polling helper
- teardown on SIGINT/SIGTERM (kill children in reverse order)

Validate + commit:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- pytest -q

git add src/forge_cli/processes.py tests/test_commands.py
git commit -m "feat(m3): add process manager and overlay health gate"
git push
```

### B5. Wire runnable `forge dev`, `forge generate`, `forge serve`, `forge init`

Implement in `commands.py`:
- `forge dev`: overlay → agent → kiln startup order
- `forge generate`: kiln generate only
- `forge serve`: overlay only
- `forge init`: scaffold vault + config

Validate + commit:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- pytest -q

git add src/forge_cli/commands.py src/forge_cli/__main__.py tests
git commit -m "feat(m3): implement dev/generate/serve/init commands"
git push
```

### B6. First local smoke run from orchestrator repo

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- python -m forge_cli dev --config ./forge.yaml.example
```

Success criteria for bootstrap:
- overlay process starts and responds on configured port
- agent process starts and responds on configured port
- kiln process starts with `--no-serve` and `--on-rebuild http://localhost:8080/internal/rebuild`
- Ctrl-C tears down all children cleanly

Kiln invocation should be:
```bash
kiln dev --no-serve --on-rebuild http://localhost:8080/internal/rebuild \
         --input <vault_dir> --output <output_dir>
```

---

## Stop/Go Gates for M4

Proceed to M4 only when all are true:
- M3 branch has runnable `forge dev` startup sequence
- `forge-overlay`, `obsidian-agent`, `obsidian-ops` remain green
- kiln-fork v0.10.3 remains green

---

## Quick Start (Right Now)

```bash
cd /home/andrew/Documents/Projects/forge
git checkout -b m3-orchestrator-bootstrap
```

Then scaffold the package structure (B2).
