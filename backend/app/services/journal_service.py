"""
Journal Service
Automatically creates and updates JournalEntry records
whenever a trade transitions to CLOSED status.
Triggered from paper trading engine and real order monitor.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import (
    Trade, JournalEntry, TradingMode, MarketType, PositionSide, TradeStatus
)
from app.services.bybit_service import bybit_service


class JournalService:
    """Creates, updates, and enriches journal entries for closed trades."""

    async def create_or_update(
        self,
        db: AsyncSession,
        trade: Trade,
        chart_candles: Optional[list] = None,
    ) -> JournalEntry:
        """
        Create a journal entry for a trade (called when trade closes).
        If entry already exists, update it.
        """
        # Check for existing entry
        result = await db.execute(
            select(JournalEntry).where(JournalEntry.trade_id == trade.id)
        )
        entry = result.scalar_one_or_none()

        # Build take_profits dict
        take_profits = {
            "tp1": trade.take_profit_1_price,
            "tp2": trade.take_profit_2_price,
            "tp3": trade.take_profit_3_price,
            "tp1_hit": trade.tp1_filled,
            "tp2_hit": trade.tp2_filled,
            "tp3_hit": trade.tp3_filled,
        }

        # Calculate PnL percent vs allocated capital
        entry_capital = trade.entry_price * trade.entry_qty
        pnl_pct = (trade.net_pnl / entry_capital * 100) if entry_capital > 0 else 0.0

        # Fetch chart data around the trade if not provided
        if chart_candles is None:
            chart_candles = await self._fetch_trade_chart(trade)

        if entry is None:
            entry = JournalEntry(
                trade_id=trade.id,
                mode=trade.mode,
                symbol=trade.symbol,
                market_type=trade.market_type,
                side=trade.side,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                stop_loss=trade.stop_loss_price,
                take_profits=take_profits,
                entry_time=trade.entry_time,
                exit_time=trade.exit_time,
                realized_pnl=trade.realized_pnl,
                fees=trade.fees_total,
                net_pnl=trade.net_pnl,
                pnl_percent=round(pnl_pct, 4),
                voltage_snapshot=trade.voltage_filters,
                chart_data={"candles": chart_candles} if chart_candles else None,
            )
            db.add(entry)
            logger.info(f"Journal entry created for trade {trade.id} ({trade.symbol})")
        else:
            # Update fields that may change (exit price, PnL, etc.)
            entry.exit_price = trade.exit_price
            entry.exit_time = trade.exit_time
            entry.take_profits = take_profits
            entry.realized_pnl = trade.realized_pnl
            entry.fees = trade.fees_total
            entry.net_pnl = trade.net_pnl
            entry.pnl_percent = round(pnl_pct, 4)
            if chart_candles:
                entry.chart_data = {"candles": chart_candles}
            logger.debug(f"Journal entry updated for trade {trade.id}")

        return entry

    async def _fetch_trade_chart(self, trade: Trade) -> list:
        """Fetch 1H candles around the trade period for the journal chart."""
        try:
            cat = "spot" if trade.market_type == MarketType.SPOT else "linear"
            candles = await bybit_service.get_klines(
                symbol=trade.symbol,
                interval="60",  # 1H for journal charts
                category=cat,
                limit=200,
            )
            return candles
        except Exception as e:
            logger.warning(f"Could not fetch chart for journal trade {trade.id}: {e}")
            return []

    async def trigger_ai_analysis_background(self, entry_id: int):
        """Schedule AI post-trade analysis — called after entry is committed."""
        from app.database import AsyncSessionLocal
        from app.services.ai_service import ai_service

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(JournalEntry).where(JournalEntry.id == entry_id)
            )
            entry = result.scalar_one_or_none()
            if not entry or entry.ai_post_analysis:
                return

            trade_data = {
                "symbol": entry.symbol,
                "side": entry.side.value,
                "entry_price": entry.entry_price,
                "exit_price": entry.exit_price or entry.entry_price,
                "entry_time": entry.entry_time.isoformat() if entry.entry_time else "",
                "exit_time": entry.exit_time.isoformat() if entry.exit_time else "",
                "stop_loss": entry.stop_loss or "N/A",
                "tp1": (entry.take_profits or {}).get("tp1", "N/A"),
                "tp2": (entry.take_profits or {}).get("tp2", "N/A"),
                "tp3": (entry.take_profits or {}).get("tp3", "N/A"),
                "tp1_hit": (entry.take_profits or {}).get("tp1_hit", False),
                "tp2_hit": (entry.take_profits or {}).get("tp2_hit", False),
                "tp3_hit": (entry.take_profits or {}).get("tp3_hit", False),
                "pnl": entry.net_pnl,
                "pnl_pct": entry.pnl_percent,
                "duration": str(
                    (entry.exit_time - entry.entry_time)
                    if entry.exit_time and entry.entry_time else "N/A"
                ),
                "voltage_snapshot": str(entry.voltage_snapshot or {}),
                "market_context": "{}",
            }

            analysis = await ai_service.post_trade_analysis(trade_data)

            entry.ai_post_analysis = analysis.get("lessons_learned", "")
            entry.ai_lessons = str(analysis.get("improvement_suggestions", ""))
            entry.ai_score = float(analysis.get("overall_quality_score", 0))
            await db.commit()
            logger.info(f"AI analysis complete for journal entry {entry_id}")


journal_service = JournalService()
