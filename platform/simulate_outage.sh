#!/usr/bin/env bash
# simulate_outage.sh — inject failures into a sandbox environment
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

ENV_ID=""
MODE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)  ENV_ID="$2"; shift 2 ;;
    --mode) MODE="$2";   shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

[[ -z "$ENV_ID" ]] && { echo "Usage: simulate_outage.sh --env <id> --mode <crash|pause|network|recover|stress>"; exit 1; }
[[ -z "$MODE"   ]] && { echo "Usage: simulate_outage.sh --env <id> --mode <crash|pause|network|recover|stress>"; exit 1; }

STATE_FILE="$ROOT/envs/$ENV_ID.json"
[[ -f "$STATE_FILE" ]] || { echo "ERROR: No state file for $ENV_ID"; exit 1; }

CONTAINER=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d['container'])")
NETWORK=$(python3   -c "import json; d=json.load(open('$STATE_FILE')); print(d['network'])")

# Guard — never simulate against platform containers
for PROTECTED in sandbox-nginx sandbox-daemon sandbox-api; do
  if [[ "$CONTAINER" == "$PROTECTED" ]]; then
    echo "ERROR: Cannot simulate outage on protected container $PROTECTED"
    exit 1
  fi
done

echo "[$(date -u +%FT%TZ)] Simulating $MODE on $ENV_ID ($CONTAINER)"

case "$MODE" in
  crash)
    docker kill "$CONTAINER"
    echo "Container killed. Health monitor should detect within 90s."
    ;;
  pause)
    docker pause "$CONTAINER"
    echo "Container paused. Use --mode recover to unpause."
    ;;
  network)
    docker network disconnect "$NETWORK" "$CONTAINER"
    echo "Container disconnected from network. Use --mode recover to reconnect."
    ;;
  recover)
    # Try all recovery methods
    docker unpause "$CONTAINER" 2>/dev/null && echo "Unpaused." || true
    docker network connect "$NETWORK" "$CONTAINER" 2>/dev/null && echo "Reconnected to network." || true
    docker start "$CONTAINER" 2>/dev/null && echo "Restarted." || true
    # Update state to running
    python3 -c "
import json
with open('$STATE_FILE') as f: d=json.load(f)
d['status']='running'
import tempfile,os
tmp=tempfile.mktemp()
with open(tmp,'w') as f: json.dump(d,f,indent=2)
os.replace(tmp,'$STATE_FILE')
"
    echo "Recovery complete."
    ;;
  stress)
    docker exec "$CONTAINER" sh -c "apk add --no-cache stress-ng 2>/dev/null; stress-ng --cpu 2 --timeout 30s &" || \
    docker exec "$CONTAINER" sh -c "stress-ng --cpu 2 --timeout 30s &" || \
    echo "stress-ng not available in container"
    ;;
  *)
    echo "Unknown mode: $MODE. Use crash|pause|network|recover|stress"
    exit 1
    ;;
esac
