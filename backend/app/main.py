"""
VOLTAGE Trading Bot — FastAPI Application (Production)
"""
import uuid
import asyncio
from contextlib import asynccontextmanager
from loguru import logger
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.database import init_db, AsyncSessionLocal
from app.security import get_authenticated_login_from_request, get_authenticated_login_from_websocket
from app.websocket.manager import manager
from app.models import BotSettings, TradingMode

logger.remove()
logger.add(sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    level=settings.LOG_LEVEL)
logger.add("logs/voltage_{time:YYYY-MM-DD}.log", rotation="00:00", retention="30 days", level="DEBUG")

_bg_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("═══ VOLTAGE Bot Starting ═══")
    await init_db()
    logger.info("✓ Database initialized")

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        for mode in TradingMode:
            result = await db.execute(select(BotSettings).where(BotSettings.mode == mode))
            if not result.scalar_one_or_none():
                db.add(BotSettings(mode=mode))
        await db.commit()
    logger.info("✓ Default settings ensured")

    from app.services.real_order_monitor import real_order_monitor
    _bg_tasks.append(asyncio.create_task(real_order_monitor.start()))
    logger.info("✓ Real order monitor started")

    from app.services.trading_engine import engine as trading_engine
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(BotSettings))
        for s in result.scalars().all():
            if s.auto_trading_enabled:
                _bg_tasks.append(asyncio.create_task(trading_engine.start(s.mode)))
                logger.info(f"✓ Resumed engine: {s.mode.value}")

    logger.info("═══ VOLTAGE Bot Ready ═══")
    yield

    logger.info("Shutting down...")
    real_order_monitor.stop()
    await trading_engine.stop()
    for t in _bg_tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    logger.info("Clean shutdown complete")


app = FastAPI(
    title="VOLTAGE Trading Bot API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


PUBLIC_HTTP_PATHS = {
    "/health",
    "/auth/login",
    "/auth/session",
}


@app.middleware("http")
async def auth_guard(request, call_next):
    path = request.url.path
    if (
        request.method == "OPTIONS"
        or path in PUBLIC_HTTP_PATHS
        or path.startswith("/docs")
        or path.startswith("/openapi")
        or path.startswith("/redoc")
        or path.startswith("/auth/codex/callback")
    ):
        return await call_next(request)

    if not get_authenticated_login_from_request(request):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Authentication required"},
        )

    return await call_next(request)

from app.api.routes import (
    auth, trading, orders, trades, journal, analytics,
    settings as settings_router, backtest, market,
)
app.include_router(auth.router,            prefix="/auth",      tags=["auth"])
app.include_router(trading.router,         prefix="/trading",   tags=["trading"])
app.include_router(orders.router,          prefix="/orders",    tags=["orders"])
app.include_router(trades.router,          prefix="/trades",    tags=["trades"])
app.include_router(journal.router,         prefix="/journal",   tags=["journal"])
app.include_router(analytics.router,       prefix="/analytics", tags=["analytics"])
app.include_router(settings_router.router, prefix="/settings",  tags=["settings"])
app.include_router(backtest.router,        prefix="/backtest",  tags=["backtest"])
app.include_router(market.router,          prefix="/market",    tags=["market"])


@app.websocket("/ws/{client_id}")
async def ws_named(websocket: WebSocket, client_id: str):
    if not get_authenticated_login_from_websocket(websocket):
        await websocket.close(code=1008)
        return
    await manager.connect(websocket, client_id)
    try:
        while True:
            if await websocket.receive_text() == "ping":
                await manager.send(client_id, "pong", {})
    except WebSocketDisconnect:
        await manager.disconnect(client_id)


@app.websocket("/ws")
async def ws_anon(websocket: WebSocket):
    if not get_authenticated_login_from_websocket(websocket):
        await websocket.close(code=1008)
        return
    cid = str(uuid.uuid4())
    await manager.connect(websocket, cid)
    try:
        while True:
            if await websocket.receive_text() == "ping":
                await manager.send(cid, "pong", {})
    except WebSocketDisconnect:
        await manager.disconnect(cid)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "VOLTAGE Bot", "version": "1.0.0"}
