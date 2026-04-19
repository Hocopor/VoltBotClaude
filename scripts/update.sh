#!/bin/bash
# VOLTAGE Bot — Update & Redeploy
set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

echo "⚡ VOLTAGE Bot — Update"
echo "Stopping services..."
docker compose down

echo "Rebuilding images..."
docker compose build --parallel --no-cache

echo "Starting services..."
docker compose up -d

echo "Waiting for health..."
sleep 8
if curl -sf http://localhost/health &>/dev/null; then
    echo "✅ Update complete and healthy"
else
    echo "❌ Health check failed — checking logs..."
    docker compose logs backend --tail 50
fi
