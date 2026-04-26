#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cleanup_on_exit() {
  local exit_code=$?
  if [[ "${DEMO_KEEP_RUNTIME_ON_FAIL:-0}" == "1" && "$exit_code" -ne 0 ]]; then
    log "validation failed; preserving runtime for inspection at $RUNTIME_DIR"
    return
  fi
  "$SCRIPT_DIR/cleanup.sh" >/dev/null 2>&1 || true
}
trap cleanup_on_exit EXIT INT TERM

log "starting full-stack demo harness validation"

"$SCRIPT_DIR/cleanup.sh" >/dev/null 2>&1 || true
"$SCRIPT_DIR/setup.sh"
"$SCRIPT_DIR/start_stack.sh"

# shellcheck disable=SC1090
source "$PID_FILE"

log "asserting kiln process flags"
KILN_ARGS="$(ps -p "$KILN_PID" -o args=)"
printf '%s\n' "$KILN_ARGS" | grep -q -- '--no-serve'
printf '%s\n' "$KILN_ARGS" | grep -q -- '--on-rebuild'
printf '%s\n' "$KILN_ARGS" | grep -q -- "/internal/rebuild"

log "asserting overlay HTML injection"
ROOT_HTML="$RUNTIME_DIR/root.html"
curl -fsS "http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/index.html" > "$ROOT_HTML"
grep -q '/ops/ops.css' "$ROOT_HTML"
grep -q '/ops/ops.js' "$ROOT_HTML"

log "asserting /api/health proxy through overlay"
HEALTH_JSON="$RUNTIME_DIR/health.json"
curl -fsS "http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/api/health" > "$HEALTH_JSON"
python - "$HEALTH_JSON" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload.get("ok") is True
assert payload.get("provider") == "dummy-llm"
PY

log "asserting sync endpoint proxy + bootstrap lifecycle"
SYNC_ENSURE_JSON="$RUNTIME_DIR/sync_ensure.json"
curl -fsS -X POST "http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/api/vault/vcs/sync/ensure" \
  -H 'content-type: application/json' \
  -d '{}' \
  > "$SYNC_ENSURE_JSON"
python - "$SYNC_ENSURE_JSON" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload.get("status") == "ready"
PY

SYNC_REMOTE_JSON="$RUNTIME_DIR/sync_remote.json"
curl -fsS -X PUT "http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/api/vault/vcs/sync/remote" \
  -H 'content-type: application/json' \
  -d '{"remote":"origin","url":"https://github.com/example/demo-vault.git"}' \
  > "$SYNC_REMOTE_JSON"
python - "$SYNC_REMOTE_JSON" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload.get("remote") == "origin"
assert payload.get("url") == "https://github.com/example/demo-vault.git"
PY

SYNC_RUN_JSON="$RUNTIME_DIR/sync_run.json"
curl -fsS -X POST "http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/api/vault/vcs/sync" \
  -H 'content-type: application/json' \
  -d '{"remote":"origin"}' \
  > "$SYNC_RUN_JSON"
python - "$SYNC_RUN_JSON" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload.get("sync_ok") is True
assert payload.get("remote") == "origin"
PY

SYNC_STATUS_JSON="$RUNTIME_DIR/sync_status.json"
curl -fsS "http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/api/vault/vcs/sync/status" > "$SYNC_STATUS_JSON"
python - "$SYNC_STATUS_JSON" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload.get("status") == "ready"
assert payload.get("sync_count", 0) >= 1
PY

log "asserting rebuild webhook propagation"

TARGET_HTML="$PUBLIC_DIR/experiments/live-reload.html"
MUTATION_TOKEN="validation-mutation-$(date -u +%Y%m%dT%H%M%SZ)-$$"
REBUILD_COUNT_BEFORE="$(grep -c 'rebuilding after file change' "$LOG_DIR/kiln.log" || true)"
printf '\n\nValidation mutation token: %s\n' "$MUTATION_TOKEN" >> "$VAULT_DIR/experiments/live-reload.md"

MUTATION_DEADLINE=$((SECONDS + 60))
while (( SECONDS < MUTATION_DEADLINE )); do
  REBUILD_COUNT_AFTER="$(grep -c 'rebuilding after file change' "$LOG_DIR/kiln.log" || true)"
  if (( REBUILD_COUNT_AFTER > REBUILD_COUNT_BEFORE )) && grep -q "$MUTATION_TOKEN" "$TARGET_HTML"; then
    break
  fi
  sleep 0.25
done
REBUILD_COUNT_AFTER="$(grep -c 'rebuilding after file change' "$LOG_DIR/kiln.log" || true)"
if (( REBUILD_COUNT_AFTER <= REBUILD_COUNT_BEFORE )); then
  fail "kiln did not report incremental rebuild after vault mutation"
fi
grep -q "$MUTATION_TOKEN" "$TARGET_HTML"

if ! wait_for_log_pattern "$LOG_DIR/forge-overlay.log" 'POST /internal/rebuild' 30; then
  fail "overlay did not receive rebuild webhook"
fi
if ! grep -q 'POST /internal/rebuild HTTP/1.1" 204' "$LOG_DIR/forge-overlay.log"; then
  fail "overlay rebuild webhook did not return 204"
fi

log "asserting apply path through overlay proxy"
APPLY_JSON="$RUNTIME_DIR/apply.json"
curl -fsS -X POST "http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/api/agent/apply" \
  -H 'content-type: application/json' \
  -d '{"instruction":"Add deterministic release-note line","current_file":"projects/forge-v2.md"}' \
  > "$APPLY_JSON"
python - "$APPLY_JSON" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload.get("ok") is True
assert payload.get("changed_files") == ["projects/forge-v2.md"]
PY

FORGE_NOTE_HTML="$PUBLIC_DIR/projects/forge-v2.html"
DEADLINE=$((SECONDS + 45))
while (( SECONDS < DEADLINE )); do
  if grep -q 'Dummy LLM Update' "$FORGE_NOTE_HTML"; then
    break
  fi
  sleep 0.25
done
grep -q 'Dummy LLM Update' "$FORGE_NOTE_HTML"

log "asserting undo path through overlay proxy"
UNDO_JSON="$RUNTIME_DIR/undo.json"
curl -fsS -X POST "http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/api/undo" \
  -H 'content-type: application/json' \
  -d '{}' \
  > "$UNDO_JSON"
python - "$UNDO_JSON" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload.get("ok") is True
assert payload.get("changed_files") == ["projects/forge-v2.md"]
PY

# Wait for rebuild after undo and confirm marker is removed.
UNDO_WAIT_DEADLINE=$((SECONDS + 45))
while (( SECONDS < UNDO_WAIT_DEADLINE )); do
  if ! grep -q 'Dummy LLM Update' "$FORGE_NOTE_HTML"; then
    break
  fi
  sleep 0.25
done
if grep -q 'Dummy LLM Update' "$FORGE_NOTE_HTML"; then
  fail "undo did not remove dummy marker from rendered output"
fi

log "full-stack demo harness validation passed"
