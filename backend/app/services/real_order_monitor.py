"""
Real Order Monitor
Polls Bybit for order fills and position changes.
Syncs state into DB, triggers journal creation on close,
broadcasts WebSocket events.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import (
    Trade, Order, OrderStatus, OrderType, TradeStatus,
    TradingMode, MarketType, PositionSide
)
from app.services.bybit_service import bybit_service
from app.services.journal_service import journal_service
from app.websocket.manager import manager, Events
from app.database import AsyncSessionLocal


class RealOrderMonitor:
    """
    Monitors real Bybit account for:
    - Order fills (entry, SL, TP)
    - Position changes
    - PnL updates

    Runs as a background task every 10 seconds.
    """

    def __init__(self):
        self._running = False

    async def start(self):
        self._running = True
        logger.info("Real order monitor started")
        while self._running:
            try:
                await self._sync_cycle()
            except Exception as e:
                logger.error(f"Monitor cycle error: {e}", exc_info=True)
            await asyncio.sleep(10)

    def stop(self):
        self._running = False
        logger.info("Real order monitor stopped")

    async def _sync_cycle(self):
        """One sync cycle: fetch open orders + positions from Bybit, update DB."""
        async with AsyncSessionLocal() as db:
            # 1. Sync open orders
            for cat in ["spot", "linear"]:
                try:
                    exchange_orders = await bybit_service.get_open_orders(category=cat)
                    await self._sync_orders(db, exchange_orders, cat)
                except Exception as e:
                    logger.warning(f"Order sync failed ({cat}): {e}")

            # 2. Sync futures positions
            try:
                positions = await bybit_service.get_positions(category="linear")
                await self._sync_positions(db, positions)
            except Exception as e:
                logger.warning(f"Position sync failed: {e}")

            # 3. Check for newly filled/closed orders (via order history)
            for cat in ["spot", "linear"]:
                try:
                    history = await bybit_service.get_order_history(category=cat, limit=20)
                    await self._process_order_history(db, history, cat)
                except Exception as e:
                    logger.warning(f"Order history sync failed ({cat}): {e}")

            await db.commit()

    async def _sync_orders(self, db: AsyncSession, exchange_orders: list, cat: str):
        """Update order statuses from exchange."""
        market = MarketType.SPOT if cat == "spot" else MarketType.FUTURES

        for eo in exchange_orders:
            oid = eo.get("orderId")
            if not oid:
                continue

            result = await db.execute(
                select(Order).where(
                    Order.exchange_order_id == oid,
                    Order.mode == TradingMode.REAL,
                )
            )
            order = result.scalar_one_or_none()
            if not order:
                continue

            # Map Bybit status to our enum
            bybit_status = eo.get("orderStatus", "")
            new_status = self._map_order_status(bybit_status)
            if new_status and order.status != new_status:
                order.status = new_status
                filled_qty = float(eo.get("cumExecQty", 0))
                avg_price = float(eo.get("avgPrice", 0))
                order.filled_qty = filled_qty
                if avg_price > 0:
                    order.avg_fill_price = avg_price

                if new_status == OrderStatus.FILLED:
                    order.filled_at = datetime.now(timezone.utc)
                    await manager.broadcast(Events.ORDER_FILLED, {
                        "order_id": order.id,
                        "symbol": order.symbol,
                        "type": order.order_type.value,
                        "price": avg_price,
                    })

    async def _sync_positions(self, db: AsyncSession, positions: list):
        """Update open trade PnL from live positions."""
        for pos in positions:
            symbol = pos.get("symbol", "")
            if not symbol:
                continue

            size = float(pos.get("size", 0))
            if size == 0:
                continue  # No open position

            unrealized_pnl = float(pos.get("unrealisedPnl", 0))
            mark_price = float(pos.get("markPrice", 0))

            # Find matching open trade in DB
            result = await db.execute(
                select(Trade).where(
                    Trade.mode == TradingMode.REAL,
                    Trade.symbol == symbol,
                    Trade.status == TradeStatus.OPEN,
                    Trade.market_type == MarketType.FUTURES,
                )
            )
            trade = result.scalar_one_or_none()
            if trade:
                trade.unrealized_pnl = unrealized_pnl
                await manager.broadcast(Events.PNL_UPDATE, {
                    "trade_id": trade.id,
                    "symbol": symbol,
                    "unrealized": unrealized_pnl,
                    "mark_price": mark_price,
                })

    async def _process_order_history(self, db: AsyncSession, history: list, cat: str):
        """Process recently filled orders — detect TP/SL fills, close trades."""
        market = MarketType.SPOT if cat == "spot" else MarketType.FUTURES

        for eo in history:
            status = eo.get("orderStatus", "")
            if status not in ("Filled", "PartiallyFilled"):
                continue

            oid = eo.get("orderId")
            result = await db.execute(
                select(Order).where(
                    Order.exchange_order_id == oid,
                    Order.mode == TradingMode.REAL,
                )
            )
            order = result.scalar_one_or_none()
            if not order or order.status == OrderStatus.FILLED:
                continue

            # Mark as filled
            filled_qty = float(eo.get("cumExecQty", 0))
            avg_price = float(eo.get("avgPrice", 0))
            order.status = OrderStatus.FILLED
            order.filled_qty = filled_qty
            order.avg_fill_price = avg_price
            order.filled_at = datetime.now(timezone.utc)
            order.fee = float(eo.get("cumExecFee", 0))

            if not order.trade_id:
                continue

            # Update parent trade
            trade_result = await db.execute(
                select(Trade).where(Trade.id == order.trade_id)
            )
            trade = trade_result.scalar_one_or_none()
            if not trade:
                continue

            if order.order_type == OrderType.TAKE_PROFIT:
                is_long = trade.side == PositionSide.LONG
                pnl = (avg_price - trade.entry_price) * filled_qty * (1 if is_long else -1)
                trade.realized_pnl += pnl
                trade.fees_total += order.fee
                trade.net_pnl = trade.realized_pnl - trade.fees_total
                trade.exit_qty += filled_qty

                # Determine which TP was hit
                tol = trade.entry_price * 0.001
                if trade.take_profit_1_price and abs(avg_price - trade.take_profit_1_price) < tol:
                    trade.tp1_filled = True
                    # Move SL to breakeven
                    trade.stop_loss_price = trade.entry_price
                    try:
                        await bybit_service.set_trading_stop(
                            symbol=trade.symbol,
                            position_idx=1 if is_long else 2,
                            stop_loss=trade.entry_price,
                        )
                    except Exception as e:
                        logger.warning(f"SL move to BE failed: {e}")

                elif trade.take_profit_2_price and abs(avg_price - trade.take_profit_2_price) < tol:
                    trade.tp2_filled = True

                elif trade.take_profit_3_price and abs(avg_price - trade.take_profit_3_price) < tol:
                    trade.tp3_filled = True
                    # Activate trailing stop on remaining
                    try:
                        trail_pct = "1.5"  # 1.5% trailing
                        await bybit_service.set_trading_stop(
                            symbol=trade.symbol,
                            position_idx=1 if is_long else 2,
                            trailing_stop=trail_pct,
                        )
                    except Exception as e:
                        logger.warning(f"Trailing stop activation failed: {e}")

                # Check if fully closed
                if abs(trade.exit_qty - trade.entry_qty) < 1e-8:
                    await self._close_trade(db, trade, avg_price)

            elif order.order_type in (OrderType.STOP_LOSS, OrderType.TRAILING_STOP):
                is_long = trade.side == PositionSide.LONG
                remaining = trade.entry_qty - trade.exit_qty
                pnl = (avg_price - trade.entry_price) * remaining * (1 if is_long else -1)
                trade.realized_pnl += pnl
                trade.fees_total += order.fee
                trade.net_pnl = trade.realized_pnl - trade.fees_total
                await self._close_trade(db, trade, avg_price)
                logger.info(f"SL triggered for trade {trade.id} @ {avg_price} | PnL: {trade.net_pnl:.4f}")

    async def _close_trade(self, db: AsyncSession, trade: Trade, exit_price: float):
        """Mark trade closed and create journal entry."""
        trade.status = TradeStatus.CLOSED
        trade.exit_price = exit_price
        trade.exit_time = datetime.now(timezone.utc)
        trade.unrealized_pnl = 0.0

        # Create journal entry
        entry = await journal_service.create_or_update(db, trade)
        await db.flush()

        # Broadcast
        await manager.broadcast(Events.TRADE_CLOSED, {
            "trade_id": trade.id,
            "symbol": trade.symbol,
            "net_pnl": trade.net_pnl,
            "mode": trade.mode.value,
        })

        # Schedule AI analysis
        if entry.id:
            asyncio.create_task(
                journal_service.trigger_ai_analysis_background(entry.id)
            )

    def _map_order_status(self, bybit_status: str) -> Optional[OrderStatus]:
        mapping = {
            "New": OrderStatus.OPEN,
            "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
            "Filled": OrderStatus.FILLED,
            "Cancelled": OrderStatus.CANCELLED,
            "Rejected": OrderStatus.REJECTED,
            "Triggered": OrderStatus.TRIGGERED,
            "Deactivated": OrderStatus.CANCELLED,
            "Untriggered": OrderStatus.OPEN,
        }
        return mapping.get(bybit_status)


real_order_monitor = RealOrderMonitor()
