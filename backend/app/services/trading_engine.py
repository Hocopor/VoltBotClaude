"""
Trading Engine — VOLTAGE Bot Core
Orchestrates real trading, paper trading, and backtest modes.
Applies VOLTAGE strategy + AI analysis → places orders with proper SL/TP.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import (
    Trade, Order, OrderStatus, OrderSide, OrderType, PositionSide,
    TradingMode, MarketType, TradeStatus, AIAnalysisLog, AISignal, BotSettings
)
from app.services.bybit_service import bybit_service
from app.services.ai_service import ai_service
from app.services.strategy.voltage_strategy import VoltageStrategy, Signal
from app.services.paper_trading import PaperTradingEngine
from app.database import AsyncSessionLocal


MAJORS = {"BTC", "ETH"}

# Bybit interval codes
TF_MAP = {
    "1W": "W",
    "1D": "D",
    "4H": "240",
    "1H": "60",
    "15M": "15",
}


class TradingEngine:
    def __init__(self):
        self._running = False
        self._tasks: dict[str, asyncio.Task] = {}
        self.paper = PaperTradingEngine()

    async def start(self, mode: TradingMode):
        if self._running:
            return
        self._running = True
        logger.info(f"VOLTAGE Engine starting [{mode.value}]")

        async with AsyncSessionLocal() as db:
            settings = await self._get_settings(db, mode)

        if not settings:
            logger.error(f"No settings for mode {mode.value}")
            self._running = False
            return

        symbols: list[tuple[str, MarketType]] = []
        if settings.spot_enabled:
            symbols += [(s, MarketType.SPOT) for s in (settings.spot_pairs or [])]
        if settings.futures_enabled:
            symbols += [(s, MarketType.FUTURES) for s in (settings.futures_pairs or [])]

        if not symbols:
            logger.warning(f"Engine started but no pairs configured for mode {mode.value}")
            self._running = False
            return

        for symbol, market_type in symbols:
            key = f"{symbol}_{market_type.value}"
            if key not in self._tasks:
                self._tasks[key] = asyncio.create_task(
                    self._symbol_loop(symbol, market_type, mode, settings)
                )

        # Also start position monitor
        self._tasks["__monitor__"] = asyncio.create_task(
            self.monitor_positions(mode)
        )

        logger.info(f"Engine running {len(self._tasks)-1} symbol loops [{mode.value}]")

    async def stop(self):
        self._running = False
        for task in self._tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("VOLTAGE Engine stopped")

    async def _symbol_loop(
        self, symbol: str, market_type: MarketType, mode: TradingMode, settings: BotSettings
    ):
        interval_secs = 60 * 15   # analyse every 15 min
        logger.info(f"Loop: {symbol} {market_type.value} [{mode.value}]")
        while self._running:
            try:
                await self._analyze_and_trade(symbol, market_type, mode, settings)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Loop error {symbol}: {e}", exc_info=True)
            await asyncio.sleep(interval_secs)

    async def _analyze_and_trade(
        self, symbol: str, market_type: MarketType, mode: TradingMode, settings: BotSettings
    ):
        logger.debug(f"Analysing {symbol} [{mode.value}]")
        cat = "spot" if market_type == MarketType.SPOT else "linear"

        # --- Fetch OHLCV ---
        try:
            klines: dict[str, pd.DataFrame] = {}
            for tf_name, tf_code in TF_MAP.items():
                raw = await bybit_service.get_klines(symbol, tf_code, category=cat, limit=200)
                if raw:
                    df = pd.DataFrame(raw)
                    for col in ["open", "high", "low", "close", "volume"]:
                        df[col] = df[col].astype(float)
                    klines[tf_name] = df
        except Exception as e:
            logger.error(f"Klines fetch failed {symbol}: {e}")
            return

        if not all(tf in klines for tf in ["1W", "1D", "4H", "1H"]):
            return

        # --- Market context ---
        try:
            orderbook = await bybit_service.get_orderbook(symbol, category=cat)
        except Exception:
            orderbook = None

        try:
            fear_greed = await bybit_service.get_fear_greed_index()
            btc_dominance = await bybit_service.get_btc_dominance()
        except Exception:
            fear_greed, btc_dominance = 50, 50.0

        # --- VOLTAGE Strategy ---
        is_major = symbol.replace("USDT", "") in MAJORS
        strategy = VoltageStrategy(symbol, is_major=is_major)
        voltage_signal = strategy.run_all_filters(
            ohlcv_1w=klines["1W"],
            ohlcv_1d=klines["1D"],
            ohlcv_4h=klines["4H"],
            ohlcv_1h=klines["1H"],
            orderbook=orderbook,
            btc_dominance=btc_dominance,
            fear_greed=fear_greed,
        )

        # --- AI enrichment ---
        current_price = float(klines["4H"]["close"].iloc[-1])
        market_data = {
            "price": current_price,
            "change_24h": 0,
            "volume_24h": float(klines["1D"]["volume"].iloc[-1]) if len(klines["1D"]) else 0,
        }
        ai_result = await ai_service.analyze_market(
            symbol=symbol,
            market_type=market_type.value,
            voltage_signal=voltage_signal,
            market_data=market_data,
        )

        # --- Log analysis ---
        async with AsyncSessionLocal() as db:
            try:
                signal_val = ai_result["signal"]
                ai_signal_enum = AISignal(signal_val) if signal_val in [s.value for s in AISignal] else AISignal.NEUTRAL
                log_entry = AIAnalysisLog(
                    mode=mode,
                    symbol=symbol,
                    market_type=market_type,
                    filters_state={"filters_passed": voltage_signal.filters_passed},
                    indicators={
                        "rsi": getattr(voltage_signal.filter3, "rsi_14", 50) if voltage_signal.filter3 else 50,
                        "macd_hist": getattr(voltage_signal.filter2, "h4_macd_hist", 0) if voltage_signal.filter2 else 0,
                        "atr": getattr(voltage_signal.filter3, "atr_14", 0) if voltage_signal.filter3 else 0,
                    },
                    market_context={
                        "price": current_price,
                        "fear_greed": fear_greed,
                        "btc_dominance": btc_dominance,
                        "scenario": voltage_signal.market_scenario.value,
                    },
                    signal=ai_signal_enum,
                    confidence=ai_result["confidence"],
                    reasoning=ai_result.get("reasoning", "")[:2000],
                    suggested_entry=ai_result.get("entry_price"),
                    suggested_sl=ai_result.get("stop_loss"),
                    suggested_tp1=ai_result.get("take_profit_1"),
                    suggested_tp2=ai_result.get("take_profit_2"),
                    suggested_tp3=ai_result.get("take_profit_3"),
                )
                db.add(log_entry)
                await db.commit()
            except Exception as e:
                logger.warning(f"AI log write failed: {e}")

        # --- Broadcast signal to UI ---
        from app.websocket.manager import manager, Events
        await manager.broadcast(Events.AI_SIGNAL, {
            "symbol": symbol,
            "mode": mode.value,
            "signal": ai_result["signal"],
            "confidence": ai_result["confidence"],
            "filters_passed": voltage_signal.filters_passed,
            "entry": ai_result.get("entry_price"),
            "sl": ai_result.get("stop_loss"),
            "tp1": ai_result.get("take_profit_1"),
            "tp2": ai_result.get("take_profit_2"),
            "tp3": ai_result.get("take_profit_3"),
        })

        # --- Decide to trade ---
        confidence = ai_result["confidence"]
        signal = ai_result["signal"]
        threshold = settings.ai_confidence_threshold

        should_trade = (
            signal in ["long", "short"]
            and confidence >= threshold
            and voltage_signal.filters_passed >= 4
            and settings.auto_trading_enabled
        )

        if should_trade:
            logger.info(
                f"SIGNAL: {symbol} {signal.upper()} | "
                f"conf={confidence:.3f} | filters={voltage_signal.filters_passed}/6"
            )
            await self._execute_trade(
                symbol=symbol,
                market_type=market_type,
                mode=mode,
                signal=signal,
                ai_result=ai_result,
                voltage_signal=voltage_signal,
                settings=settings,
                current_price=current_price,
                klines_4h=klines["4H"],
            )
        else:
            logger.debug(
                f"No trade: {symbol} | {signal} conf={confidence:.3f} "
                f"filters={voltage_signal.filters_passed}/6 threshold={threshold}"
            )

    async def _execute_trade(
        self,
        symbol: str,
        market_type: MarketType,
        mode: TradingMode,
        signal: str,
        ai_result: dict,
        voltage_signal,
        settings: BotSettings,
        current_price: float,
        klines_4h: pd.DataFrame,
    ):
        cat = "spot" if market_type == MarketType.SPOT else "linear"
        position_side = PositionSide.LONG if signal == "long" else PositionSide.SHORT
        order_side = OrderSide.BUY if signal == "long" else OrderSide.SELL

        entry_price = ai_result.get("entry_price") or current_price
        stop_loss = ai_result.get("stop_loss")
        tp1 = ai_result.get("take_profit_1")
        tp2 = ai_result.get("take_profit_2")
        tp3 = ai_result.get("take_profit_3")

        if not stop_loss:
            logger.warning(f"No SL for {symbol} — skipping trade")
            return

        if mode == TradingMode.REAL:
            balance = settings.spot_allocated_balance if market_type == MarketType.SPOT else settings.futures_allocated_balance
            if not balance:
                try:
                    balance = await bybit_service.get_usdt_balance()
                except Exception:
                    balance = 1000.0
        elif mode == TradingMode.PAPER:
            balance = (settings.paper_current_balance_spot
                       if market_type == MarketType.SPOT
                       else settings.paper_current_balance_futures)
        else:
            return  # Backtest handled separately

        if not balance or balance <= 0:
            logger.warning(f"No balance for {symbol} [{mode.value}]")
            return

        risk_amount = balance * (settings.risk_per_trade_pct / 100)
        leverage = settings.default_leverage if market_type == MarketType.FUTURES else 1

        try:
            qty = await bybit_service.calculate_position_qty(
                symbol=symbol,
                entry_price=entry_price,
                risk_amount_usdt=risk_amount,
                stop_loss_price=stop_loss,
                category=cat,
                leverage=leverage,
            )
        except Exception as e:
            logger.error(f"Qty calculation failed {symbol}: {e}")
            return

        if qty <= 0:
            logger.warning(f"qty={qty} for {symbol} — skipping")
            return

        async with AsyncSessionLocal() as db:
            # Guard: no duplicate open positions for same symbol
            existing = await db.execute(
                select(Trade).where(
                    Trade.mode == mode,
                    Trade.status == TradeStatus.OPEN,
                    Trade.symbol == symbol,
                )
            )
            if existing.scalars().first():
                logger.info(f"Already have open position in {symbol}")
                return

            # Also enforce max_open_positions
            count_q = await db.execute(
                select(Trade).where(
                    Trade.mode == mode,
                    Trade.status == TradeStatus.OPEN,
                )
            )
            open_count = len(count_q.scalars().all())
            if open_count >= settings.max_open_positions:
                logger.info(f"Max positions reached ({open_count}/{settings.max_open_positions})")
                return

            trade = Trade(
                mode=mode,
                market_type=market_type,
                symbol=symbol,
                side=position_side,
                status=TradeStatus.OPEN,
                entry_price=entry_price,
                entry_qty=qty,
                entry_time=datetime.now(timezone.utc),
                stop_loss_price=stop_loss,
                take_profit_1_price=tp1,
                take_profit_2_price=tp2,
                take_profit_3_price=tp3,
                leverage=leverage,
                ai_signal=AISignal(signal) if signal in [s.value for s in AISignal] else None,
                ai_confidence=ai_result["confidence"],
                ai_analysis_entry=ai_result.get("reasoning", "")[:2000],
                ai_filters_snapshot={"filters_passed": voltage_signal.filters_passed},
                voltage_filters=ai_result.get("voltage_filters"),
            )
            db.add(trade)
            await db.flush()  # get trade.id

            if mode == TradingMode.REAL:
                await self._place_real_orders(
                    db, trade, symbol, order_side, qty,
                    entry_price, stop_loss, tp1, cat, leverage,
                )
            elif mode == TradingMode.PAPER:
                await self.paper.open_position(db, trade, settings)

            await db.commit()
            logger.info(f"Trade opened: {symbol} {signal.upper()} qty={qty} @ {entry_price}")

    async def _place_real_orders(
        self,
        db: AsyncSession,
        trade: Trade,
        symbol: str,
        order_side: OrderSide,
        qty: float,
        entry_price: float,
        stop_loss: float,
        tp1: Optional[float],
        category: str,
        leverage: int,
    ):
        if category == "linear":
            try:
                await bybit_service.set_leverage(symbol, leverage)
            except Exception as e:
                logger.warning(f"Leverage set failed: {e}")

        order_link_id = f"VLT_{trade.id}_{uuid.uuid4().hex[:8]}"
        price_diff_pct = abs(entry_price - trade.entry_price) / max(trade.entry_price, 1)
        use_limit = price_diff_pct < 0.003

        try:
            bybit_order = await bybit_service.place_order(
                symbol=symbol,
                side=order_side.value,
                order_type="Limit" if use_limit else "Market",
                qty=qty,
                category=category,
                price=entry_price if use_limit else None,
                stop_loss=stop_loss,
                take_profit=tp1,
                order_link_id=order_link_id,
            )
            order = Order(
                mode=trade.mode,
                market_type=trade.market_type,
                exchange_order_id=bybit_order.get("orderId"),
                symbol=symbol,
                side=order_side,
                order_type=OrderType.LIMIT if use_limit else OrderType.MARKET,
                status=OrderStatus.OPEN,
                position_side=trade.side,
                price=entry_price if use_limit else None,
                qty=qty,
                trade_id=trade.id,
                ai_signal=trade.ai_signal,
                ai_confidence=trade.ai_confidence,
            )
            db.add(order)
        except Exception as e:
            logger.error(f"Real order failed {symbol}: {e}")
            trade.status = TradeStatus.CANCELLED
            raise

    async def close_position(self, trade_id: int, mode: TradingMode, reason: str = "manual"):
        """Manually close an open position and create journal entry."""
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Trade).where(Trade.id == trade_id))
            trade = r.scalar_one_or_none()
            if not trade or trade.status != TradeStatus.OPEN:
                return

            cat = "spot" if trade.market_type == MarketType.SPOT else "linear"

            if mode == TradingMode.REAL:
                close_side = "Sell" if trade.side == PositionSide.LONG else "Buy"
                try:
                    ticker = await bybit_service.get_ticker_info(trade.symbol, cat)
                    current_price = float(ticker.get("lastPrice", trade.entry_price))
                    await bybit_service.place_order(
                        symbol=trade.symbol,
                        side=close_side,
                        order_type="Market",
                        qty=round(trade.entry_qty - trade.exit_qty, 8),
                        category=cat,
                        reduce_only=True,
                    )
                    exit_price = current_price
                except Exception as e:
                    logger.error(f"Close order failed: {e}")
                    return
            else:
                # Paper: get live price for simulation
                try:
                    ticker = await bybit_service.get_ticker_info(trade.symbol, cat)
                    exit_price = float(ticker.get("lastPrice", trade.entry_price))
                except Exception:
                    exit_price = trade.entry_price

                # Settle remaining PnL
                remaining = round(trade.entry_qty - trade.exit_qty, 8)
                if remaining > 0:
                    fee = exit_price * remaining * 0.001
                    is_long = trade.side == PositionSide.LONG
                    pnl = (exit_price - trade.entry_price) * remaining * (1 if is_long else -1)
                    trade.realized_pnl += pnl
                    trade.fees_total += fee
                    trade.net_pnl = trade.realized_pnl - trade.fees_total

            trade.status = TradeStatus.CLOSED
            trade.exit_price = exit_price
            trade.exit_time = datetime.now(timezone.utc)
            trade.unrealized_pnl = 0.0
            await db.flush()

            # Create journal entry for all modes
            try:
                from app.services.journal_service import journal_service
                entry = await journal_service.create_or_update(db, trade)
                await db.flush()
                if entry.id:
                    asyncio.create_task(
                        journal_service.trigger_ai_analysis_background(entry.id)
                    )
            except Exception as e:
                logger.error(f"Journal on close failed: {e}")

            await db.commit()

            from app.websocket.manager import manager, Events
            await manager.broadcast(Events.TRADE_CLOSED, {
                "trade_id": trade_id,
                "symbol": trade.symbol,
                "net_pnl": round(trade.net_pnl, 4),
                "mode": mode.value,
            })

    async def monitor_positions(self, mode: TradingMode):
        """Monitor open positions: update PnL and check paper TP/SL."""
        while self._running:
            try:
                async with AsyncSessionLocal() as db:
                    r = await db.execute(
                        select(Trade).where(
                            Trade.mode == mode,
                            Trade.status == TradeStatus.OPEN,
                        )
                    )
                    open_trades = r.scalars().all()

                    for trade in open_trades:
                        cat = "spot" if trade.market_type == MarketType.SPOT else "linear"
                        try:
                            ticker = await bybit_service.get_ticker_info(trade.symbol, cat)
                            current_price = float(ticker.get("lastPrice", trade.entry_price))
                        except Exception:
                            continue

                        remaining = trade.entry_qty - trade.exit_qty
                        is_long = trade.side == PositionSide.LONG
                        unr = (current_price - trade.entry_price) * remaining * (1 if is_long else -1)
                        trade.unrealized_pnl = round(unr, 6)

                        # Paper/backtest: check TP/SL
                        if mode in (TradingMode.PAPER, TradingMode.BACKTEST):
                            await self.paper.check_tp_sl(db, trade, current_price)

                    await db.commit()

                from app.websocket.manager import manager, Events
                async with AsyncSessionLocal() as db:
                    r = await db.execute(
                        select(Trade).where(Trade.mode == mode, Trade.status == TradeStatus.OPEN)
                    )
                    open_trades = r.scalars().all()
                    total_unr = sum(t.unrealized_pnl for t in open_trades)

                from app.api.routes.trading import _compute_today_pnl
                today_pnl = await _compute_today_pnl(mode)
                await manager.broadcast(Events.PNL_UPDATE, {
                    "unrealized": round(total_unr, 4),
                    "today": round(today_pnl, 4),
                    "mode": mode.value,
                })

            except Exception as e:
                logger.error(f"Monitor error [{mode.value}]: {e}")

            await asyncio.sleep(30)

    async def _get_settings(self, db: AsyncSession, mode: TradingMode) -> Optional[BotSettings]:
        r = await db.execute(select(BotSettings).where(BotSettings.mode == mode))
        return r.scalar_one_or_none()

# Global singleton — imported by routes and main
engine = TradingEngine()

