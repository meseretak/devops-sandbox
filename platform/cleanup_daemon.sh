#!/usr/bin/env bash
# cleanup_daemon.sh — auto-destroy expired environments every 60s
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
LOG="$ROOT/logs/cleanup.log"

mkdir -p "$ROOT/logs"

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }

log "Cleanup daemon started (PID=$$)"

while true; do
  for STATE_FILE in "$ROOT/envs"/env-*.json; do
    [[ -f "$STATE_FILE" ]] || continue
    ENV_ID=$(basename "$STATE_FILE" .json)
    EXPIRES_AT=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('expires_at',0))" 2>/dev/null || echo 0)
    NOW=$(date -u +%s)
    if (( NOW > EXPIRES_AT )); then
      log "TTL expired for $ENV_ID — destroying"
      bash "$SCRIPT_DIR/destroy_env.sh" "$ENV_ID" >> "$LOG" 2>&1 && \
        log "Destroyed $ENV_ID" || \
        log "ERROR destroying $ENV_ID"
    fi
  done
  sleep 60
done
