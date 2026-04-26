#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

RUNTIME_DIR="${DEMO_RUNTIME_DIR:-$DEMO_DIR/runtime}"
VAULT_TEMPLATE_DIR="$DEMO_DIR/vault-template"
OVERLAY_TEMPLATE_DIR="$DEMO_DIR/overlay"

VAULT_DIR="$RUNTIME_DIR/vault"
PUBLIC_DIR="$RUNTIME_DIR/public"
OVERLAY_DIR="$RUNTIME_DIR/overlay"
LOG_DIR="$RUNTIME_DIR/logs"
PID_FILE="$RUNTIME_DIR/pids.env"

DEMO_OVERLAY_HOST="${DEMO_OVERLAY_HOST:-127.0.0.1}"
DEMO_OVERLAY_PORT="${DEMO_OVERLAY_PORT:-18080}"
DEMO_API_HOST="${DEMO_API_HOST:-127.0.0.1}"
DEMO_API_PORT="${DEMO_API_PORT:-18081}"

FORGE_OVERLAY_PROJECT_DIR="${FORGE_OVERLAY_PROJECT_DIR:-/home/andrew/Documents/Projects/forge-overlay}"

if [[ -x /home/andrew/Documents/Projects/kiln-fork/kiln ]]; then
  DEFAULT_KILN_BIN="/home/andrew/Documents/Projects/kiln-fork/kiln"
else
  DEFAULT_KILN_BIN="kiln"
fi
KILN_BIN="${KILN_BIN:-$DEFAULT_KILN_BIN}"

log() {
  printf '[demo] %s\n' "$*"
}

fail() {
  printf '[demo][error] %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "required command not found: $1"
  fi
}

ensure_port_free() {
  local host="$1"
  local port="$2"
  python - "$host" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.5)
    result = sock.connect_ex((host, port))
    if result == 0:
        raise SystemExit(1)
PY
}

wait_for_http() {
  local url="$1"
  local timeout_s="${2:-45}"
  local deadline=$((SECONDS + timeout_s))

  while (( SECONDS < deadline )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done

  return 1
}

wait_for_http_any_status() {
  local url="$1"
  local timeout_s="${2:-45}"
  local deadline=$((SECONDS + timeout_s))

  while (( SECONDS < deadline )); do
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$code" != "000" ]]; then
      return 0
    fi
    sleep 0.25
  done

  return 1
}

wait_for_file() {
  local path="$1"
  local timeout_s="${2:-45}"
  local deadline=$((SECONDS + timeout_s))

  while (( SECONDS < deadline )); do
    if [[ -f "$path" ]]; then
      return 0
    fi
    sleep 0.2
  done

  return 1
}

file_mtime() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo 0
    return 0
  fi
  stat -c '%Y' "$path"
}

wait_for_mtime_gt() {
  local path="$1"
  local previous="$2"
  local timeout_s="${3:-45}"
  local deadline=$((SECONDS + timeout_s))

  while (( SECONDS < deadline )); do
    local current
    current="$(file_mtime "$path")"
    if (( current > previous )); then
      return 0
    fi
    sleep 0.25
  done

  return 1
}

wait_for_log_pattern() {
  local log_file="$1"
  local pattern="$2"
  local timeout_s="${3:-45}"
  local deadline=$((SECONDS + timeout_s))

  while (( SECONDS < deadline )); do
    if [[ -f "$log_file" ]] && grep -q "$pattern" "$log_file"; then
      return 0
    fi
    sleep 0.2
  done

  return 1
}

stop_pid_if_running() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return 0
  fi
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi

  kill "$pid" >/dev/null 2>&1 || true
  local deadline=$((SECONDS + 10))
  while kill -0 "$pid" >/dev/null 2>&1 && (( SECONDS < deadline )); do
    sleep 0.2
  done

  if kill -0 "$pid" >/dev/null 2>&1; then
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
}

assert_json_expr() {
  local expression="$1"
  python - "$expression" <<'PY'
import json
import sys

expr = sys.argv[1]
payload = json.load(sys.stdin)
if not eval(expr, {}, {"payload": payload}):
    raise SystemExit(1)
PY
}
