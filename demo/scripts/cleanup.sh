#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if [[ -f "$PID_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$PID_FILE"
  log "stopping demo processes"
  stop_pid_if_running "${KILN_PID:-}"
  stop_pid_if_running "${OVERLAY_PID:-}"
  stop_pid_if_running "${DUMMY_API_PID:-}"
fi

log "removing runtime"
rm -rf "$RUNTIME_DIR"

log "cleanup complete"
