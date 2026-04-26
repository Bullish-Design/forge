#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_cmd curl
require_cmd uv

if [[ -f "$PID_FILE" ]]; then
  fail "existing pid file found at $PID_FILE (run: uv run demo/scripts/cleanup.py)"
fi

if ! ensure_port_free "$DEMO_API_HOST" "$DEMO_API_PORT"; then
  fail "port already in use: $DEMO_API_HOST:$DEMO_API_PORT (run: uv run demo/scripts/cleanup.py, or stop conflicting process)"
fi
if ! ensure_port_free "$DEMO_OVERLAY_HOST" "$DEMO_OVERLAY_PORT"; then
  fail "port already in use: $DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT (run: uv run demo/scripts/cleanup.py, or stop conflicting process)"
fi

if [[ ! -d "$FORGE_OVERLAY_PROJECT_DIR" ]]; then
  fail "forge-overlay project not found at $FORGE_OVERLAY_PROJECT_DIR"
fi

if [[ ! -x "$KILN_BIN" ]] && ! command -v "$KILN_BIN" >/dev/null 2>&1; then
  fail "kiln binary not found: $KILN_BIN"
fi

mkdir -p "$LOG_DIR"

cleanup_partial() {
  stop_pid_if_running "${KILN_PID:-}"
  stop_pid_if_running "${OVERLAY_PID:-}"
  stop_pid_if_running "${DUMMY_API_PID:-}"
}
trap cleanup_partial ERR

log "starting dummy API server on :$DEMO_API_PORT"
nohup uv run "$DEMO_DIR/tools/dummy_api_server.py" \
  --host "$DEMO_API_HOST" \
  --port "$DEMO_API_PORT" \
  --vault-dir "$VAULT_DIR" \
  >"$LOG_DIR/dummy-api.log" 2>&1 < /dev/null &
DUMMY_API_PID=$!

if ! wait_for_http "http://$DEMO_API_HOST:$DEMO_API_PORT/api/health" 20; then
  fail "dummy API failed health check"
fi

log "starting forge-overlay on :$DEMO_OVERLAY_PORT"
nohup uv run --project "$FORGE_OVERLAY_PROJECT_DIR" forge-overlay \
  --site-dir "$PUBLIC_DIR" \
  --overlay-dir "$OVERLAY_DIR" \
  --api-upstream "http://$DEMO_API_HOST:$DEMO_API_PORT" \
  --host "$DEMO_OVERLAY_HOST" \
  --port "$DEMO_OVERLAY_PORT" \
  >"$LOG_DIR/forge-overlay.log" 2>&1 < /dev/null &
OVERLAY_PID=$!

if ! wait_for_http_any_status "http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/" 30; then
  fail "forge-overlay failed health check"
fi

log "starting kiln watcher with --no-serve + --on-rebuild"
nohup "$KILN_BIN" dev \
  --no-serve \
  --on-rebuild "http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/internal/rebuild" \
  --input "$VAULT_DIR" \
  --output "$PUBLIC_DIR" \
  --theme default \
  --font inter \
  --lang en \
  --name "Forge Demo Harness" \
  >"$LOG_DIR/kiln.log" 2>&1 < /dev/null &
KILN_PID=$!

if ! wait_for_file "$PUBLIC_DIR/index.html" 45; then
  fail "kiln initial build did not produce index.html"
fi
if ! wait_for_log_pattern "$LOG_DIR/kiln.log" 'Build complete' 60; then
  fail "kiln initial build did not reach completion"
fi
if ! kill -0 "$KILN_PID" >/dev/null 2>&1; then
  fail "kiln process exited unexpectedly after initial build"
fi

cat > "$PID_FILE" <<PIDS
DUMMY_API_PID=$DUMMY_API_PID
OVERLAY_PID=$OVERLAY_PID
KILN_PID=$KILN_PID
PIDS

trap - ERR

log "stack started"
log "site: http://$DEMO_OVERLAY_HOST:$DEMO_OVERLAY_PORT/index.html"
