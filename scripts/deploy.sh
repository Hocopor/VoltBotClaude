#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_DIR/.env"

echo ""
echo "VOLTAGE Trading Bot deployment"
echo "================================"
echo ""

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found. Installing..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin not found. Installing..."
    apt-get update -q
    apt-get install -y docker-compose-plugin
fi

if [ ! -f "$ENV_FILE" ]; then
    echo ".env file not found. Creating from template..."
    cp "$REPO_DIR/.env.example" "$ENV_FILE"
    echo "Edit $ENV_FILE and re-run the script."
    exit 1
fi

get_var() {
    grep -E "^$1=" "$ENV_FILE" | head -n 1 | cut -d= -f2- || true
}

check_var() {
    local value
    value="$(get_var "$1")"
    if [ -z "$value" ] || [ "$value" = "$2" ]; then
        echo "$1 is not set in .env"
        MISSING=1
    fi
}

MISSING=0
check_var POSTGRES_PASSWORD CHANGE_ME_STRONG_PASSWORD
check_var REDIS_PASSWORD CHANGE_ME_REDIS_PASSWORD
check_var SECRET_KEY CHANGE_ME_SECRET_KEY_MIN_32_CHARS
check_var CLOUDFLARE_TUNNEL_TOKEN your_cloudflare_tunnel_token

if [ "$MISSING" = "1" ]; then
    echo ""
    echo "Please set all required variables in .env and re-run."
    exit 1
fi

APP_PORT="$(get_var APP_PORT)"
APP_PORT="${APP_PORT:-8088}"
HEALTH_URL="http://127.0.0.1:${APP_PORT}/health"

cd "$REPO_DIR"

echo "Building Docker images..."
docker compose build --parallel

echo ""
echo "Starting services..."
docker compose up -d --remove-orphans

echo ""
echo "Waiting for application health at $HEALTH_URL ..."
for i in $(seq 1 20); do
    if curl -fsS "$HEALTH_URL" >/dev/null; then
        echo "Application is healthy."
        break
    fi

    if [ "$i" -eq 20 ]; then
        echo "Health check failed."
        docker compose ps
        docker compose logs backend nginx cloudflared --tail 50
        exit 1
    fi

    sleep 3
done

echo ""
echo "Service status:"
docker compose ps

echo ""
echo "Deployment completed."
echo "Local origin: $HEALTH_URL"
echo "Cloudflare Tunnel container: voltage_cloudflared"
echo ""
echo "Cloudflare dashboard note:"
echo "Configure the public hostname to route to http://nginx:80"
echo "from inside the tunnel network, not to localhost on the host."
echo ""
