#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "resetting demo runtime at $RUNTIME_DIR"
rm -rf "$RUNTIME_DIR"
mkdir -p "$VAULT_DIR" "$PUBLIC_DIR" "$OVERLAY_DIR" "$LOG_DIR"

cp -R "$VAULT_TEMPLATE_DIR/." "$VAULT_DIR/"
cp -R "$OVERLAY_TEMPLATE_DIR/." "$OVERLAY_DIR/"

cat > "$RUNTIME_DIR/forge.demo.yaml" <<CFG
vault_dir: $VAULT_DIR
output_dir: $PUBLIC_DIR
overlay_dir: $OVERLAY_DIR
host: $DEMO_OVERLAY_HOST
port: $DEMO_OVERLAY_PORT

agent:
  host: $DEMO_API_HOST
  port: $DEMO_API_PORT
  vault_dir: $VAULT_DIR
  llm_model: dummy:demo

kiln:
  bin: $KILN_BIN
  theme: default
  font: inter
  lang: en
  site_name: Forge Demo Harness
CFG

log "runtime prepared"
