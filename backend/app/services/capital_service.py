from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BotSettings, MarketType, Trade, TradeStatus, TradingMode


@dataclass
class PaperMarketSnapshot:
    initial: float
    available: float
    equity: float
    closed_pnl: float
    open_realized_net: float
    unrealized: float
    reserved_capital: float


class CapitalService:
    async def compute_paper_snapshot(
        self,
        db: AsyncSession,
        settings: BotSettings,
    ) -> dict[str, PaperMarketSnapshot]:
        result = await db.execute(
            select(Trade).where(Trade.mode == TradingMode.PAPER)
        )
        trades = result.scalars().all()

        snapshots: dict[str, PaperMarketSnapshot] = {}
        for market_type in (MarketType.SPOT, MarketType.FUTURES):
            market_trades = [t for t in trades if t.market_type == market_type]
            closed = [t for t in market_trades if t.status == TradeStatus.CLOSED]
            open_trades = [t for t in market_trades if t.status == TradeStatus.OPEN]

            initial = (
                float(settings.paper_initial_balance_spot)
                if market_type == MarketType.SPOT
                else float(settings.paper_initial_balance_futures)
            )
            closed_pnl = float(sum(t.net_pnl for t in closed))
            open_realized_net = float(sum((t.realized_pnl - t.fees_total) for t in open_trades))
            unrealized = float(sum(t.unrealized_pnl for t in open_trades))

            if market_type == MarketType.SPOT:
                reserved_capital = float(
                    sum(
                        max(t.entry_qty - t.exit_qty, 0.0) * t.entry_price
                        for t in open_trades
                    )
                )
            else:
                reserved_capital = float(
                    sum(
                        (max(t.entry_qty - t.exit_qty, 0.0) * t.entry_price) / max(float(t.leverage or 1), 1.0)
                        for t in open_trades
                    )
                )

            available = initial + closed_pnl + open_realized_net - reserved_capital
            equity = initial + closed_pnl + open_realized_net + unrealized

            snapshots[market_type.value] = PaperMarketSnapshot(
                initial=round(initial, 4),
                available=round(available, 4),
                equity=round(equity, 4),
                closed_pnl=round(closed_pnl, 4),
                open_realized_net=round(open_realized_net, 4),
                unrealized=round(unrealized, 4),
                reserved_capital=round(reserved_capital, 4),
            )

        return snapshots

    async def get_mode_reserved_capital(
        self,
        db: AsyncSession,
        mode: TradingMode,
        market_type: MarketType,
    ) -> float:
        result = await db.execute(
            select(Trade).where(
                Trade.mode == mode,
                Trade.market_type == market_type,
                Trade.status == TradeStatus.OPEN,
            )
        )
        trades = result.scalars().all()
        if market_type == MarketType.SPOT:
            return float(
                sum(max(t.entry_qty - t.exit_qty, 0.0) * t.entry_price for t in trades)
            )
        return float(
            sum(
                (max(t.entry_qty - t.exit_qty, 0.0) * t.entry_price) / max(float(t.leverage or 1), 1.0)
                for t in trades
            )
        )


capital_service = CapitalService()
