"""
Analytics Routes — Deep trading performance analysis
"""
import math
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from app.database import get_db
from app.models import Trade, JournalEntry, TradingMode, TradeStatus, PositionSide, MarketType

router = APIRouter()


def _safe_number(value: float) -> Optional[float]:
    if not math.isfinite(value):
        return None
    return value


@router.get("/overview/{mode}")
async def analytics_overview(mode: TradingMode, db: AsyncSession = Depends(get_db)):
    """Full analytics overview for a trading mode."""
    result = await db.execute(
        select(Trade).where(
            Trade.mode == mode,
            Trade.status == TradeStatus.CLOSED,
        )
    )
    trades = result.scalars().all()

    if not trades:
        return _empty_overview()

    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl <= 0]
    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))

    # Average win/loss
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0

    # Max drawdown
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x.exit_time or datetime.min.replace(tzinfo=timezone.utc)):
        equity += t.net_pnl
        if equity > peak:
            peak = equity
        dd = (peak - equity) / max(peak, 1) * 100
        if dd > max_dd:
            max_dd = dd

    # Consecutive wins/losses
    results = [1 if t.net_pnl > 0 else -1 for t in sorted(trades, key=lambda x: x.exit_time or datetime.min.replace(tzinfo=timezone.utc))]
    max_consecutive_wins = _max_consecutive(results, 1)
    max_consecutive_losses = _max_consecutive(results, -1)

    # By symbol breakdown
    symbol_stats: dict[str, dict] = {}
    for t in trades:
        s = t.symbol
        if s not in symbol_stats:
            symbol_stats[s] = {"total": 0, "wins": 0, "pnl": 0.0}
        symbol_stats[s]["total"] += 1
        symbol_stats[s]["pnl"] += t.net_pnl
        if t.net_pnl > 0:
            symbol_stats[s]["wins"] += 1

    for s, data in symbol_stats.items():
        data["win_rate"] = round(data["wins"] / data["total"] * 100, 1)
        data["pnl"] = round(data["pnl"], 4)

    # By market type
    spot_trades = [t for t in trades if t.market_type == MarketType.SPOT]
    fut_trades = [t for t in trades if t.market_type == MarketType.FUTURES]

    # Long vs Short breakdown
    longs = [t for t in trades if t.side == PositionSide.LONG]
    shorts = [t for t in trades if t.side == PositionSide.SHORT]

    # Profit factor
    pf = round(gross_profit / gross_loss, 3) if gross_loss > 0 else float("inf")

    # Average hold time
    hold_times = []
    for t in trades:
        if t.entry_time and t.exit_time:
            hold_times.append((t.exit_time - t.entry_time).total_seconds() / 3600)
    avg_hold_hours = round(sum(hold_times) / len(hold_times), 2) if hold_times else 0

    return {
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 2),
        "profit_factor": _safe_number(pf),
        "total_pnl": round(sum(t.net_pnl for t in trades), 4),
        "gross_profit": round(gross_profit, 4),
        "gross_loss": round(gross_loss, 4),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "max_drawdown_pct": round(max_dd, 2),
        "max_consecutive_wins": max_consecutive_wins,
        "max_consecutive_losses": max_consecutive_losses,
        "avg_hold_hours": avg_hold_hours,
        "total_fees": round(sum(t.fees_total for t in trades), 4),
        "best_trade": round(max(t.net_pnl for t in trades), 4) if trades else 0,
        "worst_trade": round(min(t.net_pnl for t in trades), 4) if trades else 0,
        "by_symbol": symbol_stats,
        "spot": {
            "trades": len(spot_trades),
            "pnl": round(sum(t.net_pnl for t in spot_trades), 4),
            "win_rate": round(len([t for t in spot_trades if t.net_pnl > 0]) / max(len(spot_trades), 1) * 100, 1),
        },
        "futures": {
            "trades": len(fut_trades),
            "pnl": round(sum(t.net_pnl for t in fut_trades), 4),
            "win_rate": round(len([t for t in fut_trades if t.net_pnl > 0]) / max(len(fut_trades), 1) * 100, 1),
        },
        "longs": {
            "trades": len(longs),
            "pnl": round(sum(t.net_pnl for t in longs), 4),
            "win_rate": round(len([t for t in longs if t.net_pnl > 0]) / max(len(longs), 1) * 100, 1),
        },
        "shorts": {
            "trades": len(shorts),
            "pnl": round(sum(t.net_pnl for t in shorts), 4),
            "win_rate": round(len([t for t in shorts if t.net_pnl > 0]) / max(len(shorts), 1) * 100, 1),
        },
    }


@router.get("/equity-curve/{mode}")
async def equity_curve(mode: TradingMode, db: AsyncSession = Depends(get_db)):
    """Get equity curve data for charting."""
    result = await db.execute(
        select(Trade).where(
            Trade.mode == mode,
            Trade.status == TradeStatus.CLOSED,
            Trade.exit_time.isnot(None),
        ).order_by(Trade.exit_time)
    )
    trades = result.scalars().all()

    equity = 0.0
    points = [{"time": "start", "equity": 0, "pnl": 0, "symbol": ""}]
    for t in trades:
        equity += t.net_pnl
        points.append({
            "time": t.exit_time.isoformat(),
            "equity": round(equity, 4),
            "pnl": round(t.net_pnl, 4),
            "symbol": t.symbol,
        })
    return {"curve": points}


@router.get("/heatmap/{mode}")
async def pnl_heatmap(mode: TradingMode, db: AsyncSession = Depends(get_db)):
    """Calendar heatmap of daily PnL."""
    result = await db.execute(
        select(Trade).where(
            Trade.mode == mode,
            Trade.status == TradeStatus.CLOSED,
            Trade.exit_time.isnot(None),
        ).order_by(Trade.exit_time)
    )
    trades = result.scalars().all()

    daily: dict[str, float] = {}
    for t in trades:
        day = t.exit_time.strftime("%Y-%m-%d")
        daily[day] = round(daily.get(day, 0) + t.net_pnl, 4)

    return {"heatmap": [{"date": d, "pnl": v} for d, v in sorted(daily.items())]}


@router.get("/voltage-filters/{mode}")
async def voltage_filter_performance(mode: TradingMode, db: AsyncSession = Depends(get_db)):
    """Analyze which VOLTAGE filter combinations worked best."""
    result = await db.execute(
        select(Trade).where(
            Trade.mode == mode,
            Trade.status == TradeStatus.CLOSED,
            Trade.voltage_filters.isnot(None),
        )
    )
    trades = result.scalars().all()

    if not trades:
        return {"data": []}

    # Group by filters_passed count
    by_filters: dict[int, dict] = {}
    for t in trades:
        filters_passed = (t.ai_filters_snapshot or {}).get("filters_passed", 0)
        if filters_passed not in by_filters:
            by_filters[filters_passed] = {"count": 0, "wins": 0, "pnl": 0.0}
        by_filters[filters_passed]["count"] += 1
        by_filters[filters_passed]["pnl"] += t.net_pnl
        if t.net_pnl > 0:
            by_filters[filters_passed]["wins"] += 1

    data = []
    for k, v in sorted(by_filters.items()):
        data.append({
            "filters_passed": k,
            "trades": v["count"],
            "pnl": round(v["pnl"], 4),
            "win_rate": round(v["wins"] / v["count"] * 100, 1),
        })

    return {"data": data}


def _max_consecutive(results: list[int], value: int) -> int:
    max_c = current = 0
    for r in results:
        if r == value:
            current += 1
            max_c = max(max_c, current)
        else:
            current = 0
    return max_c


def _empty_overview() -> dict:
    return {
        "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
        "win_rate": 0, "profit_factor": 0, "total_pnl": 0,
        "gross_profit": 0, "gross_loss": 0, "avg_win": 0, "avg_loss": 0,
        "max_drawdown_pct": 0, "max_consecutive_wins": 0, "max_consecutive_losses": 0,
        "avg_hold_hours": 0, "total_fees": 0, "best_trade": 0, "worst_trade": 0,
        "by_symbol": {}, "spot": {}, "futures": {}, "longs": {}, "shorts": {},
    }
