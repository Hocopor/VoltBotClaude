"""
Paper Trading Engine
Simulates all trading operations in-memory and database
without sending real orders to Bybit.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import (
    Trade, Order, BotSettings, OrderStatus, OrderSide, OrderType,
    PositionSide, TradingMode, TradeStatus
)


class PaperTradingEngine:
    """
    Simulates order execution and position management.
    Used for Paper trading and as reference for Backtest engine.
    """

    async def open_position(self, db: AsyncSession, trade: Trade, settings: BotSettings):
        """Simulate opening a position — instant fill at entry price."""
        order = Order(
            mode=trade.mode,
            market_type=trade.market_type,
            exchange_order_id=f"PAPER_{trade.id}_ENTRY",
            symbol=trade.symbol,
            side=OrderSide.BUY if trade.side == PositionSide.LONG else OrderSide.SELL,
            order_type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            position_side=trade.side,
            price=trade.entry_price,
            qty=trade.entry_qty,
            filled_qty=trade.entry_qty,
            avg_fill_price=trade.entry_price,
            fee=trade.entry_price * trade.entry_qty * 0.001,
            filled_at=datetime.now(timezone.utc),
            trade_id=trade.id,
            ai_signal=trade.ai_signal,
            ai_confidence=trade.ai_confidence,
        )
        db.add(order)
        trade.fees_total += order.fee

        # SL order
        if trade.stop_loss_price:
            db.add(Order(
                mode=trade.mode, market_type=trade.market_type,
                exchange_order_id=f"PAPER_{trade.id}_SL",
                symbol=trade.symbol,
                side=OrderSide.SELL if trade.side == PositionSide.LONG else OrderSide.BUY,
                order_type=OrderType.STOP_LOSS, status=OrderStatus.OPEN,
                position_side=trade.side, stop_price=trade.stop_loss_price,
                qty=trade.entry_qty, trade_id=trade.id,
            ))

        # TP orders (40% / 30% / 30%)
        tp_qty_1 = round(trade.entry_qty * 0.4, 8)
        tp_qty_2 = round(trade.entry_qty * 0.3, 8)
        tp_qty_3 = round(trade.entry_qty - tp_qty_1 - tp_qty_2, 8)

        for tp_price, tp_qty, tp_label in [
            (trade.take_profit_1_price, tp_qty_1, "TP1"),
            (trade.take_profit_2_price, tp_qty_2, "TP2"),
            (trade.take_profit_3_price, tp_qty_3, "TP3"),
        ]:
            if tp_price and tp_qty > 0:
                db.add(Order(
                    mode=trade.mode, market_type=trade.market_type,
                    exchange_order_id=f"PAPER_{trade.id}_{tp_label}",
                    symbol=trade.symbol,
                    side=OrderSide.SELL if trade.side == PositionSide.LONG else OrderSide.BUY,
                    order_type=OrderType.TAKE_PROFIT, status=OrderStatus.OPEN,
                    position_side=trade.side, price=tp_price, qty=tp_qty,
                    trade_id=trade.id,
                ))

        logger.info(
            f"Paper position opened: {trade.symbol} {trade.side.value} "
            f"qty={trade.entry_qty} entry={trade.entry_price}"
        )

    async def check_tp_sl(self, db: AsyncSession, trade: Trade, current_price: float):
        """Check if TP or SL has been hit and process fills."""
        if trade.status != TradeStatus.OPEN:
            return

        is_long = trade.side == PositionSide.LONG

        # SL check (highest priority)
        if trade.stop_loss_price:
            sl_hit = (current_price <= trade.stop_loss_price if is_long
                      else current_price >= trade.stop_loss_price)
            if sl_hit:
                await self._fill_stop_loss(db, trade, current_price)
                return

        # Trailing stop
        if trade.trailing_stop_active and trade.trailing_stop_price:
            trail_hit = (current_price <= trade.trailing_stop_price if is_long
                         else current_price >= trade.trailing_stop_price)
            if trail_hit:
                await self._fill_trailing_stop(db, trade, current_price)
                return

        # TP1 → 40%
        if trade.take_profit_1_price and not trade.tp1_filled:
            tp1_hit = (current_price >= trade.take_profit_1_price if is_long
                       else current_price <= trade.take_profit_1_price)
            if tp1_hit:
                await self._fill_take_profit(db, trade, 1, current_price)
                # Move SL to breakeven
                trade.stop_loss_price = trade.entry_price
                logger.info(f"Trade {trade.id}: TP1 @ {current_price} — SL moved to BE")

        # TP2 → 30%
        if trade.take_profit_2_price and trade.tp1_filled and not trade.tp2_filled:
            tp2_hit = (current_price >= trade.take_profit_2_price if is_long
                       else current_price <= trade.take_profit_2_price)
            if tp2_hit:
                await self._fill_take_profit(db, trade, 2, current_price)

        # TP3 → 30% + trailing
        if trade.take_profit_3_price and trade.tp2_filled and not trade.tp3_filled:
            tp3_hit = (current_price >= trade.take_profit_3_price if is_long
                       else current_price <= trade.take_profit_3_price)
            if tp3_hit:
                await self._fill_take_profit(db, trade, 3, current_price)
                trade.trailing_stop_active = True
                trail_offset = abs(trade.entry_price - (trade.stop_loss_price or trade.entry_price)) * 0.5
                trade.trailing_stop_price = (current_price - trail_offset if is_long
                                              else current_price + trail_offset)
                logger.info(f"Trade {trade.id}: TP3 hit — trailing @ {trade.trailing_stop_price:.4f}")

        # Update trailing stop ratchet
        if trade.trailing_stop_active and trade.trailing_stop_price:
            trail_offset = abs(trade.entry_price - (trade.stop_loss_price or trade.entry_price)) * 0.5
            new_trail = (current_price - trail_offset if is_long else current_price + trail_offset)
            if is_long and new_trail > trade.trailing_stop_price:
                trade.trailing_stop_price = new_trail
            elif not is_long and new_trail < trade.trailing_stop_price:
                trade.trailing_stop_price = new_trail

    async def _fill_take_profit(self, db: AsyncSession, trade: Trade, tp_num: int, price: float):
        """Record a TP partial fill."""
        qty_map = {1: trade.entry_qty * 0.4, 2: trade.entry_qty * 0.3, 3: trade.entry_qty * 0.3}
        fill_qty = round(qty_map[tp_num], 8)
        fee = price * fill_qty * 0.001
        is_long = trade.side == PositionSide.LONG
        pnl = (price - trade.entry_price) * fill_qty * (1 if is_long else -1)

        trade.realized_pnl += pnl
        trade.fees_total += fee
        trade.net_pnl = trade.realized_pnl - trade.fees_total
        trade.exit_qty += fill_qty
        setattr(trade, f"tp{tp_num}_filled", True)

        # Mark TP order filled
        r = await db.execute(select(Order).where(
            Order.trade_id == trade.id,
            Order.exchange_order_id == f"PAPER_{trade.id}_TP{tp_num}",
        ))
        o = r.scalar_one_or_none()
        if o:
            o.status = OrderStatus.FILLED
            o.filled_qty = fill_qty
            o.avg_fill_price = price
            o.filled_at = datetime.now(timezone.utc)
            o.fee = fee

        # Close trade if all TPs done (TP3 is the last)
        if tp_num == 3 or (trade.tp1_filled and trade.tp2_filled and trade.tp3_filled):
            await self._close_trade(db, trade, price)

    async def _fill_stop_loss(self, db: AsyncSession, trade: Trade, price: float):
        """Record a SL fill and close the trade."""
        remaining_qty = round(trade.entry_qty - trade.exit_qty, 8)
        fee = price * remaining_qty * 0.001
        is_long = trade.side == PositionSide.LONG
        pnl = (price - trade.entry_price) * remaining_qty * (1 if is_long else -1)

        trade.realized_pnl += pnl
        trade.fees_total += fee
        trade.net_pnl = trade.realized_pnl - trade.fees_total

        r = await db.execute(select(Order).where(
            Order.trade_id == trade.id,
            Order.order_type == OrderType.STOP_LOSS,
        ))
        sl = r.scalar_one_or_none()
        if sl:
            sl.status = OrderStatus.TRIGGERED
            sl.filled_qty = remaining_qty
            sl.avg_fill_price = price
            sl.filled_at = datetime.now(timezone.utc)

        await self._cancel_remaining_orders(db, trade.id)
        await self._close_trade(db, trade, price)
        logger.info(f"Trade {trade.id}: SL @ {price} | PnL: {trade.net_pnl:.4f}")

    async def _fill_trailing_stop(self, db: AsyncSession, trade: Trade, price: float):
        """Record trailing stop fill."""
        remaining_qty = round(trade.entry_qty - trade.exit_qty, 8)
        fee = price * remaining_qty * 0.001
        is_long = trade.side == PositionSide.LONG
        pnl = (price - trade.entry_price) * remaining_qty * (1 if is_long else -1)

        trade.realized_pnl += pnl
        trade.fees_total += fee
        trade.net_pnl = trade.realized_pnl - trade.fees_total
        trade.trailing_stop_active = False

        await self._cancel_remaining_orders(db, trade.id)
        await self._close_trade(db, trade, price)
        logger.info(f"Trade {trade.id}: Trailing stop @ {price} | PnL: {trade.net_pnl:.4f}")

    async def _cancel_remaining_orders(self, db: AsyncSession, trade_id: int):
        """Cancel all still-open orders for a trade."""
        r = await db.execute(select(Order).where(
            Order.trade_id == trade_id,
            Order.status == OrderStatus.OPEN,
        ))
        for o in r.scalars().all():
            o.status = OrderStatus.CANCELLED

    async def _close_trade(self, db: AsyncSession, trade: Trade, exit_price: float):
        """
        Mark trade CLOSED, then create/update journal entry and
        schedule AI post-trade analysis in background.
        """
        trade.status = TradeStatus.CLOSED
        trade.exit_price = exit_price
        trade.exit_time = datetime.now(timezone.utc)
        trade.unrealized_pnl = 0.0

        # Flush so trade.id is available for journal FK
        await db.flush()

        # Create journal entry (paper + backtest modes)
        try:
            from app.services.journal_service import journal_service
            from app.websocket.manager import manager, Events

            entry = await journal_service.create_or_update(db, trade)
            await db.flush()

            # Broadcast closure event
            await manager.broadcast(Events.TRADE_CLOSED, {
                "trade_id": trade.id,
                "symbol": trade.symbol,
                "net_pnl": round(trade.net_pnl, 4),
                "mode": trade.mode.value,
            })

            # Schedule AI analysis without blocking
            if entry.id:
                asyncio.create_task(
                    journal_service.trigger_ai_analysis_background(entry.id)
                )
        except Exception as e:
            logger.error(f"Journal creation failed for trade {trade.id}: {e}")
