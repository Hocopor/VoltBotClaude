"""
Orders Routes
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import Order, OrderStatus, TradingMode, MarketType

router = APIRouter()


@router.get("/")
async def get_orders(
    mode: TradingMode,
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    market_type: Optional[MarketType] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Get orders with filtering."""
    q = select(Order).where(Order.mode == mode)
    if status:
        try:
            q = q.where(Order.status == OrderStatus(status))
        except ValueError:
            pass
    if symbol:
        q = q.where(Order.symbol == symbol)
    if market_type:
        q = q.where(Order.market_type == market_type)

    q = q.order_by(desc(Order.created_at)).limit(limit).offset(offset)
    result = await db.execute(q)
    orders = result.scalars().all()

    return {
        "orders": [
            {
                "id": o.id,
                "exchange_order_id": o.exchange_order_id,
                "symbol": o.symbol,
                "side": o.side.value,
                "order_type": o.order_type.value,
                "status": o.status.value,
                "position_side": o.position_side.value,
                "price": o.price,
                "stop_price": o.stop_price,
                "qty": o.qty,
                "filled_qty": o.filled_qty,
                "avg_fill_price": o.avg_fill_price,
                "fee": o.fee,
                "fee_currency": o.fee_currency,
                "market_type": o.market_type.value,
                "trade_id": o.trade_id,
                "ai_signal": o.ai_signal.value if o.ai_signal else None,
                "ai_confidence": o.ai_confidence,
                "created_at": o.created_at.isoformat(),
                "filled_at": o.filled_at.isoformat() if o.filled_at else None,
            }
            for o in orders
        ],
        "total": len(orders),
    }
