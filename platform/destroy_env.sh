#!/usr/bin/env bash
# destroy_env.sh — tear down a sandbox environment
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
source "$ROOT/.env" 2>/dev/null || true

ENV_ID="${1:?Usage: destroy_env.sh <env-id>}"
STATE_FILE="$ROOT/envs/$ENV_ID.json"
LOG_DIR="$ROOT/logs/$ENV_ID"
ARCHIVE_DIR="$ROOT/logs/archived/$ENV_ID"
NGINX_CONF="$ROOT/nginx/conf.d/$ENV_ID.conf"

if [[ ! -f "$STATE_FILE" ]]; then
  echo "[$(date -u +%FT%TZ)] ERROR: No state file for $ENV_ID" >&2
  exit 1
fi

echo "[$(date -u +%FT%TZ)] Destroying environment: $ENV_ID"

# Read state
CONTAINER=$(python3 -c "import json,sys; d=json.load(open('$STATE_FILE')); print(d['container'])")
NETWORK=$(python3  -c "import json,sys; d=json.load(open('$STATE_FILE')); print(d['network'])")

# 1. Kill log-shipping process
if [[ -f "$LOG_DIR/log_pid" ]]; then
  LOG_PID=$(cat "$LOG_DIR/log_pid")
  kill "$LOG_PID" 2>/dev/null || true
  rm -f "$LOG_DIR/log_pid"
fi

# 2. Stop and remove all labeled containers
docker ps -q --filter "label=sandbox.env=$ENV_ID" | xargs -r docker stop  2>/dev/null || true
docker ps -aq --filter "label=sandbox.env=$ENV_ID" | xargs -r docker rm -f 2>/dev/null || true

# 3. Remove Docker network
docker network rm "$NETWORK" 2>/dev/null || true

# 4. Remove Nginx config and reload
rm -f "$NGINX_CONF"
docker exec sandbox-nginx nginx -s reload 2>/dev/null || true

# 5. Archive logs
mkdir -p "$ARCHIVE_DIR"
if [[ -d "$LOG_DIR" ]]; then
  cp -r "$LOG_DIR/." "$ARCHIVE_DIR/" 2>/dev/null || true
  rm -rf "$LOG_DIR"
fi

# 6. Delete state file
rm -f "$STATE_FILE"

echo "[$(date -u +%FT%TZ)] ✅ Environment $ENV_ID destroyed and logs archived to $ARCHIVE_DIR"
