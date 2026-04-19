# ⚡ VOLTAGE — AI Crypto Trading Bot

> Automated crypto trading system powered by DeepSeek AI and the VOLTAGE strategy.  
> Supports Bybit Mainnet · Spot Long · Futures Long/Short · Paper Trading · Backtesting

---

## Architecture

```
voltage-bot/
├── backend/              Python 3.12 · FastAPI · SQLAlchemy · asyncpg
│   └── app/
│       ├── api/routes/   REST API endpoints (9 modules)
│       ├── models/       SQLAlchemy ORM models
│       ├── services/
│       │   ├── strategy/voltage_strategy.py   ← VOLTAGE 6-filter engine
│       │   ├── ai_service.py                  ← DeepSeek integration
│       │   ├── bybit_service.py               ← Bybit API wrapper
│       │   ├── trading_engine.py              ← Main orchestrator
│       │   ├── paper_trading.py               ← Paper simulation
│       │   ├── backtest_engine.py             ← Historical backtest
│       │   ├── real_order_monitor.py          ← Live order sync
│       │   └── journal_service.py             ← Auto journal creation
│       └── websocket/    Real-time WebSocket events
├── frontend/             React 18 · TypeScript · Vite · Tailwind CSS
│   └── src/
│       ├── pages/        Dashboard · Journal · Analytics · Orders
│       │                 Trades · Backtest · Settings
│       ├── components/   TradingChart · PositionsTable · AISignalPanel
│       └── hooks/        useWebSocket (real-time updates)
├── nginx/                Reverse proxy config
├── scripts/              deploy.sh · update.sh
├── docker-compose.yml    Full prod stack
└── .env.example          Config template
```

---

## Quick Start (VPS Ubuntu 24)

### 1. Clone & Configure

```bash
git clone <your-repo> voltage-bot
cd voltage-bot

# Copy and fill in your credentials
cp .env.example .env
nano .env
```

### 2. Fill `.env`

```env
# Required — generate strong random values:
POSTGRES_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-password>
SECRET_KEY=<32+-char-random-string>

# Bybit Mainnet API
BYBIT_API_KEY=your_key
BYBIT_API_SECRET=your_secret

# DeepSeek AI
DEEPSEEK_API_KEY=sk-...

# Cloudflare Tunnel (for remote access via your domain)
CLOUDFLARE_TUNNEL_TOKEN=your_tunnel_token

# Your public domain
ALLOWED_ORIGINS=https://trading.yourdomain.com
```

### 3. Deploy

```bash
chmod +x scripts/deploy.sh
sudo bash scripts/deploy.sh
```

The script will:
- Install Docker if needed
- Build all containers
- Start the full stack
- Run DB migrations
- Configure Cloudflare Tunnel

---

## Cloudflare Tunnel Setup

1. Go to **Cloudflare Zero Trust → Networks → Tunnels**
2. Create a tunnel → copy the token
3. Set in `.env`: `CLOUDFLARE_TUNNEL_TOKEN=your_token`
4. In Cloudflare dashboard, add a Public Hostname:
   - Subdomain: `trading` (or whatever you prefer)
   - Service: `http://localhost:80`

---

## VOLTAGE Strategy — 6 Filters

The bot strictly follows the VOLTAGE strategy. All 6 filters must pass for a trade:

| Filter | Name | Key Indicators |
|--------|------|----------------|
| 1 | BTC Dominance & Sentiment | BTC.D, Fear & Greed, Total MCAP |
| 2 | Multi-Timeframe Analysis | EMA21/55 on 1W/1D/4H/1H, Ichimoku |
| 3 | Crypto Indicators | RSI(14) 35-65, Stochastic(5,3,3), Williams%R, ATR |
| 4 | **Volume** *(most important)* | OBV, Volume Delta, VPVR, Accumulation |
| 5 | Price Action | Engulfing, Pin Bar, Liquidity Grab, Consolidation |
| 6 | Liquidity & Clusters | Order book depth, cluster analysis |

**Risk Management (fixed rules):**
- Position size: 1-3% of deposit per trade
- TP1 = 1.5R → close 40%, move SL to breakeven
- TP2 = 3.0R → close 30%
- TP3 = 5.0R → close 30% + activate trailing stop
- SL for alts: 8-12% · SL for BTC/ETH: 5-8%

---

## Trading Modes

| Mode | Description | Data |
|------|-------------|------|
| **Real** | Live trading on Bybit Mainnet | Real balance, real orders |
| **Paper** | Simulated trading at live prices | Configurable virtual balance |
| **Backtest** | Historical walk-forward simulation | Bybit historical OHLCV |

Each mode is completely independent — dashboard, journal, analytics, orders, trades all show only the selected mode's data.

---

## API Endpoints

| Prefix | Description |
|--------|-------------|
| `/auth/` | Codex OAuth, API key management |
| `/trading/` | Engine control, positions, PnL |
| `/orders/` | All order types (open/filled/cancelled/SL/TP) |
| `/trades/` | Full trade lifecycle with PnL |
| `/journal/` | Trader diary, AI analysis, PnL calendar |
| `/analytics/` | Equity curve, heatmap, filter performance |
| `/settings/` | Per-mode configuration |
| `/backtest/` | Session management, results |
| `/market/` | Pairs, klines, orderbook, Fear&Greed |
| `/ws` | WebSocket (real-time events) |

---

## WebSocket Events

```
trade.opened       → New position opened
trade.closed       → Position closed (with PnL)
order.filled       → Order execution
pnl.update         → Real-time PnL for open positions
ai.signal          → New AI analysis result
balance.update     → Balance change
backtest.progress  → Backtest % complete
backtest.complete  → Backtest finished
engine.status      → Engine started/stopped
```

---

## Operations

```bash
# View logs
docker compose logs -f backend

# Restart backend only
docker compose restart backend

# Stop everything
docker compose down

# Update to latest
bash scripts/update.sh

# Database shell
docker compose exec postgres psql -U voltage voltage

# Backup database
docker compose exec postgres pg_dump -U voltage voltage > backup_$(date +%Y%m%d).sql
```

---

## Security Notes

- API docs (`/docs`) are disabled in production (`DEBUG=false`)
- All secrets are in `.env` — never commit it to git
- Bybit API keys should have **trading permissions only** — no withdrawal
- The app runs as a non-root user inside Docker

---

## Support

Built for personal use on VPS Ubuntu 24 with Cloudflare Tunnel access.
