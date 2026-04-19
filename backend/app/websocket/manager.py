"""
WebSocket Manager
Real-time communication: trades, orders, PnL, signals, AI analysis.
"""
from __future__ import annotations

import json
import asyncio
from typing import Any
from datetime import datetime
from loguru import logger
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, client_id: str):
        await ws.accept()
        async with self._lock:
            self.active[client_id] = ws
        logger.info(f"WS client connected: {client_id} (total: {len(self.active)})")

    async def disconnect(self, client_id: str):
        async with self._lock:
            self.active.pop(client_id, None)
        logger.info(f"WS client disconnected: {client_id}")

    async def broadcast(self, event: str, data: Any):
        """Send event to all connected clients."""
        message = json.dumps({"event": event, "data": data, "ts": datetime.utcnow().isoformat()})
        dead = []
        for cid, ws in list(self.active.items()):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(cid)
        for cid in dead:
            await self.disconnect(cid)

    async def send(self, client_id: str, event: str, data: Any):
        """Send event to specific client."""
        ws = self.active.get(client_id)
        if ws:
            try:
                await ws.send_text(json.dumps({
                    "event": event,
                    "data": data,
                    "ts": datetime.utcnow().isoformat(),
                }))
            except Exception:
                await self.disconnect(client_id)


# Global events broadcasted to frontend
class Events:
    TRADE_OPENED = "trade.opened"
    TRADE_UPDATED = "trade.updated"
    TRADE_CLOSED = "trade.closed"
    ORDER_PLACED = "order.placed"
    ORDER_FILLED = "order.filled"
    ORDER_CANCELLED = "order.cancelled"
    PNL_UPDATE = "pnl.update"
    AI_SIGNAL = "ai.signal"
    BACKTEST_PROGRESS = "backtest.progress"
    BACKTEST_COMPLETE = "backtest.complete"
    BALANCE_UPDATE = "balance.update"
    PRICE_UPDATE = "price.update"
    ENGINE_STATUS = "engine.status"


manager = ConnectionManager()
