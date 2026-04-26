# DEMO_SCRIPT

## Goal

Demonstrate end-to-end Forge + overlay + backend operations in the current architecture:

- Forge: static host + overlay injection + `/api/*` proxy
- Obsidian-agent: `/api/apply`, `/api/undo`, `/api/health`
- Obsidian-ops: vault and VCS operations via agent

## Demo Duration

- Quick run: 10-15 minutes
- Full walkthrough: 20-30 minutes

## Prerequisites

- Repos available locally:
  - `/home/andrew/Documents/Projects/forge`
  - `/home/andrew/Documents/Projects/obsidian-agent`
- `devenv` installed
- `jj` installed
- LLM backend configured:
  - Anthropic path: set `ANTHROPIC_API_KEY`
  - OpenAI-compatible path: set `AGENT_LLM_BASE_URL` + model/provider

## Preflight Checks

### 1) Reset demo content

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- demo-clean
```

### 2) Confirm vault and JJ workspace can initialize

```bash
cd /home/andrew/Documents/Projects/forge
[ -d demo/runtime-vault ] && echo "runtime-vault ready"
```

### 3) Start backend (`obsidian-agent`)

Terminal A:

```bash
cd /home/andrew/Documents/Projects/obsidian-agent
AGENT_VAULT_DIR=/home/andrew/Documents/Projects/forge/demo/runtime-vault \
AGENT_HOST=127.0.0.1 \
AGENT_PORT=8081 \
# Optional for OpenAI-compatible endpoint:
# AGENT_LLM_MODEL=openai:Qwen/Qwen3-4B-Instruct-2507-FP8 \
# AGENT_LLM_BASE_URL=http://remora-server:8000/v1 \
devenv shell -- obsidian-agent
```

### 4) Start frontend host (`forge`)

Terminal B:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- go run ./cmd/forge dev \
  --input ./demo/runtime-vault \
  --output ./demo/public \
  --overlay-dir ./static \
  --inject-overlay \
  --proxy-backend http://127.0.0.1:8081 \
  --port 8080
```

### 5) Sanity check backend through direct + proxy paths

Terminal C:

```bash
curl -sS http://127.0.0.1:8081/api/health
curl -sS http://127.0.0.1:8080/api/health
```

Expected both to return:

```json
{"ok":true,"status":"healthy"}
```

## Main Walkthrough

### Step 1: Load site and verify overlay

1. Open `http://127.0.0.1:8080/`.
2. Confirm page renders and overlay launcher appears.
3. Open browser network tab and filter for `/api/`.

### Step 2: Run a simple instruction on current note

1. Open a note page (for example homepage or a guide page).
2. Open overlay.
3. Submit a small edit instruction, for example:
   - `Add a one-line note at the end saying "Demo edit complete."`
4. Verify `/api/apply` returns a valid `OperationResult`.

### Step 3: Validate content update

1. Refresh page.
2. Confirm rendered content changed.
3. Optionally inspect source vault file under `demo/runtime-vault`.

### Step 4: Undo

1. Click `Undo` in overlay.
2. Confirm success response from `/api/undo`.
3. Refresh and verify prior state restored.

## Negative/Robustness Checks

### Contract rejection checks

```bash
curl -sS -X POST http://127.0.0.1:8081/api/apply \
  -H 'content-type: application/json' \
  -d '{"instruction":"x","current_url_path":"/bad"}'

curl -sS -X POST http://127.0.0.1:8081/api/apply \
  -H 'content-type: application/json' \
  -d '{"instruction":"x","interface_id":"unknown"}'
```

Expected:
- first request: 422 validation failure
- second request: deterministic unsupported interface error

## What To Try (Feature Demonstration Ideas)

- Targeted rewrite:
  - Ask for a concise rewrite of one paragraph.
- Structure edit:
  - Ask to add a new section with heading.
- Metadata/frontmatter behavior:
  - Ask to adjust tags or status field on a note.
- Multi-step instruction:
  - Ask for a small set of coordinated edits across two related notes.
- Undo safety:
  - Perform two changes, then run undo and verify latest change rollback behavior.

## Troubleshooting

- Overlay visible but actions fail:
  - verify `--proxy-backend http://127.0.0.1:8081` is set in Forge command.
- 422 on apply:
  - inspect payload shape (`current_file`/`interface_id`).
- 500 on apply:
  - check agent logs for missing LLM credentials or backend unavailability.
- No content update after success:
  - confirm edits target a note page with valid `current_file` context.

## Demo Exit

- Stop both processes with `Ctrl+C`.
- Reset demo state when needed:

```bash
cd /home/andrew/Documents/Projects/forge
devenv shell -- demo-clean
```
