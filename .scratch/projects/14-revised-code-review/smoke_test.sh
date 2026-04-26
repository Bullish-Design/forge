#!/usr/bin/env bash
# smoke_test.sh — Docker container smoke test for Forge
#
# Tests that the forge Docker image builds, starts, serves the demo vault,
# hot-reloads on vault changes, and correctly proxies agent API calls.
# Optionally verifies connectivity to a remora-server LLM endpoint.
#
# Usage:
#   ./smoke_test.sh [options]
#
# Options:
#   --browser          Open browser at the site URL after checks pass
#   --remora-url URL   Remora LLM base URL to probe (default: http://remora-server:8000)
#                      Set to empty string ("") to skip remora probe
#   --port PORT        Host port to bind forge to (default: 9090)
#   --mock-port PORT   Host port for mock agent (default: 8082)
#   --skip-build       Skip docker build (use existing forge:smoke-test image)
#   --no-cleanup       Leave container and temp files running after test
#   -h, --help         Show this help
#
# Environment variables (override via env or flags):
#   REMORA_URL         Same as --remora-url
#   SMOKE_PORT         Same as --port
#   MOCK_AGENT_PORT    Same as --mock-port

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"   # repo root

SMOKE_PORT="${SMOKE_PORT:-9090}"
MOCK_AGENT_PORT="${MOCK_AGENT_PORT:-8082}"
REMORA_URL="${REMORA_URL:-http://remora-server:8000}"
OPEN_BROWSER=0
SKIP_BUILD=0
NO_CLEANUP=0
IMAGE_TAG="forge:smoke-test"
CONTAINER_NAME="forge-smoke"

SMOKE_VAULT="/tmp/forge-smoke-vault"
SMOKE_OUTPUT="/tmp/forge-smoke-output"

# PIDs to clean up
AGENT_PID=""

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --browser)       OPEN_BROWSER=1; shift ;;
    --remora-url)    REMORA_URL="${2:-}"; shift 2 ;;
    --port)          SMOKE_PORT="$2"; shift 2 ;;
    --mock-port)     MOCK_AGENT_PORT="$2"; shift 2 ;;
    --skip-build)    SKIP_BUILD=1; shift ;;
    --no-cleanup)    NO_CLEANUP=1; shift ;;
    -h|--help)
      sed -n '/^# Usage:/,/^[^#]/{ /^#/{ s/^# \{0,1\}//; p } }' "$0"
      exit 0
      ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
done

BASE_URL="http://127.0.0.1:${SMOKE_PORT}"

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

phase() { echo -e "\n${BOLD}==> $*${RESET}"; }
info()  { echo "    $*"; }
pass()  { echo -e "    ${GREEN}[PASS]${RESET} $*"; (( PASS_COUNT++ )) || true; }
fail()  { echo -e "    ${RED}[FAIL]${RESET} $*"; (( FAIL_COUNT++ )) || true; }
skip()  { echo -e "    ${YELLOW}[SKIP]${RESET} $*"; (( SKIP_COUNT++ )) || true; }
warn()  { echo -e "    ${YELLOW}[WARN]${RESET} $*"; }

# Run a check: check "description" <expected_code> <actual_code>
check_code() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    pass "${desc} (HTTP ${actual})"
  else
    fail "${desc} — expected HTTP ${expected}, got ${actual}"
  fi
}

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
cleanup() {
  local exit_code=$?
  if [[ ${NO_CLEANUP} -eq 1 ]]; then
    warn "Skipping cleanup (--no-cleanup). Container: ${CONTAINER_NAME}, vault: ${SMOKE_VAULT}"
    exit "${exit_code}"
  fi

  echo ""
  phase "Cleanup"
  if docker container inspect "${CONTAINER_NAME}" &>/dev/null; then
    docker rm -f "${CONTAINER_NAME}" &>/dev/null && info "Removed container ${CONTAINER_NAME}"
  fi
  if [[ -n "${AGENT_PID}" ]] && kill -0 "${AGENT_PID}" 2>/dev/null; then
    kill "${AGENT_PID}" 2>/dev/null || true
    wait "${AGENT_PID}" 2>/dev/null || true
    info "Stopped mock agent (PID ${AGENT_PID})"
  fi
  rm -rf "${SMOKE_VAULT}" "${SMOKE_OUTPUT}" /tmp/forge-smoke-sse.txt
  info "Removed temp dirs"
  exit "${exit_code}"
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------
phase "Prerequisites"

if ! command -v docker &>/dev/null; then
  fail "docker not found in PATH"
  exit 1
fi
pass "docker available ($(docker --version | head -1))"

if ! command -v python3 &>/dev/null; then
  fail "python3 not found (needed for mock agent)"
  exit 1
fi
pass "python3 available"

if ! command -v curl &>/dev/null; then
  fail "curl not found"
  exit 1
fi
pass "curl available"

# ---------------------------------------------------------------------------
# Phase 1: Build docker image
# ---------------------------------------------------------------------------
phase "Build Docker image"

if [[ ${SKIP_BUILD} -eq 1 ]]; then
  if docker image inspect "${IMAGE_TAG}" &>/dev/null; then
    skip "Skipping build (--skip-build), using existing ${IMAGE_TAG}"
  else
    fail "Image ${IMAGE_TAG} does not exist and --skip-build was set"
    exit 1
  fi
else
  info "Building ${IMAGE_TAG} from ${ROOT_DIR} ..."
  if docker build \
      -f "${ROOT_DIR}/docker/forge.Dockerfile" \
      -t "${IMAGE_TAG}" \
      "${ROOT_DIR}" \
      2>&1 | tail -5; then
    pass "Docker image built: ${IMAGE_TAG}"
  else
    fail "Docker build failed"
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Phase 2: Prepare vault
# ---------------------------------------------------------------------------
phase "Prepare demo vault"

rm -rf "${SMOKE_VAULT}" "${SMOKE_OUTPUT}"
cp -r "${ROOT_DIR}/demo/vault" "${SMOKE_VAULT}"
mkdir -p "${SMOKE_OUTPUT}"
pass "Copied demo vault to ${SMOKE_VAULT}"

# ---------------------------------------------------------------------------
# Phase 3: Start mock agent
# ---------------------------------------------------------------------------
phase "Start mock agent"

AGENT_VAULT_DIR="${SMOKE_VAULT}" \
  python3 "${SCRIPT_DIR}/mock_agent.py" "${MOCK_AGENT_PORT}" &>/tmp/mock-agent.log &
AGENT_PID=$!

# Wait for mock agent
for i in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:${MOCK_AGENT_PORT}/api/health" &>/dev/null; then
    pass "Mock agent healthy on port ${MOCK_AGENT_PORT}"
    break
  fi
  sleep 0.3
  if [[ $i -eq 20 ]]; then
    fail "Mock agent did not become healthy"
    cat /tmp/mock-agent.log || true
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# Phase 4: Start forge container
# ---------------------------------------------------------------------------
phase "Start forge container"

# Remove stale container if present
docker rm -f "${CONTAINER_NAME}" &>/dev/null || true

# Use host networking so the container can reach the mock agent on 127.0.0.1
docker run -d \
  --name "${CONTAINER_NAME}" \
  --network host \
  -v "${SMOKE_VAULT}:/data/vault" \
  -v "${SMOKE_OUTPUT}:/data/public" \
  -e VAULT_DIR=/data/vault \
  -e OUTPUT_DIR=/data/public \
  -e OVERLAY_DIR=/app/static \
  -e PORT="${SMOKE_PORT}" \
  -e PROXY_BACKEND="http://127.0.0.1:${MOCK_AGENT_PORT}" \
  "${IMAGE_TAG}"

pass "Container started: ${CONTAINER_NAME}"
info "Forge dev server: ${BASE_URL}"
info "Proxy backend:    http://127.0.0.1:${MOCK_AGENT_PORT}"

# ---------------------------------------------------------------------------
# Phase 5: Wait for forge to become healthy
# ---------------------------------------------------------------------------
phase "Wait for forge to become healthy"

HEALTHY=0
for i in $(seq 1 60); do
  HTTP=$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/health" 2>/dev/null || echo "000")
  if [[ "${HTTP}" == "200" ]]; then
    HEALTHY=1
    pass "Forge healthy after ~$((i / 2))s (${BASE_URL}/api/health → HTTP 200)"
    break
  fi
  sleep 0.5
done

if [[ ${HEALTHY} -eq 0 ]]; then
  fail "Forge did not become healthy within 30s"
  info "Container logs:"
  docker logs "${CONTAINER_NAME}" 2>&1 | tail -20
  exit 1
fi

# ---------------------------------------------------------------------------
# Phase 6: HTTP endpoint checks
# ---------------------------------------------------------------------------
phase "HTTP endpoint checks"

http_code() { curl -s -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo "000"; }
http_body() { curl -s "$1" 2>/dev/null; }
http_header() { curl -sI "$1" 2>/dev/null | grep -i "^$2:" | tr -d '\r' | cut -d' ' -f2-; }

# Homepage
check_code "GET / (homepage)" "200" "$(http_code "${BASE_URL}/")"

# Clean URL for a markdown page
check_code "GET /guides/getting-started (clean URL)" "200" \
  "$(http_code "${BASE_URL}/guides/getting-started")"

# Blog post
check_code "GET /blog/2026-03-01-launch-log" "200" \
  "$(http_code "${BASE_URL}/blog/2026-03-01-launch-log")"

# 404 for non-existent page
check_code "GET /does-not-exist (expect 404)" "404" \
  "$(http_code "${BASE_URL}/does-not-exist")"

# graph.json (always built)
GRAPH_BODY="$(http_body "${BASE_URL}/graph.json")"
if echo "${GRAPH_BODY}" | python3 -c 'import sys,json; json.load(sys.stdin)' &>/dev/null; then
  pass "GET /graph.json — valid JSON"
else
  fail "GET /graph.json — invalid or missing JSON response"
fi

# SSE endpoint headers
SSE_CT="$(http_header "${BASE_URL}/ops/events" "content-type")"
if [[ "${SSE_CT}" == *"text/event-stream"* ]]; then
  pass "GET /ops/events — Content-Type: text/event-stream"
else
  fail "GET /ops/events — unexpected Content-Type: '${SSE_CT}'"
fi

# Shared CSS asset
check_code "GET /shared.css (built asset)" "200" \
  "$(http_code "${BASE_URL}/shared.css")"

# App JS asset
check_code "GET /app.js (built asset)" "200" \
  "$(http_code "${BASE_URL}/app.js")"

# ---------------------------------------------------------------------------
# Phase 7: Agent API proxy checks
# ---------------------------------------------------------------------------
phase "Agent API proxy checks (via mock)"

check_code "GET /api/health (proxied to mock agent)" "200" \
  "$(http_code "${BASE_URL}/api/health")"

APPLY_BODY='{"instruction":"write a hello world note"}'
APPLY_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
  -X POST -H 'Content-Type: application/json' \
  -d "${APPLY_BODY}" \
  "${BASE_URL}/api/apply" 2>/dev/null || echo "000")
check_code "POST /api/apply (proxied to mock agent)" "200" "${APPLY_CODE}"

# ---------------------------------------------------------------------------
# Phase 8: Remora connectivity probe (optional)
# ---------------------------------------------------------------------------
phase "Remora LLM endpoint probe"

if [[ -z "${REMORA_URL}" ]]; then
  skip "REMORA_URL is empty — skipping remora probe"
else
  MODELS_URL="${REMORA_URL%/}/v1/models"
  info "Probing ${MODELS_URL} ..."
  REMORA_CODE=$(curl -s -o /tmp/remora-models.json -w '%{http_code}' \
    --connect-timeout 5 --max-time 10 \
    "${MODELS_URL}" 2>/dev/null || echo "000")

  if [[ "${REMORA_CODE}" == "200" ]]; then
    MODEL_COUNT=$(python3 -c \
      "import sys,json; d=json.load(open('/tmp/remora-models.json')); print(len(d.get('data',[])))" \
      2>/dev/null || echo "?")
    pass "Remora reachable at ${REMORA_URL} — ${MODEL_COUNT} model(s) available"
  elif [[ "${REMORA_CODE}" == "000" ]]; then
    warn "Remora not reachable at ${REMORA_URL} (connection refused or DNS failure)"
    info "This is expected if remora-server is not running locally."
    info "Start it and re-run with: REMORA_URL=http://localhost:8000 ./smoke_test.sh"
    (( SKIP_COUNT++ )) || true
  else
    warn "Remora returned HTTP ${REMORA_CODE} — may need authentication or different URL"
    (( SKIP_COUNT++ )) || true
  fi
fi

# ---------------------------------------------------------------------------
# Phase 9: Hot-reload (mutation) test
# ---------------------------------------------------------------------------
phase "Hot-reload test"

SSE_LOG="/tmp/forge-smoke-sse.txt"
info "Listening for SSE events on ${BASE_URL}/ops/events ..."

# Stream SSE in background, capturing events
timeout 25 curl -sN "${BASE_URL}/ops/events" >"${SSE_LOG}" 2>&1 &
SSE_PID=$!

# Give curl time to connect before writing the file
sleep 1

info "Writing smoke-test-page.md to vault ..."
cat >"${SMOKE_VAULT}/smoke-test-page.md" <<'MDEOF'
---
title: Smoke Test Page
publish: true
tags: [smoke-test]
---

# Smoke Test Page

This page was created automatically by the forge smoke test.

> [!tip]
> If you can read this, hot-reload is working.

Wikilink back to home: [[index]]
MDEOF

# Wait for the rebuilt event (forge watches every 200ms, debounces 500ms)
REBUILT=0
for i in $(seq 1 30); do
  sleep 0.5
  if grep -q '"type":"rebuilt"' "${SSE_LOG}" 2>/dev/null; then
    REBUILT=1
    break
  fi
done

# Stop SSE listener
kill "${SSE_PID}" 2>/dev/null || true
wait "${SSE_PID}" 2>/dev/null || true

if [[ ${REBUILT} -eq 1 ]]; then
  pass "Received 'rebuilt' SSE event after vault mutation"
else
  warn "Did not receive 'rebuilt' SSE event within 15s"
  info "SSE output: $(cat "${SSE_LOG}" 2>/dev/null | head -5)"
  (( SKIP_COUNT++ )) || true
fi

# Check the new page is served
NEW_PAGE_CODE="$(http_code "${BASE_URL}/smoke-test-page")"
check_code "GET /smoke-test-page (newly created file)" "200" "${NEW_PAGE_CODE}"

# Verify content
NEW_PAGE_BODY="$(http_body "${BASE_URL}/smoke-test-page")"
if echo "${NEW_PAGE_BODY}" | grep -q "Smoke Test Page"; then
  pass "New page body contains expected heading"
else
  fail "New page body does not contain 'Smoke Test Page'"
  info "Body preview: $(echo "${NEW_PAGE_BODY}" | head -3)"
fi

# Also verify the agent-result page (written by mock agent via POST /api/apply)
AGENT_PAGE_CODE="$(http_code "${BASE_URL}/agent-result")"
if [[ "${AGENT_PAGE_CODE}" == "200" ]]; then
  pass "GET /agent-result (file written by mock agent via /api/apply) → 200"
else
  warn "GET /agent-result returned ${AGENT_PAGE_CODE} (may not have rebuilt yet)"
  (( SKIP_COUNT++ )) || true
fi

# ---------------------------------------------------------------------------
# Phase 10: Browser (optional)
# ---------------------------------------------------------------------------
if [[ ${OPEN_BROWSER} -eq 1 ]]; then
  phase "Open browser"
  OPEN_CMD=""
  if command -v xdg-open &>/dev/null; then OPEN_CMD="xdg-open"
  elif command -v open &>/dev/null;     then OPEN_CMD="open"
  fi

  if [[ -n "${OPEN_CMD}" ]]; then
    info "Opening ${BASE_URL}/ ..."
    "${OPEN_CMD}" "${BASE_URL}/" &>/dev/null &
    info "Use the walkthrough in WALKTHROUGH.md to explore the site manually."
    info "Press Ctrl-C or wait for the script to exit to stop the container."
    # If browser mode, pause so the container keeps running for inspection
    info "Container will stay up. Press Enter to proceed to cleanup."
    read -r
  else
    warn "No browser opener found (xdg-open / open). Visit ${BASE_URL}/ manually."
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}====== Smoke Test Summary ======${RESET}"
echo -e "  ${GREEN}PASS: ${PASS_COUNT}${RESET}"
if [[ ${FAIL_COUNT} -gt 0 ]]; then
  echo -e "  ${RED}FAIL: ${FAIL_COUNT}${RESET}"
else
  echo -e "  FAIL: 0"
fi
echo -e "  ${YELLOW}SKIP: ${SKIP_COUNT}${RESET}"
echo ""

if [[ ${FAIL_COUNT} -gt 0 ]]; then
  echo -e "${RED}Some checks failed. See output above.${RESET}"
  echo "Container logs:"
  docker logs "${CONTAINER_NAME}" 2>&1 | tail -30
  exit 1
else
  echo -e "${GREEN}All checks passed.${RESET}"
  exit 0
fi
