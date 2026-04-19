#!/bin/bash
# ══════════════════════════════════════════════════════
# VOLTAGE Bot — Production Deployment Script
# Ubuntu 24 LTS + Docker + Cloudflare Tunnel
# ══════════════════════════════════════════════════════
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$REPO_DIR/.env"

echo ""
echo "  ⚡ VOLTAGE Trading Bot — Deployment"
echo "  ═══════════════════════════════════"
echo ""

# ─── Pre-flight checks ───────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "Docker not found. Installing..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi

if ! docker compose version &>/dev/null 2>&1; then
    echo "Docker Compose plugin not found. Installing..."
    apt-get update -q
    apt-get install -y docker-compose-plugin
fi

# ─── Environment setup ───────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env file not found. Creating from template..."
    cp "$REPO_DIR/.env.example" "$ENV_FILE"
    echo ""
    echo "⚠️  Please edit .env with your credentials:"
    echo "    nano $ENV_FILE"
    echo ""
    echo "Required fields:"
    echo "  POSTGRES_PASSWORD, REDIS_PASSWORD, SECRET_KEY"
    echo "  BYBIT_API_KEY, BYBIT_API_SECRET"
    echo "  DEEPSEEK_API_KEY"
    echo "  CLOUDFLARE_TUNNEL_TOKEN (for remote access)"
    echo ""
    exit 1
fi

# Validate required env vars
check_var() {
    local val
    val=$(grep "^$1=" "$ENV_FILE" | cut -d= -f2-)
    if [ -z "$val" ] || [ "$val" = "CHANGE_ME_STRONG_PASSWORD" ] || [ "$val" = "CHANGE_ME_SECRET_KEY_MIN_32_CHARS" ] || [ "$val" = "CHANGE_ME_REDIS_PASSWORD" ]; then
        echo "❌ $1 is not set in .env"
        MISSING=1
    fi
}

MISSING=0
check_var POSTGRES_PASSWORD
check_var REDIS_PASSWORD
check_var SECRET_KEY

if [ "$MISSING" = "1" ]; then
    echo ""
    echo "Please set all required variables in .env and re-run."
    exit 1
fi

# ─── Build & Deploy ───────────────────────────────────
echo "📦 Building Docker images..."
cd "$REPO_DIR"
docker compose build --parallel

echo ""
echo "🚀 Starting services..."
docker compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 8

# Check backend health
for i in {1..20}; do
    if curl -sf http://localhost/health &>/dev/null; then
        echo "✅ Backend is healthy"
        break
    fi
    if [ $i -eq 20 ]; then
        echo "❌ Backend health check failed"
        docker compose logs backend --tail 30
        exit 1
    fi
    sleep 3
done

echo ""
echo "📊 Service status:"
docker compose ps

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ VOLTAGE Bot deployed successfully!"
echo ""
echo "  Local access:  http://localhost"
echo "  API docs:      http://localhost/docs (debug mode only)"
echo ""
echo "  To view logs:  docker compose logs -f backend"
echo "  To stop:       docker compose down"
echo "  To restart:    docker compose restart backend"
echo ""

# ─── Cloudflare Tunnel ───────────────────────────────
CF_TOKEN=$(grep "^CLOUDFLARE_TUNNEL_TOKEN=" "$ENV_FILE" | cut -d= -f2-)
if [ -n "$CF_TOKEN" ] && [ "$CF_TOKEN" != "your_cloudflare_tunnel_token" ]; then
    echo "🌐 Setting up Cloudflare Tunnel..."

    # Install cloudflared if not present
    if ! command -v cloudflared &>/dev/null; then
        curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
        echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared focal main' > /etc/apt/sources.list.d/cloudflared.list
        apt-get update -q && apt-get install -y cloudflared
    fi

    # Run as systemd service
    cloudflared service install "$CF_TOKEN" 2>/dev/null || true
    systemctl start cloudflared 2>/dev/null || true

    echo "  ✅ Cloudflare Tunnel active"
    echo "══════════════════════════════════════════════"
else
    echo "  ℹ️  Set CLOUDFLARE_TUNNEL_TOKEN in .env for remote access"
    echo "══════════════════════════════════════════════"
fi
echo ""
