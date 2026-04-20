"""
Backtest Routes — Historical simulation management
"""
import math
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete, func

from app.database import get_db
from app.models import BacktestSession, MarketType, Trade, Order, TradingMode, JournalEntry
from app.services.backtest_engine import backtest_engine

router = APIRouter()


def _safe_number(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class BacktestCreate(BaseModel):
    name: str
    symbols: list[str]
    market_type: MarketType
    start_date: str   # ISO format
    end_date: str     # ISO format
    initial_balance: float = 10000.0
    risk_per_trade_pct: float = 2.0
    ai_confidence_threshold: float = 0.60
    leverage: int = 1


@router.post("/start")
async def start_backtest(
    payload: BacktestCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start a new backtest session."""
    start = datetime.fromisoformat(payload.start_date)
    end = datetime.fromisoformat(payload.end_date)

    if end <= start:
        raise HTTPException(400, "end_date must be after start_date")
    if len(payload.symbols) == 0:
        raise HTTPException(400, "At least one symbol required")
    if len(payload.symbols) > 20:
        raise HTTPException(400, "Maximum 20 symbols per backtest")

    session = BacktestSession(
        name=payload.name,
        symbols=payload.symbols,
        market_type=payload.market_type,
        start_date=start,
        end_date=end,
        initial_balance=payload.initial_balance,
        status="pending",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    background_tasks.add_task(
        backtest_engine.run_backtest,
        session_id=session.id,
        symbols=payload.symbols,
        market_type=payload.market_type,
        start_date=start,
        end_date=end,
        initial_balance=payload.initial_balance,
        risk_per_trade_pct=payload.risk_per_trade_pct,
        ai_confidence_threshold=payload.ai_confidence_threshold,
        leverage=payload.leverage,
    )

    return {"session_id": session.id, "status": "started", "name": payload.name}


@router.get("/sessions")
async def get_sessions(db: AsyncSession = Depends(get_db)):
    """List all backtest sessions."""
    result = await db.execute(
        select(BacktestSession).order_by(desc(BacktestSession.created_at)).limit(50)
    )
    sessions = result.scalars().all()
    return {
        "sessions": [
            {
                "id": s.id,
                "name": s.name,
                "symbols": s.symbols,
                "market_type": s.market_type.value,
                "start_date": s.start_date.isoformat(),
                "end_date": s.end_date.isoformat(),
                "initial_balance": s.initial_balance,
                "final_balance": s.final_balance,
                "status": s.status,
                "progress": s.progress,
                "total_trades": s.total_trades,
                "win_rate": s.win_rate,
                "profit_factor": _safe_number(s.profit_factor),
                "max_drawdown": s.max_drawdown,
                "total_pnl": s.total_pnl,
                "created_at": s.created_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """Get full backtest session results."""
    result = await db.execute(
        select(BacktestSession).where(BacktestSession.id == session_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Session not found")

    trade_count_result = await db.execute(
        select(func.count(Trade.id)).where(Trade.backtest_session_id == session_id)
    )
    journal_count_result = await db.execute(
        select(func.count(JournalEntry.id))
        .join(Trade, Trade.id == JournalEntry.trade_id)
        .where(Trade.backtest_session_id == session_id)
    )

    return {
        "id": s.id,
        "name": s.name,
        "symbols": s.symbols,
        "market_type": s.market_type.value,
        "start_date": s.start_date.isoformat(),
        "end_date": s.end_date.isoformat(),
        "initial_balance": s.initial_balance,
        "final_balance": s.final_balance,
        "status": s.status,
        "progress": s.progress,
        "error_message": s.error_message,
        "total_trades": s.total_trades,
        "winning_trades": s.winning_trades,
        "losing_trades": s.losing_trades,
        "win_rate": s.win_rate,
        "profit_factor": _safe_number(s.profit_factor),
        "max_drawdown": s.max_drawdown,
        "total_pnl": s.total_pnl,
        "avg_rr": s.avg_rr,
        "artifacts": {
            "persisted_trades": trade_count_result.scalar() or 0,
            "persisted_journal_entries": journal_count_result.scalar() or 0,
        },
        "results_data": s.results_data,
        "created_at": s.created_at.isoformat(),
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
    }


@router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """Stop a running backtest."""
    result = await db.execute(
        select(BacktestSession).where(BacktestSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    if session.status in {"done", "error", "stopped"}:
        return {"stopped": True, "status": session.status}

    session.status = "stopping"
    await db.commit()
    backtest_engine.stop_session(session_id)
    return {"stopped": True, "status": "stopping"}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a backtest session and all its trades."""
    result = await db.execute(
        select(BacktestSession).where(BacktestSession.id == session_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Session not found")

    trade_ids_subquery = select(Trade.id).where(Trade.backtest_session_id == session_id)
    await db.execute(delete(JournalEntry).where(JournalEntry.trade_id.in_(trade_ids_subquery)))
    await db.execute(delete(Trade).where(Trade.backtest_session_id == session_id))
    await db.delete(s)
    await db.commit()
    return {"deleted": True}


@router.delete("/clear-all")
async def clear_all_backtests(db: AsyncSession = Depends(get_db)):
    """Clear ALL backtest sessions and trades."""
    trade_ids_subquery = select(Trade.id).where(Trade.mode == TradingMode.BACKTEST)
    await db.execute(delete(JournalEntry).where(JournalEntry.trade_id.in_(trade_ids_subquery)))
    await db.execute(delete(Trade).where(Trade.mode == TradingMode.BACKTEST))
    await db.execute(delete(BacktestSession))
    await db.commit()
    return {"cleared": True}
