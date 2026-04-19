#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_DIR/.env"
LOG_DIR="$REPO_DIR/logs/deploy"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/update-$TIMESTAMP.log"

init_logging() {
    if [ "${VOLTAGE_LOGGING_INITIALIZED:-0}" = "1" ]; then
        return
    fi

    mkdir -p "$LOG_DIR"
    touch "$LOG_FILE"
    export VOLTAGE_LOGGING_INITIALIZED=1
    exec > >(tee -a "$LOG_FILE") 2>&1
}

init_logging

trap 'status=$?; echo ""; if [ "$status" -eq 0 ]; then echo "Log saved to: $LOG_FILE"; else echo "Script failed with exit code $status"; echo "Full log: $LOG_FILE"; fi' EXIT

if [ ! -f "$ENV_FILE" ]; then
    echo ".env file is missing. Run scripts/deploy.sh first."
    exit 1
fi

get_var() {
    grep -E "^$1=" "$ENV_FILE" | head -n 1 | cut -d= -f2- || true
}

APP_PORT="$(get_var APP_PORT)"
APP_PORT="${APP_PORT:-8088}"
HEALTH_URL="http://127.0.0.1:${APP_PORT}/health"

cd "$REPO_DIR"

echo "Updating VOLTAGE deployment"
echo "Log file: $LOG_FILE"
echo "Stopping services..."
docker compose down

echo "Rebuilding images..."
docker compose build --parallel --no-cache

echo "Starting services..."
docker compose up -d --remove-orphans

echo "Waiting for application health at $HEALTH_URL ..."
for i in $(seq 1 20); do
    if curl -fsS "$HEALTH_URL" >/dev/null; then
        echo "Update complete and healthy."
        echo "Full log: $LOG_FILE"
        exit 0
    fi
    sleep 3
done

echo "Health check failed."
docker compose ps
docker compose logs backend nginx cloudflared --tail 50
exit 1
