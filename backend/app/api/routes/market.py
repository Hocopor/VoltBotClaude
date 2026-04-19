"""
Market Routes — Pairs, OHLCV, Orderbook, Ticker data
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.bybit_service import bybit_service

router = APIRouter()


@router.get("/pairs/spot")
async def get_spot_pairs():
    """Get all available spot USDT pairs from Bybit."""
    try:
        pairs = await bybit_service.get_spot_pairs()
        return {"pairs": pairs, "count": len(pairs)}
    except Exception as e:
        raise HTTPException(503, f"Failed to fetch spot pairs: {e}")


@router.get("/pairs/futures")
async def get_futures_pairs():
    """Get all available futures USDT pairs from Bybit."""
    try:
        pairs = await bybit_service.get_futures_pairs()
        return {"pairs": pairs, "count": len(pairs)}
    except Exception as e:
        raise HTTPException(503, f"Failed to fetch futures pairs: {e}")


@router.get("/klines/{symbol}")
async def get_klines(
    symbol: str,
    interval: str = "240",
    category: str = "spot",
    limit: int = Query(200, le=1000),
):
    """Get OHLCV klines for charting."""
    try:
        candles = await bybit_service.get_klines(symbol, interval, category, limit)
        return {"candles": candles, "symbol": symbol, "interval": interval}
    except Exception as e:
        raise HTTPException(503, f"Failed to fetch klines: {e}")


@router.get("/orderbook/{symbol}")
async def get_orderbook(
    symbol: str,
    category: str = "spot",
    limit: int = Query(50, le=200),
):
    """Get current orderbook."""
    try:
        return await bybit_service.get_orderbook(symbol, category, limit)
    except Exception as e:
        raise HTTPException(503, f"Failed to fetch orderbook: {e}")


@router.get("/ticker/{symbol}")
async def get_ticker(symbol: str, category: str = "spot"):
    """Get current ticker info."""
    try:
        return await bybit_service.get_ticker_info(symbol, category)
    except Exception as e:
        raise HTTPException(503, f"Failed to fetch ticker: {e}")


@router.get("/fear-greed")
async def get_fear_greed():
    """Get current Fear & Greed index."""
    try:
        value = await bybit_service.get_fear_greed_index()
        if value <= 25:
            zone = "extreme_fear"
        elif value <= 45:
            zone = "fear"
        elif value <= 55:
            zone = "neutral"
        elif value <= 75:
            zone = "greed"
        else:
            zone = "extreme_greed"
        return {"value": value, "zone": zone}
    except Exception as e:
        raise HTTPException(503, str(e))
