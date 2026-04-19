"""
Trades Routes — Open, Closed, Cancelled trades with PnL
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import Trade, TradeStatus, TradingMode, MarketType, PositionSide

router = APIRouter()


def trade_to_dict(t: Trade) -> dict:
    return {
        "id": t.id,
        "mode": t.mode.value,
        "symbol": t.symbol,
        "market_type": t.market_type.value,
        "side": t.side.value,
        "status": t.status.value,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "entry_qty": t.entry_qty,
        "exit_qty": t.exit_qty,
        "stop_loss": t.stop_loss_price,
        "tp1": t.take_profit_1_price,
        "tp2": t.take_profit_2_price,
        "tp3": t.take_profit_3_price,
        "tp1_filled": t.tp1_filled,
        "tp2_filled": t.tp2_filled,
        "tp3_filled": t.tp3_filled,
        "realized_pnl": t.realized_pnl,
        "unrealized_pnl": t.unrealized_pnl,
        "net_pnl": t.net_pnl,
        "fees": t.fees_total,
        "leverage": t.leverage,
        "ai_signal": t.ai_signal.value if t.ai_signal else None,
        "ai_confidence": t.ai_confidence,
        "ai_analysis_entry": t.ai_analysis_entry,
        "ai_analysis_exit": t.ai_analysis_exit,
        "entry_time": t.entry_time.isoformat() if t.entry_time else None,
        "exit_time": t.exit_time.isoformat() if t.exit_time else None,
        "trailing_stop_active": t.trailing_stop_active,
        "trailing_stop_price": t.trailing_stop_price,
        "backtest_session_id": t.backtest_session_id,
    }


@router.get("/")
async def get_trades(
    mode: TradingMode,
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    market_type: Optional[MarketType] = None,
    side: Optional[str] = None,
    backtest_session_id: Optional[int] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Get trades with full filtering."""
    q = select(Trade).where(Trade.mode == mode)
    if status:
        try:
            q = q.where(Trade.status == TradeStatus(status))
        except ValueError:
            pass
    if symbol:
        q = q.where(Trade.symbol == symbol)
    if market_type:
        q = q.where(Trade.market_type == market_type)
    if side:
        try:
            q = q.where(Trade.side == PositionSide(side))
        except ValueError:
            pass
    if backtest_session_id is not None:
        q = q.where(Trade.backtest_session_id == backtest_session_id)

    q = q.order_by(desc(Trade.entry_time)).limit(limit).offset(offset)
    result = await db.execute(q)
    trades = result.scalars().all()
    return {"trades": [trade_to_dict(t) for t in trades], "total": len(trades)}


@router.get("/{trade_id}")
async def get_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
    """Get single trade with full details including orders."""
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        from fastapi import HTTPException
        raise HTTPException(404, "Trade not found")

    from app.models import Order
    orders_result = await db.execute(
        select(Order).where(Order.trade_id == trade_id)
    )
    orders = orders_result.scalars().all()

    data = trade_to_dict(trade)
    data["orders"] = [
        {
            "id": o.id,
            "type": o.order_type.value,
            "side": o.side.value,
            "status": o.status.value,
            "price": o.price,
            "stop_price": o.stop_price,
            "qty": o.qty,
            "filled_qty": o.filled_qty,
            "avg_fill_price": o.avg_fill_price,
            "fee": o.fee,
            "created_at": o.created_at.isoformat(),
            "filled_at": o.filled_at.isoformat() if o.filled_at else None,
        }
        for o in orders
    ]
    return data
