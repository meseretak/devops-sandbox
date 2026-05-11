#!/usr/bin/env bash
# create_env.sh — spin up a new sandbox environment
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
source "$ROOT/.env" 2>/dev/null || true

NAME="${1:-sandbox}"
# Sanitize name — replace spaces and special chars with hyphens
NAME=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')
TTL="${2:-${DEFAULT_TTL:-1800}}"
ENV_ID="env-$(date +%s)-$(python3 -c 'import secrets; print(secrets.token_hex(4))')"
NETWORK="net-$ENV_ID"
CONTAINER="app-$ENV_ID"
APP_IMAGE="${APP_IMAGE:-sandbox-app:latest}"
NGINX_CONF="$ROOT/nginx/conf.d/$ENV_ID.conf"
STATE_FILE="$ROOT/envs/$ENV_ID.json"
LOG_DIR="$ROOT/logs/$ENV_ID"
PORT=$(python3 -c "import random; print(random.randint(10000,19999))")

mkdir -p "$LOG_DIR" "$ROOT/envs"

echo "[$(date -u +%FT%TZ)] Creating environment: $ENV_ID (name=$NAME, ttl=${TTL}s)"

# 1. Create Docker network
docker network create "$NETWORK" >/dev/null

# 2. Start app container
docker run -d \
  --name "$CONTAINER" \
  --network sandbox-net \
  -e ENV_ID="$ENV_ID" \
  -e ENV_NAME="$NAME" \
  -l "sandbox.env=$ENV_ID" \
  -l "sandbox.name=$NAME" \
  -p "$PORT:5000" \
  "$APP_IMAGE" >/dev/null

# Also connect to env-specific network
docker network connect "$NETWORK" "$CONTAINER" 2>/dev/null || true

# 3. Write Nginx config
cat > "$NGINX_CONF" <<EOF
upstream $ENV_ID {
    server $CONTAINER:5000;
}
server {
    listen 80;
    server_name _;
    location /$ENV_ID/ {
        proxy_pass http://$ENV_ID/;
        proxy_set_header Host \$host;
        proxy_set_header X-Env-ID $ENV_ID;
    }
}
EOF

# Reload Nginx
docker exec sandbox-nginx nginx -s reload 2>/dev/null || true

# 4. Start log shipping (Approach A)
docker logs -f "$CONTAINER" >> "$LOG_DIR/app.log" 2>&1 &
LOG_PID=$!
echo "$LOG_PID" > "$LOG_DIR/log_pid"

# 5. Write state file atomically
CREATED_AT=$(date -u +%s)
EXPIRES_AT=$((CREATED_AT + TTL))
TMP=$(mktemp)
cat > "$TMP" <<EOF
{
  "id": "$ENV_ID",
  "name": "$NAME",
  "container": "$CONTAINER",
  "network": "$NETWORK",
  "port": $PORT,
  "created_at": $CREATED_AT,
  "expires_at": $EXPIRES_AT,
  "ttl": $TTL,
  "status": "running"
}
EOF
mv "$TMP" "$STATE_FILE"

echo ""
echo "✅ Environment ready!"
echo "   ID:      $ENV_ID"
echo "   Name:    $NAME"
echo "   URL:     http://localhost/$ENV_ID/"
echo "   Direct:  http://localhost:$PORT/"
echo "   TTL:     ${TTL}s (expires $(date -u -d "@$EXPIRES_AT" +%FT%TZ 2>/dev/null || date -u -r "$EXPIRES_AT" +%FT%TZ))"
echo ""
