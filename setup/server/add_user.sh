#!/usr/bin/env bash
# =============================================================================
# add_user.sh — Admin script to provision a new Qlik MCP user (central server)
# =============================================================================
# Usage:
#   bash setup/server/add_user.sh <username> <email> <port>
#
# Example:
#   bash setup/server/add_user.sh alice alice@ispot.tv 8001
#
# This script:
#   1. Creates users/<username>.env from the template
#   2. Prints the docker-compose.yml block to add manually
#   3. Prints the nginx.conf location block to add manually
#   4. Reminds admin to restart services
# =============================================================================

set -euo pipefail

USERNAME="${1:-}"
EMAIL="${2:-}"
PORT="${3:-}"

if [[ -z "$USERNAME" || -z "$EMAIL" || -z "$PORT" ]]; then
    echo "Usage: bash add_user.sh <username> <email> <port>"
    echo "Example: bash add_user.sh alice alice@ispot.tv 8001"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USERS_DIR="$SCRIPT_DIR/users"
ENV_FILE="$USERS_DIR/$USERNAME.env"

mkdir -p "$USERS_DIR"

# ── 1. Create env file ────────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    echo "⚠  $ENV_FILE already exists — not overwriting"
else
    sed "s/firstname.lastname@ispot.tv/$EMAIL/" "$USERS_DIR/template.env" > "$ENV_FILE"
    echo "✓  Created $ENV_FILE"
    echo "   → Edit it to set the correct QLIK_USER_ID and cert paths"
fi

# ── 2. docker-compose.yml block ───────────────────────────────────────────────
echo ""
echo "── Add to docker-compose.yml ────────────────────────────────────────────"
cat <<EOF

  qlik-mcp-$USERNAME:
    image: ghcr.io/open-webui/mcpo:latest
    command: ["--port", "$PORT", "--", "python", "-m", "qlik_sense_mcp_server.server"]
    env_file: ./users/$USERNAME.env
    ports:
      - "$PORT:$PORT"
    volumes:
      - ./certs:/certs:ro
    restart: unless-stopped
EOF

# ── 3. nginx location block ───────────────────────────────────────────────────
echo ""
echo "── Add to nginx.conf (inside the server {} block) ───────────────────────"
cat <<EOF

        location /qlik-mcp/$USERNAME/ {
            limit_req zone=qlik_mcp burst=20 nodelay;
            proxy_pass http://localhost:$PORT/;
            proxy_http_version 1.1;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_set_header Connection '';
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 300s;
        }
EOF

# ── 4. Remind admin ───────────────────────────────────────────────────────────
echo ""
echo "── Next steps ───────────────────────────────────────────────────────────"
echo "  1. Edit $ENV_FILE with correct credentials"
echo "  2. Add the docker-compose.yml block above to docker-compose.yml"
echo "  3. Add the nginx location block above to nginx.conf"
echo "  4. Restart services:"
echo "       docker compose up -d qlik-mcp-$USERNAME"
echo "       docker compose exec nginx nginx -s reload"
echo ""
echo "  User endpoint: https://qlik-mcp.ispot.tv/qlik-mcp/$USERNAME/"
echo ""
echo "  Share with $USERNAME:"
echo "    - Their endpoint URL above"
echo "    - Their GEMINI_API_KEY (they set this in their local Gemini agent config)"
echo "    - Connection type: SSE (not stdio)"
echo ""
