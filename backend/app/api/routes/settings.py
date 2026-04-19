"""
Settings Routes — Bot configuration
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import BotSettings, TradingMode

router = APIRouter()


class SettingsUpdate(BaseModel):
    spot_pairs: Optional[list[str]] = None
    futures_pairs: Optional[list[str]] = None
    spot_enabled: Optional[bool] = None
    futures_enabled: Optional[bool] = None
    spot_allocated_balance: Optional[float] = None
    futures_allocated_balance: Optional[float] = None
    paper_initial_balance_spot: Optional[float] = None
    paper_initial_balance_futures: Optional[float] = None
    backtest_initial_balance_spot: Optional[float] = None
    backtest_initial_balance_futures: Optional[float] = None
    risk_per_trade_pct: Optional[float] = None
    max_open_positions: Optional[int] = None
    ai_confidence_threshold: Optional[float] = None
    default_leverage: Optional[int] = None
    auto_trading_enabled: Optional[bool] = None
    backtest_start_date: Optional[str] = None
    backtest_end_date: Optional[str] = None


@router.get("/{mode}")
async def get_settings(mode: TradingMode, db: AsyncSession = Depends(get_db)):
    """Get settings for a trading mode."""
    result = await db.execute(
        select(BotSettings).where(BotSettings.mode == mode)
    )
    s = result.scalar_one_or_none()
    if not s:
        # Create default settings
        s = BotSettings(mode=mode)
        db.add(s)
        await db.commit()
        await db.refresh(s)
    return _settings_to_dict(s)


@router.patch("/{mode}")
async def update_settings(
    mode: TradingMode,
    payload: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update settings for a trading mode."""
    result = await db.execute(
        select(BotSettings).where(BotSettings.mode == mode)
    )
    s = result.scalar_one_or_none()
    if not s:
        s = BotSettings(mode=mode)
        db.add(s)

    for field, value in payload.dict(exclude_none=True).items():
        if hasattr(s, field):
            setattr(s, field, value)

    # Reset paper balance when initial is changed
    if payload.paper_initial_balance_spot is not None:
        s.paper_current_balance_spot = payload.paper_initial_balance_spot
    if payload.paper_initial_balance_futures is not None:
        s.paper_current_balance_futures = payload.paper_initial_balance_futures

    await db.commit()
    await db.refresh(s)
    return _settings_to_dict(s)


def _settings_to_dict(s: BotSettings) -> dict:
    return {
        "mode": s.mode.value,
        "spot_pairs": s.spot_pairs or [],
        "futures_pairs": s.futures_pairs or [],
        "spot_enabled": s.spot_enabled,
        "futures_enabled": s.futures_enabled,
        "spot_allocated_balance": s.spot_allocated_balance,
        "futures_allocated_balance": s.futures_allocated_balance,
        "paper_initial_balance_spot": s.paper_initial_balance_spot,
        "paper_initial_balance_futures": s.paper_initial_balance_futures,
        "paper_current_balance_spot": s.paper_current_balance_spot,
        "paper_current_balance_futures": s.paper_current_balance_futures,
        "backtest_initial_balance_spot": s.backtest_initial_balance_spot,
        "backtest_initial_balance_futures": s.backtest_initial_balance_futures,
        "risk_per_trade_pct": s.risk_per_trade_pct,
        "max_open_positions": s.max_open_positions,
        "ai_confidence_threshold": s.ai_confidence_threshold,
        "default_leverage": s.default_leverage,
        "auto_trading_enabled": s.auto_trading_enabled,
        "backtest_start_date": s.backtest_start_date.isoformat() if s.backtest_start_date else None,
        "backtest_end_date": s.backtest_end_date.isoformat() if s.backtest_end_date else None,
    }
