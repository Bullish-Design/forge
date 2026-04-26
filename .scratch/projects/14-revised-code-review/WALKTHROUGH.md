# Forge Docker Smoke Test — Walkthrough

This document accompanies `smoke_test.sh`. It explains each phase of the test,
what to look for in headless output, and what to verify interactively when
running with `--browser`.

---

## Quick Start

```bash
# From the repo root
cd .scratch/projects/14-revised-code-review

# Headless (automated, all checks):
./smoke_test.sh

# With browser (pauses for manual inspection):
./smoke_test.sh --browser

# Already built the image? Skip the docker build step:
./smoke_test.sh --skip-build

# Point at a real remora server:
./smoke_test.sh --remora-url http://localhost:8000

# Full combo:
./smoke_test.sh --browser --remora-url http://remora-server:8000
```

---

## Prerequisites

| Tool | Purpose |
|------|---------|
| `docker` | Build and run the forge container |
| `python3` | Run the mock obsidian-agent |
| `curl` | Drive HTTP checks |
| `xdg-open` / `open` | Open browser (optional, only with `--browser`) |

The script checks for all required tools before starting and exits early with a
clear error if any are missing.

---

## Architecture Under Test

```
Host
├── smoke_test.sh           ← orchestrates everything
├── mock_agent.py           ← fake obsidian-agent (port 8082)
│   ├── GET  /api/health    → {"status":"ok"}
│   └── POST /api/apply     → writes agent-result.md to vault
│
└── Docker container: forge:smoke-test (--network host, port 9090)
    ├── forge dev
    │   ├── Watches /data/vault (mounted from host)
    │   ├── Serves /data/public on :9090
    │   └── Proxies /api/* → http://127.0.0.1:8082 (mock agent)
    └── /ops/events         ← SSE stream for hot-reload events
```

The forge container uses `--network host` so it shares the host's loopback
interface and can reach the mock agent at `127.0.0.1:8082` without any extra
Docker networking configuration.

---

## Phase-by-Phase Guide

### Phase 1 — Build Docker image

The script runs:
```bash
docker build -f docker/forge.Dockerfile -t forge:smoke-test .
```

This is a multi-stage build: Go compilation happens in a `golang:bookworm`
builder stage, then the binary is copied into a `debian:bookworm-slim` runtime
image along with the `static/` overlay assets.

**Expected output:** Build completes and reports layer sizes.
**Skip with:** `--skip-build` (uses an existing `forge:smoke-test` image).

---

### Phase 2 — Prepare demo vault

A fresh copy of `demo/vault/` is placed at `/tmp/forge-smoke-vault/`. This is
the content the container will serve and watch for changes.

The copy is writable so the hot-reload phase can inject new files directly from
the host — just as a user editing a vault on disk would.

---

### Phase 3 — Start mock agent

`mock_agent.py` starts a tiny HTTP server on `127.0.0.1:8082` that mimics the
real obsidian-agent:

| Endpoint | Response |
|----------|----------|
| `GET /api/health` | `{"status":"ok","mock":true}` |
| `POST /api/apply` | Writes `agent-result.md` to vault, returns `{"ok":true}` |

This lets the forge proxy layer be exercised without needing a real LLM backend.
The mock agent's log is written to `/tmp/mock-agent.log`.

---

### Phase 4 — Start forge container

```bash
docker run -d \
  --name forge-smoke \
  --network host \
  -v /tmp/forge-smoke-vault:/data/vault \
  -v /tmp/forge-smoke-output:/data/public \
  -e PORT=9090 \
  -e PROXY_BACKEND=http://127.0.0.1:8082 \
  forge:smoke-test
```

The entrypoint runs `forge dev --input /data/vault --output /data/public
--inject-overlay --proxy-backend http://127.0.0.1:8082 --port 9090`.

Forge performs a **full initial build** of the demo vault, then starts the file
watcher and HTTP server.

---

### Phase 5 — Wait for forge to become healthy

The script polls `http://127.0.0.1:9090/api/health` (proxied through forge to
the mock agent) every 500ms for up to 30s. This verifies:

1. Forge's HTTP server is accepting connections
2. The initial build has completed (pages are served)
3. The proxy layer successfully routes to the mock agent

---

### Phase 6 — HTTP endpoint checks

| Check | What it verifies |
|-------|-----------------|
| `GET /` → 200 | Homepage (`demo/vault/index.md`) was built |
| `GET /guides/getting-started` → 200 | Clean URL resolution (no `.html` extension needed) |
| `GET /blog/2026-03-01-launch-log` → 200 | Nested path rendering |
| `GET /does-not-exist` → 404 | Custom 404 page is served |
| `GET /graph.json` → valid JSON | Knowledge graph was generated |
| `GET /ops/events` → `text/event-stream` | SSE endpoint is live |
| `GET /shared.css` → 200 | Built CSS asset served |
| `GET /app.js` → 200 | Built JS asset served |

**What to look for (headless):** All lines show `[PASS]`. Any `[FAIL]` line
includes the actual HTTP code received.

---

### Phase 7 — Agent API proxy checks

These verify forge's reverse proxy correctly forwards requests to the agent:

| Check | What it verifies |
|-------|-----------------|
| `GET /api/health` → 200 | Proxy routes GET to mock agent |
| `POST /api/apply` → 200 | Proxy routes POST with body to mock agent |

If the mock agent is not running or the proxy is misconfigured, these return
502 or 000.

---

### Phase 8 — Remora LLM endpoint probe (optional)

If `--remora-url` is set (or `REMORA_URL` env var), the script probes
`${REMORA_URL}/v1/models`. This is the endpoint the real obsidian-agent uses
to wait for LLM availability.

**Outcomes:**

- **PASS** — remora is reachable and returns a models list
- **SKIP (WARN)** — remora is not reachable (connection refused / DNS failure).
  This is expected when remora-server is not running locally.
- **SKIP (WARN)** — remora returned a non-200 code (auth, wrong URL, etc.)

The remora check is purely informational — it does not affect the pass/fail
outcome of the core tests.

**To run against a local remora-server:**
```bash
./smoke_test.sh --remora-url http://localhost:8000
```

**To run against the Docker Compose default:**
```bash
# Add remora-server to /etc/hosts or use its Docker network IP
./smoke_test.sh --remora-url http://remora-server:8000
```

---

### Phase 9 — Hot-reload (mutation) test

This is the most important integration test. It verifies the full
write → detect → rebuild → serve cycle.

**Steps:**
1. Open a background `curl` stream listening on `/ops/events`
2. Write `smoke-test-page.md` into the vault on the host filesystem
3. Wait up to 15s for a `{"type":"rebuilt"}` SSE event
4. Verify `GET /smoke-test-page` returns 200 with expected content
5. Verify `GET /agent-result` returns 200 (the file the mock agent wrote
   when `POST /api/apply` was called in Phase 7)

**What can go wrong:**
- The `rebuilt` event may not appear if the SSE connection is established after
  the rebuild completes (race condition). In that case, the check is reported as
  `[SKIP]` rather than `[FAIL]`, and the page availability check still runs.
- If forge's file watcher has a long debounce, the rebuild may take a few
  seconds longer than expected.

---

### Phase 10 — Browser (optional, `--browser`)

When `--browser` is passed, the script opens `http://127.0.0.1:9090/` in the
default browser and pauses for interactive inspection before cleaning up.

**Manual checks to perform in the browser:**

1. **Homepage** (`/`) — Verify the demo vault home page renders with correct
   title, embedded CTA block, Mermaid diagram, and math formula ($E=mc^2$).

2. **Navigation** — Click through sidebar links to confirm wikilink resolution
   works correctly.

3. **Getting Started** (`/guides/getting-started`) — Check that wikilinks to
   `[[glossary]]` and `[[rendering-features|Features]]` resolve without 404.

4. **Smoke test page** (`/smoke-test-page`) — This page was created during the
   test. Verify it renders with the callout tip box and the back-link to `index`.

5. **Agent result** (`/agent-result`) — This page was written by the mock agent
   via `POST /api/apply`. Verify its content shows the instruction string.

6. **404 page** (`/any-missing-page`) — Navigate to a non-existent URL. Should
   show the custom 404 page rather than a browser default.

7. **Graph** (`/graph`) — Open the knowledge graph page. Nodes for the new
   pages should appear.

8. **Search** — Use the search bar (if visible) to query for "smoke test".
   Should find the newly created page.

9. **Live reload** (advanced) — Keep the browser open, then in another terminal:
   ```bash
   echo "# Edited" >> /tmp/forge-smoke-vault/smoke-test-page.md
   ```
   The page should reload automatically in the browser within ~2s.

10. **Dev overlay** — In the browser's Network tab, verify `/ops/events` is an
    open SSE connection. Events appear there whenever a rebuild completes.

---

## Interpreting the Summary

```
====== Smoke Test Summary ======
  PASS: 14
  FAIL: 0
  SKIP: 1
```

- **PASS** — check ran and succeeded
- **FAIL** — check ran and failed; the container logs are dumped automatically
- **SKIP** — check was intentionally skipped (missing optional dep) or
  inconclusive (race condition in hot-reload detection)

The script exits with code `0` if `FAIL == 0`, `1` otherwise.

---

## Troubleshooting

**"Docker build failed"**
- Check for network issues (jj download in Dockerfile needs GitHub access)
- Try `--skip-build` if you already have a recent image

**"Forge did not become healthy within 30s"**
- Container logs are printed automatically
- Check if port 9090 is in use: `ss -tlnp | grep 9090`
- Check if the vault was copied correctly: `ls /tmp/forge-smoke-vault/`

**"Mock agent did not become healthy"**
- Check if port 8082 is in use: `ss -tlnp | grep 8082`
- Check `/tmp/mock-agent.log` for Python errors

**"GET /smoke-test-page returned 404"**
- The rebuild may not have triggered. Check that `/tmp/forge-smoke-vault/smoke-test-page.md` exists
- Try with `--no-cleanup`, then manually: `curl http://127.0.0.1:9090/smoke-test-page`

**Remora not reachable**
- Expected unless remora-server is running. Start it separately and retry with `--remora-url`
- The forge stack itself works fine without remora; it's only needed for LLM operations

---

## Cleanup

The script automatically removes the container and temp directories on exit
(Ctrl-C included). To skip cleanup for debugging:

```bash
./smoke_test.sh --no-cleanup
# Then manually:
docker logs forge-smoke
docker exec -it forge-smoke /bin/bash
docker rm -f forge-smoke
rm -rf /tmp/forge-smoke-vault /tmp/forge-smoke-output
```
