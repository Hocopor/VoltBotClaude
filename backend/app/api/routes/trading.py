"""
Trading Routes — Engine control, AI signals, real-time positions
"""
from datetime import datetime, timezone
from typing import Optional
from loguru import logger
import pandas as pd

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import get_db
from app.models import BotSettings, TradingMode, MarketType, Trade, TradeStatus, AIAnalysisLog, AISignal
from app.services.trading_engine import engine
from app.services.bybit_service import bybit_service
from app.services.capital_service import capital_service
from app.services.ai_service import ai_service
from app.services.strategy.voltage_strategy import VoltageStrategy
from app.websocket.manager import manager, Events

router = APIRouter()


TF_MAP = {
    "1W": "W",
    "1D": "D",
    "4H": "240",
    "1H": "60",
}
MAJORS = {"BTC", "ETH"}


class EngineControl(BaseModel):
    mode: TradingMode
    action: str  # start, stop


class ManualTradeRequest(BaseModel):
    symbol: str
    market_type: MarketType
    side: str  # long, short
    entry_price: Optional[float] = None  # None = market
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    qty: Optional[float] = None
    risk_percent: float = 2.0


class ManualAnalysisRequest(BaseModel):
    mode: TradingMode
    symbol: str
    market_type: MarketType


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


@router.post("/engine")
async def control_engine(
    payload: EngineControl,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start or stop the trading engine for a mode."""
    if payload.mode == TradingMode.BACKTEST:
        raise HTTPException(400, "Backtest uses its own engine. Use the Backtest page instead of Start Engine.")

    if payload.action == "start":
        # Update auto_trading_enabled in settings
        result = await db.execute(
            select(BotSettings).where(BotSettings.mode == payload.mode)
        )
        settings = result.scalar_one_or_none()
        if not settings:
            raise HTTPException(404, f"No settings for mode {payload.mode.value}")

        settings.auto_trading_enabled = True
        await db.commit()

        background_tasks.add_task(engine.start, payload.mode)
        await manager.broadcast(Events.ENGINE_STATUS, {
            "mode": payload.mode.value,
            "status": "started"
        })
        return {"status": "started", "mode": payload.mode.value}

    elif payload.action == "stop":
        result = await db.execute(
            select(BotSettings).where(BotSettings.mode == payload.mode)
        )
        settings = result.scalar_one_or_none()
        if settings:
            settings.auto_trading_enabled = False
            await db.commit()

        await engine.stop(payload.mode)
        await manager.broadcast(Events.ENGINE_STATUS, {
            "mode": payload.mode.value,
            "status": "stopped"
        })
        return {"status": "stopped", "mode": payload.mode.value}

    raise HTTPException(400, "action must be 'start' or 'stop'")


@router.get("/engine/status")
async def engine_status(db: AsyncSession = Depends(get_db)):
    """Get current engine status for all modes."""
    result = await db.execute(select(BotSettings))
    all_settings = result.scalars().all()
    return {
        s.mode.value: {
            "auto_trading": s.auto_trading_enabled,
            "spot_enabled": s.spot_enabled,
            "futures_enabled": s.futures_enabled,
            "running": engine.is_running(s.mode) if s.mode != TradingMode.BACKTEST else False,
        }
        for s in all_settings
    }


@router.get("/balance/{mode}")
async def get_balance(mode: TradingMode, db: AsyncSession = Depends(get_db)):
    """Get balance for a trading mode."""
    result = await db.execute(
        select(BotSettings).where(BotSettings.mode == mode)
    )
    settings = result.scalar_one_or_none()

    if mode == TradingMode.REAL:
        try:
            balances = await bybit_service.get_wallet_balance()
            usdt = balances.get("USDT", {})
            return {
                "mode": mode.value,
                "total_usdt": usdt.get("wallet_balance", 0),
                "available_usdt": usdt.get("available", 0),
                "unrealized_pnl": usdt.get("unrealized_pnl", 0),
                "all_coins": balances,
                "spot_allocated": settings.spot_allocated_balance if settings else None,
                "futures_allocated": settings.futures_allocated_balance if settings else None,
            }
        except Exception as e:
            raise HTTPException(503, f"Failed to fetch Bybit balance: {e}")

    elif mode == TradingMode.PAPER:
        if not settings:
            return {"spot": 10000, "futures": 10000}
        snapshot = await capital_service.compute_paper_snapshot(db, settings)
        spot = snapshot["spot"]
        futures = snapshot["futures"]
        return {
            "mode": "paper",
            "spot_balance": spot.available,
            "spot_equity": spot.equity,
            "spot_initial": settings.paper_initial_balance_spot,
            "spot_reserved": spot.reserved_capital,
            "spot_unrealized": spot.unrealized,
            "futures_balance": futures.available,
            "futures_equity": futures.equity,
            "futures_initial": settings.paper_initial_balance_futures,
            "futures_reserved": futures.reserved_capital,
            "futures_unrealized": futures.unrealized,
            "total_available": spot.available + futures.available,
            "total_equity": spot.equity + futures.equity,
        }

    elif mode == TradingMode.BACKTEST:
        if not settings:
            return {"spot": 10000, "futures": 10000}
        return {
            "mode": "backtest",
            "spot_initial": settings.backtest_initial_balance_spot,
            "futures_initial": settings.backtest_initial_balance_futures,
        }


@router.post("/analyze")
async def run_manual_analysis(
    payload: ManualAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run an on-demand AI market analysis without opening a trade."""
    symbol = payload.symbol.upper()
    cat = "spot" if payload.market_type == MarketType.SPOT else "linear"

    klines: dict[str, pd.DataFrame] = {}
    for tf_name, tf_code in TF_MAP.items():
        raw = await bybit_service.get_klines(symbol, tf_code, category=cat, limit=200)
        if raw:
            df = pd.DataFrame(raw)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            klines[tf_name] = df

    if not all(tf in klines for tf in ["1W", "1D", "4H", "1H"]):
        raise HTTPException(503, f"Insufficient market data to analyze {symbol}")

    try:
        orderbook = await bybit_service.get_orderbook(symbol, category=cat)
    except Exception:
        orderbook = None

    try:
        fear_greed = await bybit_service.get_fear_greed_index()
    except Exception as exc:
        raise HTTPException(503, f"Fear & Greed data unavailable for analysis: {exc}") from exc

    btc_dominance = None
    btc_dominance_source = "unavailable"
    try:
        btc_dominance, btc_dominance_source = await bybit_service.get_btc_dominance_snapshot()
    except Exception as exc:
        btc_dominance_source = "unavailable"

    try:
        ticker = await bybit_service.get_ticker_info(symbol, cat)
    except Exception:
        ticker = {}

    current_price = _safe_float(ticker.get("lastPrice"), float(klines["4H"]["close"].iloc[-1]))
    market_data = {
        "price": current_price,
        "change_24h": _safe_float(ticker.get("price24hPcnt"), 0.0) * 100,
        "volume_24h": _safe_float(ticker.get("volume24h"), _safe_float(klines["1D"]["volume"].iloc[-1] if len(klines["1D"]) else 0)),
    }

    strategy = VoltageStrategy(symbol, is_major=symbol.replace("USDT", "") in MAJORS)
    strategy_signal = strategy.run_all_filters(
        ohlcv_1w=klines["1W"],
        ohlcv_1d=klines["1D"],
        ohlcv_4h=klines["4H"],
        ohlcv_1h=klines["1H"],
        orderbook=orderbook,
        btc_dominance=btc_dominance,
        fear_greed=fear_greed,
    )

    ai_result = await ai_service.analyze_market(
        symbol=symbol,
        market_type=payload.market_type.value,
        voltage_signal=strategy_signal,
        market_data=market_data,
    )

    signal_val = ai_result["signal"]
    ai_signal_enum = AISignal(signal_val) if signal_val in [s.value for s in AISignal] else AISignal.NEUTRAL

    log_entry = AIAnalysisLog(
        mode=payload.mode,
        symbol=symbol,
        market_type=payload.market_type,
        filters_state={
            "filters_passed": strategy_signal.filters_passed,
            "filters_total": strategy_signal.filters_total,
        },
        indicators={
            "rsi": getattr(strategy_signal.filter3, "rsi_14", 50) if strategy_signal.filter3 else 50,
            "macd_hist": getattr(strategy_signal.filter2, "h4_macd_hist", 0) if strategy_signal.filter2 else 0,
            "atr": getattr(strategy_signal.filter3, "atr_14", 0) if strategy_signal.filter3 else 0,
        },
        market_context={
            "price": current_price,
            "fear_greed": fear_greed,
            "btc_dominance": btc_dominance,
            "btc_dominance_source": btc_dominance_source,
            "scenario": ai_result.get("scenario", strategy_signal.market_scenario.value),
            "manual_triggered": True,
        },
        signal=ai_signal_enum,
        confidence=ai_result["confidence"],
        reasoning=ai_result.get("reasoning", "")[:2000],
        suggested_entry=ai_result.get("entry_price"),
        suggested_sl=ai_result.get("stop_loss"),
        suggested_tp1=ai_result.get("take_profit_1"),
        suggested_tp2=ai_result.get("take_profit_2"),
        suggested_tp3=ai_result.get("take_profit_3"),
        trade_opened=False,
        trade_id=None,
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)

    return {
        "id": log_entry.id,
        "mode": payload.mode.value,
        "symbol": symbol,
        "market_type": payload.market_type.value,
        "signal": ai_result["signal"],
        "confidence": ai_result["confidence"],
        "strategy_confidence": ai_result.get("strategy_confidence", strategy_signal.confidence),
        "ai_confidence": ai_result.get("ai_confidence", strategy_signal.confidence),
        "filters_passed": strategy_signal.filters_passed,
        "scenario": ai_result.get("scenario", strategy_signal.market_scenario.value),
        "fear_greed": fear_greed,
        "btc_dominance": btc_dominance,
        "btc_dominance_source": btc_dominance_source,
        "entry_price": ai_result.get("entry_price"),
        "stop_loss": ai_result.get("stop_loss"),
        "take_profit_1": ai_result.get("take_profit_1"),
        "take_profit_2": ai_result.get("take_profit_2"),
        "take_profit_3": ai_result.get("take_profit_3"),
        "reasoning": ai_result.get("reasoning", ""),
        "filters_assessment": ai_result.get("filters_assessment", {}),
        "voltage_filters": ai_result.get("voltage_filters", {}),
        "created_at": log_entry.created_at.isoformat() if log_entry.created_at else None,
    }


@router.post("/manual-trade")
async def place_manual_trade(
    payload: ManualTradeRequest,
    mode: TradingMode,
    db: AsyncSession = Depends(get_db),
):
    """Place a manual trade overriding AI signals."""
    result = await db.execute(
        select(BotSettings).where(BotSettings.mode == mode)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        raise HTTPException(404, "Settings not found")

    # Fetch current price if entry not specified
    cat = "spot" if payload.market_type == MarketType.SPOT else "linear"
    current_price = payload.entry_price
    if not current_price:
        try:
            ticker = await bybit_service.get_ticker_info(payload.symbol, cat)
            current_price = float(ticker.get("lastPrice", 0))
        except Exception as e:
            raise HTTPException(503, f"Failed to get price: {e}")

    from app.models import PositionSide, AISignal
    from app.services.bybit_service import bybit_service as _bbs
    position_side = PositionSide.LONG if payload.side == "long" else PositionSide.SHORT

    # Auto-calculate qty from risk if not provided
    qty = payload.qty
    if not qty or qty <= 0:
        # Use configured risk on actual available capital
        try:
            if mode == TradingMode.REAL:
                configured_budget = settings.spot_allocated_balance if payload.market_type == MarketType.SPOT else settings.futures_allocated_balance
                if configured_budget:
                    reserved = await capital_service.get_mode_reserved_capital(db, mode, payload.market_type)
                    balance = max(float(configured_budget) - reserved, 0.0)
                else:
                    balance = await _bbs.get_usdt_balance()
            elif mode == TradingMode.PAPER:
                paper_snapshot = await capital_service.compute_paper_snapshot(db, settings)
                balance = paper_snapshot[payload.market_type.value].available
            else:
                balance = settings.backtest_initial_balance_spot if payload.market_type == MarketType.SPOT else settings.backtest_initial_balance_futures
            risk_amount = (balance or 1000) * (settings.risk_per_trade_pct / 100)
            cat_tmp = "spot" if payload.market_type == MarketType.SPOT else "linear"
            leverage = settings.default_leverage if payload.market_type == MarketType.FUTURES else 1
            qty = await _bbs.calculate_position_qty(
                symbol=payload.symbol,
                entry_price=current_price,
                risk_amount_usdt=risk_amount,
                stop_loss_price=payload.stop_loss,
                category=cat_tmp,
                leverage=leverage,
                capital_limit_usdt=balance,
            )
        except Exception:
            qty = 0.0

    if not qty or qty <= 0:
        raise HTTPException(400, "Could not determine position size. Please provide qty explicitly.")

    trade = Trade(
        mode=mode,
        market_type=payload.market_type,
        symbol=payload.symbol,
        side=position_side,
        status=TradeStatus.OPEN,
        entry_price=current_price,
        entry_qty=qty,
        entry_time=datetime.now(timezone.utc),
        stop_loss_price=payload.stop_loss,
        take_profit_1_price=payload.take_profit_1,
        take_profit_2_price=payload.take_profit_2,
        take_profit_3_price=payload.take_profit_3,
        leverage=settings.default_leverage if payload.market_type == MarketType.FUTURES else 1,
        ai_signal=None,
        ai_analysis_entry="Manual trade",
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    await manager.broadcast(Events.TRADE_OPENED, {
        "trade_id": trade.id,
        "symbol": payload.symbol,
        "side": payload.side,
        "mode": mode.value,
    })
    return {"success": True, "trade_id": trade.id}


@router.post("/close/{trade_id}")
async def close_trade(
    trade_id: int,
    mode: TradingMode,
    db: AsyncSession = Depends(get_db),
):
    """Manually close a trade."""
    result = await db.execute(
        select(Trade).where(Trade.id == trade_id, Trade.mode == mode)
    )
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(404, "Trade not found")
    if trade.status != TradeStatus.OPEN:
        raise HTTPException(400, "Trade is not open")

    await engine.close_position(trade_id, mode, reason="manual")

    await manager.broadcast(Events.TRADE_CLOSED, {
        "trade_id": trade_id,
        "mode": mode.value,
    })
    return {"success": True}


@router.get("/open-positions/{mode}")
async def get_open_positions(mode: TradingMode, db: AsyncSession = Depends(get_db)):
    """Get all open positions for a mode."""
    result = await db.execute(
        select(Trade).where(
            Trade.mode == mode,
            Trade.status == TradeStatus.OPEN,
        )
    )
    trades = result.scalars().all()

    positions = []
    for t in trades:
        # Get current price for unrealized PnL
        cat = "spot" if t.market_type == MarketType.SPOT else "linear"
        try:
            ticker = await bybit_service.get_ticker_info(t.symbol, cat)
            current_price = float(ticker.get("lastPrice", t.entry_price))
        except Exception:
            current_price = t.entry_price

        remaining_qty = t.entry_qty - t.exit_qty
        if t.side.value == "Long":
            unr_pnl = (current_price - t.entry_price) * remaining_qty
        else:
            unr_pnl = (t.entry_price - current_price) * remaining_qty

        positions.append({
            "id": t.id,
            "symbol": t.symbol,
            "market_type": t.market_type.value,
            "side": t.side.value,
            "entry_price": t.entry_price,
            "current_price": current_price,
            "qty": t.entry_qty,
            "remaining_qty": remaining_qty,
            "stop_loss": t.stop_loss_price,
            "tp1": t.take_profit_1_price,
            "tp2": t.take_profit_2_price,
            "tp3": t.take_profit_3_price,
            "tp1_filled": t.tp1_filled,
            "tp2_filled": t.tp2_filled,
            "tp3_filled": t.tp3_filled,
            "realized_pnl": t.realized_pnl,
            "unrealized_pnl": round(unr_pnl, 4),
            "net_pnl": t.net_pnl,
            "fees": t.fees_total,
            "leverage": t.leverage,
            "ai_signal": t.ai_signal.value if t.ai_signal else None,
            "ai_confidence": t.ai_confidence,
            "entry_time": t.entry_time.isoformat(),
            "trailing_stop_active": t.trailing_stop_active,
            "trailing_stop_price": t.trailing_stop_price,
        })

    return {"positions": positions, "count": len(positions)}


@router.get("/pnl-summary/{mode}")
async def get_pnl_summary(mode: TradingMode, db: AsyncSession = Depends(get_db)):
    """Get PnL summary: today, this week, this month, all time."""
    from sqlalchemy import func
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = today_start.replace(day=1)

    result = await db.execute(
        select(Trade).where(
            Trade.mode == mode,
            Trade.status == TradeStatus.CLOSED,
        )
    )
    closed = result.scalars().all()

    def pnl_for(trades, start):
        return sum(
            t.net_pnl for t in trades
            if t.exit_time and t.exit_time >= start
        )

    unrealized = await db.execute(
        select(Trade).where(
            Trade.mode == mode,
            Trade.status == TradeStatus.OPEN,
        )
    )
    open_trades = unrealized.scalars().all()
    total_unrealized = sum(t.unrealized_pnl for t in open_trades)

    return {
        "today": round(pnl_for(closed, today_start), 4),
        "week": round(pnl_for(closed, week_start), 4),
        "month": round(pnl_for(closed, month_start), 4),
        "all_time": round(sum(t.net_pnl for t in closed), 4),
        "unrealized": round(total_unrealized, 4),
        "open_positions": len(open_trades),
    }


async def _compute_today_pnl(mode) -> float:
    """Helper: sum net_pnl for today's closed trades."""
    from datetime import datetime, timezone
    from app.database import AsyncSessionLocal
    from app.models import Trade, TradeStatus
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Trade).where(
                Trade.mode == mode,
                Trade.status == TradeStatus.CLOSED,
                Trade.exit_time >= today_start,
            )
        )
        return sum(t.net_pnl for t in r.scalars().all())
