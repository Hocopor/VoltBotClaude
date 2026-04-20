"""
Journal Routes — Trader's Diary (CScalp-style)
"""
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, delete, case

from app.database import get_db
from app.models import JournalEntry, Trade, TradeStatus, TradingMode

router = APIRouter()


class NoteUpdate(BaseModel):
    notes: str
    tags: Optional[list[str]] = None


@router.get("/")
async def get_journal(
    mode: TradingMode,
    symbol: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    backtest_session_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """
    Get journal entries — one entry per closed trade.
    Analogous to CScalp journal view.
    """
    q = select(JournalEntry).where(JournalEntry.mode == mode)
    if symbol:
        q = q.where(JournalEntry.symbol == symbol)
    if date_from:
        dt = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
        q = q.where(JournalEntry.entry_time >= dt)
    if date_to:
        dt = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
        q = q.where(JournalEntry.entry_time <= dt)
    if backtest_session_id is not None:
        q = q.join(Trade, Trade.id == JournalEntry.trade_id).where(Trade.backtest_session_id == backtest_session_id)

    q = q.order_by(desc(JournalEntry.entry_time)).limit(limit).offset(offset)
    result = await db.execute(q)
    entries = result.scalars().all()

    return {
        "entries": [_entry_to_dict(e) for e in entries],
        "total": len(entries),
    }


@router.get("/entry/{entry_id}")
async def get_journal_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single journal entry with full chart data and AI analysis."""
    result = await db.execute(
        select(JournalEntry).where(JournalEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Journal entry not found")
    return _entry_to_dict(entry, include_chart=True)


@router.get("/by-trade/{trade_id}")
async def get_journal_by_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
    """Get journal entry for a specific trade."""
    result = await db.execute(
        select(JournalEntry).where(JournalEntry.trade_id == trade_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "No journal entry for this trade")
    return _entry_to_dict(entry, include_chart=True)


@router.patch("/entry/{entry_id}/notes")
async def update_notes(
    entry_id: int,
    payload: NoteUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Add/update user notes and tags on a journal entry."""
    result = await db.execute(
        select(JournalEntry).where(JournalEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Not found")
    entry.user_notes = payload.notes
    if payload.tags is not None:
        entry.tags = payload.tags
    await db.commit()
    return {"success": True}


@router.post("/entry/{entry_id}/analyze")
async def request_ai_analysis(
    entry_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger AI post-trade analysis for a journal entry."""
    result = await db.execute(
        select(JournalEntry).where(JournalEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Not found")

    if entry.ai_post_analysis:
        return {"status": "already_analyzed", "analysis": entry.ai_post_analysis}

    background_tasks.add_task(_run_ai_analysis, entry_id)
    return {"status": "analysis_started"}


@router.get("/pnl/daily")
async def daily_pnl(
    mode: TradingMode,
    db: AsyncSession = Depends(get_db),
):
    """Get daily PnL breakdown."""
    result = await db.execute(
        select(
            func.date(JournalEntry.exit_time).label("date"),
            func.sum(JournalEntry.net_pnl).label("pnl"),
            func.count(JournalEntry.id).label("trades"),
        ).where(
            JournalEntry.mode == mode,
            JournalEntry.exit_time.isnot(None),
        ).group_by(
            func.date(JournalEntry.exit_time)
        ).order_by(
            func.date(JournalEntry.exit_time).desc()
        ).limit(90)
    )
    rows = result.all()
    return {
        "daily": [
            {
                "date": str(r.date),
                "pnl": round(float(r.pnl), 4),
                "trades": r.trades,
            }
            for r in rows
        ]
    }


@router.get("/pnl/monthly")
async def monthly_pnl(mode: TradingMode, db: AsyncSession = Depends(get_db)):
    """Get monthly PnL breakdown."""
    month_expr = func.date_trunc("month", JournalEntry.exit_time)
    result = await db.execute(
        select(
            month_expr.label("month_start"),
            func.sum(JournalEntry.net_pnl).label("pnl"),
            func.count(JournalEntry.id).label("trades"),
            func.sum(case((JournalEntry.net_pnl > 0, 1), else_=0)).label("wins"),
        ).where(
            JournalEntry.mode == mode,
            JournalEntry.exit_time.isnot(None),
        ).group_by(month_expr).order_by(month_expr)
    )
    rows = result.all()
    return {
        "monthly": [
            {
                "month": r.month_start.strftime("%Y-%m") if r.month_start else None,
                "pnl": round(float(r.pnl), 4),
                "trades": r.trades,
                "wins": r.wins,
                "win_rate": round(r.wins / r.trades * 100, 1) if r.trades > 0 else 0,
            }
            for r in rows
        ]
    }


@router.delete("/clear/{mode}")
async def clear_journal(mode: TradingMode, db: AsyncSession = Depends(get_db)):
    """
    Clear journal history for PAPER or BACKTEST mode.
    REAL mode is protected.
    """
    if mode == TradingMode.REAL:
        raise HTTPException(403, "Cannot clear real trading journal")

    await db.execute(
        delete(JournalEntry).where(JournalEntry.mode == mode)
    )
    # Also clear trades
    await db.execute(
        delete(Trade).where(Trade.mode == mode)
    )
    await db.commit()
    return {"cleared": True, "mode": mode.value}


async def _run_ai_analysis(entry_id: int):
    """Background task: run AI analysis on a completed trade journal entry."""
    from app.database import AsyncSessionLocal
    from app.services.ai_service import ai_service

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
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
                (entry.exit_time - entry.entry_time) if entry.exit_time and entry.entry_time else "N/A"
            ),
            "voltage_snapshot": str(entry.voltage_snapshot or {}),
            "market_context": "{}",
        }

        analysis = await ai_service.post_trade_analysis(trade_data)

        entry.ai_post_analysis = analysis.get("lessons_learned", "")
        entry.ai_lessons = str(analysis.get("improvement_suggestions", ""))
        entry.ai_score = analysis.get("overall_quality_score")
        await db.commit()


def _entry_to_dict(e: JournalEntry, include_chart: bool = False) -> dict:
    data = {
        "id": e.id,
        "trade_id": e.trade_id,
        "mode": e.mode.value,
        "symbol": e.symbol,
        "market_type": e.market_type.value,
        "side": e.side.value,
        "entry_price": e.entry_price,
        "exit_price": e.exit_price,
        "stop_loss": e.stop_loss,
        "take_profits": e.take_profits,
        "entry_time": e.entry_time.isoformat() if e.entry_time else None,
        "exit_time": e.exit_time.isoformat() if e.exit_time else None,
        "realized_pnl": e.realized_pnl,
        "fees": e.fees,
        "net_pnl": e.net_pnl,
        "pnl_percent": e.pnl_percent,
        "ai_post_analysis": e.ai_post_analysis,
        "ai_lessons": e.ai_lessons,
        "ai_score": e.ai_score,
        "voltage_snapshot": e.voltage_snapshot,
        "user_notes": e.user_notes,
        "tags": e.tags,
        "created_at": e.created_at.isoformat(),
    }
    if include_chart:
        data["chart_data"] = e.chart_data
    return data
