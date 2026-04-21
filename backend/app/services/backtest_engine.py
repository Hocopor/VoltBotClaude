"""
Backtest Engine — Historical Trading Simulation
Walk-forward simulation of VOLTAGE strategy on Bybit historical data.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

import pandas as pd
import numpy as np

from sqlalchemy import select, delete

from app.models import (
    BacktestSession, Trade, TradingMode, MarketType, TradeStatus, PositionSide, AISignal
)
from app.services.strategy.voltage_strategy import VoltageStrategy, Signal
from app.services.bybit_service import bybit_service
from app.services.ai_service import ai_service
from app.services.macro_data_service import macro_data_service
from app.services.journal_service import journal_service
from app.database import AsyncSessionLocal


class BacktestEngine:
    def __init__(self):
        self._active: dict[int, bool] = {}

    @staticmethod
    def _slice_until(
        df: pd.DataFrame,
        timestamp_ms: int,
        *,
        max_rows: Optional[int] = None,
    ) -> pd.DataFrame:
        if df.empty or "timestamp" not in df.columns:
            return pd.DataFrame()

        sliced = df[df["timestamp"] <= timestamp_ms].copy()
        if max_rows and len(sliced) > max_rows:
            sliced = sliced.iloc[-max_rows:].copy()
        return sliced.reset_index(drop=True)

    async def run_backtest(
        self,
        session_id: int,
        symbols: list[str],
        market_type: MarketType,
        start_date: datetime,
        end_date: datetime,
        initial_balance: float,
        risk_per_trade_pct: float = 2.0,
        ai_confidence_threshold: float = 0.60,
        leverage: int = 1,
        scan_interval_minutes: int = 240,
    ) -> dict:
        self._active[session_id] = True
        cat = "spot" if market_type == MarketType.SPOT else "linear"

        async with AsyncSessionLocal() as db:
            r = await db.execute(select(BacktestSession).where(BacktestSession.id == session_id))
            session = r.scalar_one_or_none()
            if not session:
                return {"error": "Session not found"}
            session.status = "running"
            await db.commit()

        try:
            all_trades: list[dict] = []
            all_ai_analyses: list[dict] = []
            all_decisions: list[dict] = []
            decision_stats: dict[str, int] = {}
            balance = initial_balance
            equity_curve = [{"time": start_date.isoformat(), "equity": balance}]
            total = len(symbols)
            macro_context = await macro_data_service.get_historical_context(start_date, end_date)
            stopped = False

            for idx, symbol in enumerate(symbols):
                if not self._active.get(session_id):
                    stopped = True
                    break
                logger.info(f"Backtest {symbol} ({idx+1}/{total}) [{session_id}]")

                klines_map = await self._fetch_historical(symbol, cat, start_date, end_date)
                if not klines_map or "4H" not in klines_map or len(klines_map["4H"]) < 60:
                    logger.warning(f"Insufficient data for {symbol}")
                    continue

                simulation = await self._simulate_symbol(
                    symbol=symbol,
                    market_type=market_type,
                    klines_map=klines_map,
                    macro_context=macro_context,
                    start_date=start_date,
                    end_date=end_date,
                    balance=balance,
                    risk_pct=risk_per_trade_pct,
                    conf_threshold=ai_confidence_threshold,
                    leverage=leverage,
                    scan_interval_minutes=scan_interval_minutes,
                    session_id=session_id,
                    symbol_index=idx,
                    total_symbols=total,
                )
                sym_trades = simulation["trades"]

                await self._persist_backtest_trades(
                    symbol=symbol,
                    market_type=market_type,
                    trades=sym_trades,
                    klines_map=klines_map,
                    session_id=session_id,
                )

                for t in sym_trades:
                    balance += t["net_pnl"]
                    equity_curve.append({"time": t["exit_time"] or "", "equity": round(balance, 2)})

                all_trades.extend(sym_trades)
                all_ai_analyses.extend(simulation["ai_analyses"])
                all_decisions.extend(simulation["decisions"])
                for reason, count in simulation["decision_stats"].items():
                    decision_stats[reason] = decision_stats.get(reason, 0) + count

                if not self._active.get(session_id):
                    stopped = True

                progress = (idx + 1) / total
                interim_metrics = self._calc_metrics(all_trades, initial_balance, balance)
                interim_metrics["equity_curve"] = equity_curve
                interim_metrics["decision_stats"] = decision_stats
                await self._update_session_state(
                    session_id=session_id,
                    status="stopped" if stopped else "running",
                    progress=progress,
                    final_balance=balance,
                    metrics=interim_metrics,
                    macro_context=macro_context,
                    decisions=all_decisions,
                    trades=all_trades,
                    ai_analyses=all_ai_analyses,
                    progress_marker={
                        "symbol": symbol,
                        "time": None,
                        "equity": round(balance, 2),
                        "progress_pct": round(progress * 100, 2),
                    },
                    completed=stopped,
                )

                if stopped:
                    break

            metrics = self._calc_metrics(all_trades, initial_balance, balance)
            metrics["equity_curve"] = equity_curve
            metrics["decision_stats"] = decision_stats

            final_status = "stopped" if stopped else "done"
            await self._update_session_state(
                session_id=session_id,
                status=final_status,
                progress=1.0 if not stopped else None,
                final_balance=balance,
                metrics=metrics,
                macro_context=macro_context,
                decisions=all_decisions,
                trades=all_trades,
                ai_analyses=all_ai_analyses,
                progress_marker={
                    "symbol": None,
                    "time": None,
                    "equity": round(balance, 2),
                    "progress_pct": 100.0 if not stopped else None,
                },
                completed=True,
            )

            from app.websocket.manager import manager, Events
            await manager.broadcast(Events.BACKTEST_COMPLETE, {
                "session_id": session_id,
                "session_name": "",
                "total_trades": metrics["total_trades"],
                "win_rate": metrics["win_rate"],
                "total_pnl": metrics["total_pnl"],
                "status": final_status,
            })

            return metrics

        except Exception as e:
            logger.error(f"Backtest error [{session_id}]: {e}", exc_info=True)
            async with AsyncSessionLocal() as db:
                r = await db.execute(select(BacktestSession).where(BacktestSession.id == session_id))
                s = r.scalar_one_or_none()
                if s:
                    s.status = "error"
                    s.error_message = str(e)[:500]
                    await db.commit()
            return {"error": str(e)}
        finally:
            self._active.pop(session_id, None)

    def _build_results_data(
        self,
        *,
        equity_curve: list[dict],
        macro_context: dict,
        decision_stats: dict[str, int],
        decisions: list[dict],
        trades: list[dict],
        ai_analyses: list[dict],
        progress_marker: Optional[dict] = None,
    ) -> dict:
        return {
            "equity_curve": equity_curve,
            "monthly_pnl": self._calc_metrics(trades, equity_curve[0]["equity"] if equity_curve else 0.0, equity_curve[-1]["equity"] if equity_curve else 0.0).get("monthly_pnl", {}),
            "macro_context": {
                "btc_dominance_source": macro_context.get("btc_dominance_source"),
            },
            "decision_stats": decision_stats,
            "decision_log": decisions[:1000],
            "trades_summary": [self._summary(t) for t in trades[:500]],
            "ai_analyses": ai_analyses[:1000],
            "progress_marker": progress_marker,
        }

    async def _update_session_state(
        self,
        *,
        session_id: int,
        status: str,
        progress: Optional[float],
        final_balance: float,
        metrics: dict,
        macro_context: dict,
        decisions: list[dict],
        trades: list[dict],
        ai_analyses: list[dict],
        progress_marker: Optional[dict] = None,
        completed: bool = False,
    ) -> None:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(BacktestSession).where(BacktestSession.id == session_id))
            s = r.scalar_one_or_none()
            if not s:
                return

            s.status = status
            if progress is not None:
                s.progress = progress
            s.final_balance = final_balance
            s.total_trades = metrics.get("total_trades", 0)
            s.winning_trades = metrics.get("winning_trades", 0)
            s.losing_trades = metrics.get("losing_trades", 0)
            s.win_rate = metrics.get("win_rate", 0.0)
            s.profit_factor = metrics.get("profit_factor", 0.0)
            s.max_drawdown = metrics.get("max_drawdown", 0.0)
            s.total_pnl = metrics.get("total_pnl", 0.0)
            s.avg_rr = metrics.get("avg_rr", 0.0)
            s.results_data = self._build_results_data(
                equity_curve=metrics.get("equity_curve", []),
                macro_context=macro_context,
                decision_stats=metrics.get("decision_stats", {}),
                decisions=decisions,
                trades=trades,
                ai_analyses=ai_analyses,
                progress_marker=progress_marker,
            )
            if completed:
                s.completed_at = datetime.now(timezone.utc)
            await db.commit()

        from app.websocket.manager import manager, Events
        await manager.broadcast(
            Events.BACKTEST_PROGRESS,
            {
                "session_id": session_id,
                "status": status,
                "progress": progress,
                "progress_marker": progress_marker,
            },
        )

    async def _fetch_historical(
        self, symbol: str, category: str, start: datetime, end: datetime
    ) -> dict[str, pd.DataFrame]:
        tf_codes = {"1W": "W", "1D": "D", "4H": "240", "1H": "60"}
        result: dict[str, pd.DataFrame] = {}
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        for tf_name, tf_code in tf_codes.items():
            try:
                all_candles: list[dict] = []
                current_end = end_ms
                for _ in range(20):  # max 20 pages = 4000 bars
                    candles = await bybit_service.get_klines(
                        symbol=symbol, interval=tf_code, category=category,
                        limit=200, end_time=current_end,
                    )
                    if not candles:
                        break
                    all_candles = candles + all_candles
                    if candles[0]["timestamp"] <= start_ms or len(candles) < 200:
                        break
                    current_end = candles[0]["timestamp"] - 1

                if all_candles:
                    df = pd.DataFrame(all_candles)
                    df = df[df["timestamp"] >= start_ms].copy()
                    for col in ["open", "high", "low", "close", "volume"]:
                        df[col] = df[col].astype(float)
                    result[tf_name] = df.reset_index(drop=True)
            except Exception as e:
                logger.warning(f"Fetch {tf_name}/{symbol}: {e}")

        return result

    async def _simulate_symbol(
        self,
        symbol: str,
        market_type: MarketType,
        klines_map: dict[str, pd.DataFrame],
        macro_context: dict,
        start_date: datetime,
        end_date: datetime,
        balance: float,
        risk_pct: float,
        conf_threshold: float,
        leverage: int,
        scan_interval_minutes: int,
        session_id: int,
        symbol_index: int,
        total_symbols: int,
    ) -> dict[str, list[dict] | dict[str, int]]:
        trades: list[dict] = []
        ai_analyses: list[dict] = []
        decisions: list[dict] = []
        decision_stats: dict[str, int] = {}
        h4 = klines_map["4H"]
        is_major = symbol.replace("USDT", "") in {"BTC", "ETH"}
        strategy = VoltageStrategy(symbol, is_major=is_major)
        open_trade: Optional[dict] = None
        min_bars = 60

        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)
        scan_interval_ms = max(int(scan_interval_minutes), 1) * 60 * 1000
        last_scan_ts: Optional[int] = None

        for i in range(min_bars, len(h4)):
            if not self._active.get(session_id):
                break

            bar = h4.iloc[i]
            ts = int(bar["timestamp"])
            if ts < start_ms or ts > end_ms:
                continue
            if last_scan_ts is not None and ts - last_scan_ts < scan_interval_ms:
                continue
            last_scan_ts = ts

            current_close = float(bar["close"])
            current_fear_greed = int(
                macro_data_service.value_for_timestamp(
                    macro_context.get("fear_greed", {}),
                    ts,
                    50,
                )
            )
            current_btc_dominance = macro_data_service.value_for_timestamp(
                    macro_context.get("btc_dominance", {}),
                    ts,
                    None,
                )

            # Check existing trade first
            if open_trade:
                closed = self._check_exit(open_trade, bar)
                if closed:
                    trades.append(closed)
                    open_trade = None
                continue

            # Only one position at a time per symbol
            h4_slice = h4.iloc[max(0, i - 200): i + 1].copy()
            w_slice = self._slice_until(klines_map.get("1W", pd.DataFrame()), ts, max_rows=200)
            d_slice = self._slice_until(klines_map.get("1D", pd.DataFrame()), ts, max_rows=250)
            h1_slice = self._slice_until(klines_map.get("1H", pd.DataFrame()), ts, max_rows=300)

            if len(h4_slice) < min_bars or d_slice.empty or h1_slice.empty:
                continue

            try:
                strategy_signal = strategy.run_all_filters(
                    ohlcv_1w=w_slice, ohlcv_1d=d_slice,
                    ohlcv_4h=h4_slice, ohlcv_1h=h1_slice,
                    btc_dominance=current_btc_dominance,
                    fear_greed=current_fear_greed,
                )
            except Exception:
                continue

            market_data = {
                "price": current_close,
                "change_24h": 0,
                "volume_24h": float(d_slice["volume"].iloc[-1]) if len(d_slice) else 0,
            }

            ai_result = await ai_service.analyze_market(
                symbol=symbol,
                market_type=market_type.value,
                voltage_signal=strategy_signal,
                market_data=market_data,
            )

            reason = self._decision_reason(
                ai_result=ai_result,
                strategy_signal=strategy_signal,
                conf_threshold=conf_threshold,
            )
            self._record_decision(
                decisions=decisions,
                decision_stats=decision_stats,
                ai_analyses=ai_analyses,
                symbol=symbol,
                timestamp_ms=ts,
                price=current_close,
                ai_result=ai_result,
                strategy_signal=strategy_signal,
                reason=reason,
                fear_greed=current_fear_greed,
                btc_dominance=current_btc_dominance,
            )

            if i == min_bars or i % 12 == 0:
                step_progress = (i - min_bars + 1) / max(len(h4) - min_bars, 1)
                global_progress = min(0.999, (symbol_index + step_progress) / max(total_symbols, 1))
                running_equity = balance + sum(t["net_pnl"] for t in trades)
                interim_metrics = self._calc_metrics(trades, balance, running_equity)
                interim_metrics["equity_curve"] = [{"time": start_date.isoformat(), "equity": balance}] + [
                    {"time": t["exit_time"] or "", "equity": round(balance + sum(x["net_pnl"] for x in trades[:idx + 1]), 2)}
                    for idx, t in enumerate(trades)
                ]
                interim_metrics["decision_stats"] = decision_stats
                await self._update_session_state(
                    session_id=session_id,
                    status="running",
                    progress=global_progress,
                    final_balance=running_equity,
                    metrics=interim_metrics,
                    macro_context=macro_context,
                    decisions=decisions,
                    trades=trades,
                    ai_analyses=ai_analyses,
                    progress_marker={
                        "symbol": symbol,
                        "time": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                        "equity": round(running_equity, 2),
                        "progress_pct": round(global_progress * 100, 2),
                    },
                    completed=False,
                )

            if reason == "trade_opened":
                risk_amount = balance * (risk_pct / 100)
                risk_per_unit = abs(ai_result["entry_price"] - ai_result["stop_loss"])
                if risk_per_unit < 1e-10:
                    decision_stats["risk_per_unit_zero"] = decision_stats.get("risk_per_unit_zero", 0) + 1
                    continue
                qty = (risk_amount * leverage) / risk_per_unit
                if current_close > 0:
                    if market_type == MarketType.SPOT:
                        max_qty_from_capital = (balance * 0.999) / current_close
                    else:
                        max_qty_from_capital = (balance * leverage * 0.999) / current_close
                    qty = min(qty, max_qty_from_capital)
                if qty <= 0:
                    decision_stats["qty_non_positive"] = decision_stats.get("qty_non_positive", 0) + 1
                    continue

                open_trade = {
                    "symbol": symbol,
                    "market_type": market_type.value,
                    "side": ai_result["signal"],
                    "entry_price": current_close,
                    "entry_time": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                    "qty": qty,
                    "stop_loss": ai_result.get("stop_loss"),
                    "tp1": ai_result.get("take_profit_1"),
                    "tp2": ai_result.get("take_profit_2"),
                    "tp3": ai_result.get("take_profit_3"),
                    "tp1_filled": False, "tp2_filled": False, "tp3_filled": False,
                    "tp1_price_filled": None, "tp2_price_filled": None, "tp3_price_filled": None,
                    "trailing_stop": None, "trailing_active": False,
                    "realized_pnl": 0.0, "fees": 0.0, "exit_qty": 0.0,
                    "confidence": ai_result["confidence"],
                    "strategy_confidence": ai_result.get("strategy_confidence", strategy_signal.confidence),
                    "ai_confidence": ai_result.get("ai_confidence", strategy_signal.confidence),
                    "filters_passed": strategy_signal.filters_passed,
                    "reasoning": ai_result.get("reasoning", ""),
                    "filters_assessment": ai_result.get("filters_assessment", {}),
                    "voltage_filters": ai_result.get("voltage_filters", {}),
                    "scenario": ai_result.get("scenario", strategy_signal.market_scenario.value),
                    "fear_greed": current_fear_greed,
                    "btc_dominance": current_btc_dominance,
                    "leverage": leverage,
                    "exit_price": None, "exit_time": None,
                    "exit_reason": None, "net_pnl": 0.0,
                    "session_id": session_id,
                }

        if open_trade:
            last = h4.iloc[-1]
            last_price = float(last["close"])
            last_ts = datetime.fromtimestamp(int(last["timestamp"]) / 1000, tz=timezone.utc).isoformat()
            open_trade = self._force_close(open_trade, last_price, last_ts)
            trades.append(open_trade)

        return {
            "trades": trades,
            "ai_analyses": ai_analyses,
            "decisions": decisions,
            "decision_stats": decision_stats,
        }

    def _decision_reason(self, ai_result: dict, strategy_signal, conf_threshold: float) -> str:
        signal = ai_result.get("signal")
        if signal not in [Signal.LONG.value, Signal.SHORT.value]:
            return "signal_not_actionable"
        if ai_result.get("confidence", 0.0) < conf_threshold:
            return "confidence_below_threshold"
        if strategy_signal.filters_passed < 4:
            return "filters_below_minimum"
        if not ai_result.get("entry_price") or not ai_result.get("stop_loss"):
            return "missing_entry_or_stop_loss"
        return "trade_opened"

    def _record_decision(
        self,
        *,
        decisions: list[dict],
        decision_stats: dict[str, int],
        ai_analyses: list[dict],
        symbol: str,
        timestamp_ms: int,
        price: float,
        ai_result: dict,
        strategy_signal,
        reason: str,
        fear_greed: int,
        btc_dominance: Optional[float],
    ) -> None:
        decision_stats[reason] = decision_stats.get(reason, 0) + 1
        if len(ai_analyses) < 1000:
            ai_analyses.append(
                {
                    "symbol": symbol,
                    "time": datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat(),
                    "price": round(price, 6),
                    "signal": ai_result.get("signal"),
                    "confidence": ai_result.get("confidence"),
                    "strategy_confidence": ai_result.get("strategy_confidence", strategy_signal.confidence),
                    "ai_confidence": ai_result.get("ai_confidence", strategy_signal.confidence),
                    "filters_passed": strategy_signal.filters_passed,
                    "scenario": ai_result.get("scenario", strategy_signal.market_scenario.value),
                    "fear_greed": fear_greed,
                    "btc_dominance": round(btc_dominance, 4) if btc_dominance is not None else None,
                    "entry_price": ai_result.get("entry_price"),
                    "stop_loss": ai_result.get("stop_loss"),
                    "take_profit_1": ai_result.get("take_profit_1"),
                    "take_profit_2": ai_result.get("take_profit_2"),
                    "take_profit_3": ai_result.get("take_profit_3"),
                    "reasoning": ai_result.get("reasoning", "")[:1500],
                    "decision_reason": reason,
                    "filters_assessment": ai_result.get("filters_assessment", {}),
                    "voltage_filters": ai_result.get("voltage_filters", {}),
                }
            )
        if len(decisions) >= 1000:
            return

        decisions.append(
            {
                "symbol": symbol,
                "time": datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat(),
                "price": round(price, 6),
                "reason": reason,
                "signal": ai_result.get("signal"),
                "confidence": ai_result.get("confidence"),
                "strategy_confidence": ai_result.get("strategy_confidence", strategy_signal.confidence),
                "ai_confidence": ai_result.get("ai_confidence", strategy_signal.confidence),
                "filters_passed": strategy_signal.filters_passed,
                "scenario": ai_result.get("scenario", strategy_signal.market_scenario.value),
                "fear_greed": fear_greed,
                "btc_dominance": round(btc_dominance, 4) if btc_dominance is not None else None,
                "entry_price": ai_result.get("entry_price"),
                "stop_loss": ai_result.get("stop_loss"),
                "reasoning": ai_result.get("reasoning", "")[:1000],
            }
        )

    def _check_exit(self, trade: dict, bar: pd.Series) -> Optional[dict]:
        """Check bar high/low against SL and TP levels. Mutates trade dict for partials."""
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        ts = datetime.fromtimestamp(int(bar["timestamp"]) / 1000, tz=timezone.utc).isoformat()
        is_long = trade["side"] == "long"

        def partial_fill(tp_num: int, price: float, pct: float):
            qty = trade["qty"] * pct
            fee = price * qty * 0.001
            pnl = (price - trade["entry_price"]) * qty * (1 if is_long else -1)
            trade["realized_pnl"] += pnl - fee
            trade["fees"] += fee
            trade["exit_qty"] += qty
            trade[f"tp{tp_num}_filled"] = True
            trade[f"tp{tp_num}_price_filled"] = price
            if tp_num == 1:
                trade["stop_loss"] = trade["entry_price"]  # BE

        # SL check (highest priority)
        sl = trade["stop_loss"]
        if sl:
            sl_hit = (low <= sl) if is_long else (high >= sl)
            if sl_hit:
                remaining = trade["qty"] - trade["exit_qty"]
                fee = sl * remaining * 0.001
                pnl = (sl - trade["entry_price"]) * remaining * (1 if is_long else -1)
                trade["realized_pnl"] += pnl - fee
                trade["fees"] += fee
                trade["net_pnl"] = trade["realized_pnl"]
                trade["exit_price"] = sl
                trade["exit_time"] = ts
                trade["exit_reason"] = "stop_loss"
                return trade

        # Trailing stop
        if trade["trailing_active"] and trade["trailing_stop"]:
            hit = (low <= trade["trailing_stop"]) if is_long else (high >= trade["trailing_stop"])
            if hit:
                price = trade["trailing_stop"]
                remaining = trade["qty"] - trade["exit_qty"]
                fee = price * remaining * 0.001
                pnl = (price - trade["entry_price"]) * remaining * (1 if is_long else -1)
                trade["realized_pnl"] += pnl - fee
                trade["fees"] += fee
                trade["net_pnl"] = trade["realized_pnl"]
                trade["exit_price"] = price
                trade["exit_time"] = ts
                trade["exit_reason"] = "trailing_stop"
                return trade

        # TP1
        if trade["tp1"] and not trade["tp1_filled"]:
            hit = (high >= trade["tp1"]) if is_long else (low <= trade["tp1"])
            if hit:
                partial_fill(1, trade["tp1"], 0.4)

        # TP2
        if trade["tp2"] and trade["tp1_filled"] and not trade["tp2_filled"]:
            hit = (high >= trade["tp2"]) if is_long else (low <= trade["tp2"])
            if hit:
                partial_fill(2, trade["tp2"], 0.3)

        # TP3 → full exit
        if trade["tp3"] and trade["tp2_filled"] and not trade["tp3_filled"]:
            hit = (high >= trade["tp3"]) if is_long else (low <= trade["tp3"])
            if hit:
                partial_fill(3, trade["tp3"], 0.3)
                trade["net_pnl"] = trade["realized_pnl"]
                trade["exit_price"] = trade["tp3"]
                trade["exit_time"] = ts
                trade["exit_reason"] = "tp3"
                return trade

        # Update trailing ratchet
        if trade["trailing_active"] and trade["trailing_stop"]:
            entry_risk = abs(trade["entry_price"] - (trade.get("_original_sl") or trade["stop_loss"] or trade["entry_price"]))
            offset = entry_risk * 0.5
            new_trail = (close - offset) if is_long else (close + offset)
            if is_long and new_trail > trade["trailing_stop"]:
                trade["trailing_stop"] = new_trail
            elif not is_long and new_trail < trade["trailing_stop"]:
                trade["trailing_stop"] = new_trail

        return None  # trade still open

    def _force_close(self, trade: dict, price: float, ts: str) -> dict:
        remaining = trade["qty"] - trade["exit_qty"]
        fee = price * remaining * 0.001
        is_long = trade["side"] == "long"
        pnl = (price - trade["entry_price"]) * remaining * (1 if is_long else -1)
        trade["realized_pnl"] += pnl - fee
        trade["fees"] += fee
        trade["net_pnl"] = trade["realized_pnl"]
        trade["exit_price"] = price
        trade["exit_time"] = ts
        trade["exit_reason"] = "end_of_test"
        return trade

    def _calc_metrics(self, trades: list[dict], initial: float, final: float) -> dict:
        if not trades:
            return {
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "win_rate": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0,
                "total_pnl": 0.0, "avg_rr": 0.0, "final_balance": final,
                "roi_pct": 0.0, "monthly_pnl": {},
            }

        winners = [t for t in trades if t["net_pnl"] > 0]
        losers  = [t for t in trades if t["net_pnl"] <= 0]
        gross_profit = sum(t["net_pnl"] for t in winners)
        gross_loss   = abs(sum(t["net_pnl"] for t in losers))

        # Max drawdown
        equity = initial
        peak = initial
        max_dd = 0.0
        for t in trades:
            equity += t["net_pnl"]
            if equity > peak:
                peak = equity
            dd = (peak - equity) / max(peak, 1e-9) * 100
            max_dd = max(max_dd, dd)

        # Average R:R (actual PnL / risk taken)
        rr_vals = []
        for t in trades:
            sl = t.get("stop_loss")
            ep = t.get("entry_price", 0)
            if sl and ep and abs(ep - sl) > 1e-10:
                risk_usdt = abs(ep - sl) * t["qty"]
                if risk_usdt > 0:
                    rr_vals.append(t["net_pnl"] / risk_usdt)
        avg_rr = round(float(np.mean(rr_vals)), 3) if rr_vals else 0.0

        # Monthly PnL
        monthly: dict[str, float] = {}
        for t in trades:
            et = t.get("exit_time") or ""
            if et:
                month = et[:7]
                monthly[month] = round(monthly.get(month, 0) + t["net_pnl"], 4)

        return {
            "total_trades": len(trades),
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": round(len(winners) / len(trades) * 100, 2) if trades else 0.0,
            "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
            "max_drawdown": round(max_dd, 2),
            "total_pnl": round(sum(t["net_pnl"] for t in trades), 4),
            "avg_rr": avg_rr,
            "final_balance": round(final, 2),
            "roi_pct": round((final - initial) / max(initial, 1e-9) * 100, 2),
            "monthly_pnl": monthly,
        }

    def _summary(self, t: dict) -> dict:
        qty = float(t.get("qty") or 0.0)
        tp_fills: list[tuple[float, float, str]] = []
        if t.get("tp1_filled") and t.get("tp1_price_filled") is not None:
            tp_fills.append((qty * 0.4, float(t["tp1_price_filled"]), "tp1"))
        if t.get("tp2_filled") and t.get("tp2_price_filled") is not None:
            tp_fills.append((qty * 0.3, float(t["tp2_price_filled"]), "tp2"))
        if t.get("tp3_filled") and t.get("tp3_price_filled") is not None:
            tp_fills.append((qty * 0.3, float(t["tp3_price_filled"]), "tp3"))

        exit_reason = t.get("exit_reason")
        filled_qty = sum(fill_qty for fill_qty, _, _ in tp_fills)
        remaining_qty = max(qty - filled_qty, 0.0)
        final_exit_price = t.get("exit_price")
        if (
            final_exit_price is not None
            and remaining_qty > 1e-10
            and exit_reason in {"stop_loss", "trailing_stop", "end_of_test"}
        ):
            tp_fills.append((remaining_qty, float(final_exit_price), "final"))
        elif final_exit_price is not None and not tp_fills and qty > 0:
            tp_fills.append((qty, float(final_exit_price), "final"))

        avg_exit = None
        exit_path: list[str] = []
        total_exit_qty = sum(fill_qty for fill_qty, _, _ in tp_fills)
        if total_exit_qty > 1e-10:
            weighted_sum = sum(fill_qty * fill_price for fill_qty, fill_price, _ in tp_fills)
            avg_exit = weighted_sum / total_exit_qty
            exit_path = [label.upper() for _, _, label in tp_fills if label != "final"]

        reason_label = exit_reason
        if exit_reason == "stop_loss":
            if t.get("tp2_filled"):
                reason_label = "stop_loss_after_tp1_tp2"
            elif t.get("tp1_filled"):
                reason_label = "stop_loss_after_tp1"
        elif exit_reason == "trailing_stop":
            if t.get("tp2_filled"):
                reason_label = "trailing_stop_after_tp1_tp2"
            elif t.get("tp1_filled"):
                reason_label = "trailing_stop_after_tp1"
        elif exit_reason == "end_of_test":
            if t.get("tp2_filled"):
                reason_label = "end_of_test_after_tp1_tp2"
            elif t.get("tp1_filled"):
                reason_label = "end_of_test_after_tp1"

        return {
            "symbol": t.get("symbol"),
            "side": t.get("side"),
            "entry": t.get("entry_price"),
            "exit": t.get("exit_price"),
            "final_exit": t.get("exit_price"),
            "avg_exit": avg_exit,
            "entry_time": t.get("entry_time"),
            "exit_time": t.get("exit_time"),
            "pnl": round(t.get("net_pnl", 0), 4),
            "reason": t.get("exit_reason"),
            "reason_label": reason_label,
            "exit_path": " -> ".join(exit_path) if exit_path else "final_only",
            "tp_hits": len(exit_path),
            "tp1_filled": t.get("tp1_filled", False),
            "tp2_filled": t.get("tp2_filled", False),
            "tp3_filled": t.get("tp3_filled", False),
            "confidence": t.get("confidence"),
            "strategy_confidence": t.get("strategy_confidence"),
            "ai_confidence": t.get("ai_confidence"),
            "filters_passed": t.get("filters_passed"),
            "scenario": t.get("scenario"),
            "fear_greed": t.get("fear_greed"),
            "btc_dominance": t.get("btc_dominance"),
            "reasoning": t.get("reasoning"),
            "filters_assessment": t.get("filters_assessment"),
            "voltage_filters": t.get("voltage_filters"),
        }

    def stop_session(self, session_id: int):
        self._active[session_id] = False

    async def _persist_backtest_trades(
        self,
        symbol: str,
        market_type: MarketType,
        trades: list[dict],
        klines_map: dict[str, pd.DataFrame],
        session_id: int,
    ) -> None:
        if not trades:
            return

        h1 = klines_map.get("1H", pd.DataFrame())
        async with AsyncSessionLocal() as db:
            for item in trades:
                side = PositionSide.LONG if item["side"] == "long" else PositionSide.SHORT
                ai_signal = item.get("side")
                trade = Trade(
                    mode=TradingMode.BACKTEST,
                    market_type=market_type,
                    symbol=symbol,
                    side=side,
                    status=TradeStatus.CLOSED,
                    entry_price=item["entry_price"],
                    entry_qty=item["qty"],
                    entry_time=datetime.fromisoformat(item["entry_time"]),
                    exit_price=item.get("exit_price"),
                    exit_qty=item.get("exit_qty", item["qty"]),
                    exit_time=datetime.fromisoformat(item["exit_time"]) if item.get("exit_time") else None,
                    stop_loss_price=item.get("stop_loss"),
                    take_profit_1_price=item.get("tp1"),
                    take_profit_2_price=item.get("tp2"),
                    take_profit_3_price=item.get("tp3"),
                    tp1_filled=item.get("tp1_filled", False),
                    tp2_filled=item.get("tp2_filled", False),
                    tp3_filled=item.get("tp3_filled", False),
                    trailing_stop_active=item.get("trailing_active", False),
                    trailing_stop_price=item.get("trailing_stop"),
                    realized_pnl=item.get("realized_pnl", 0.0),
                    unrealized_pnl=0.0,
                    fees_total=item.get("fees", 0.0),
                    net_pnl=item.get("net_pnl", 0.0),
                    leverage=item.get("leverage", 1),
                    ai_signal=AISignal(ai_signal) if ai_signal in [member.value for member in AISignal] else None,
                    ai_confidence=item.get("confidence"),
                    ai_analysis_entry=item.get("reasoning"),
                    ai_filters_snapshot={
                        "filters_passed": item.get("filters_passed", 0),
                        "strategy_confidence": item.get("strategy_confidence"),
                        "ai_confidence": item.get("ai_confidence"),
                        "scenario": item.get("scenario"),
                        "fear_greed": item.get("fear_greed"),
                        "btc_dominance": item.get("btc_dominance"),
                        "filters_assessment": item.get("filters_assessment", {}),
                    },
                    voltage_filters=item.get("voltage_filters", {}),
                    backtest_session_id=session_id,
                )
                db.add(trade)
                await db.flush()

                chart_candles = self._build_trade_chart(h1, item)
                await journal_service.create_or_update(db, trade, chart_candles=chart_candles)

            await db.commit()

    def _build_trade_chart(self, h1: pd.DataFrame, trade: dict) -> list[dict]:
        if h1.empty:
            return []

        try:
            entry_ts = int(datetime.fromisoformat(trade["entry_time"]).timestamp() * 1000)
            exit_raw = trade.get("exit_time") or trade["entry_time"]
            exit_ts = int(datetime.fromisoformat(exit_raw).timestamp() * 1000)
        except (KeyError, TypeError, ValueError):
            return []

        start_ts = entry_ts - (48 * 60 * 60 * 1000)
        end_ts = exit_ts + (48 * 60 * 60 * 1000)
        window = h1[(h1["timestamp"] >= start_ts) & (h1["timestamp"] <= end_ts)].copy()
        if window.empty:
            return []

        if len(window) > 200:
            window = window.iloc[-200:].copy()

        return [
            {
                "timestamp": int(row["timestamp"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
            for _, row in window.iterrows()
        ]


backtest_engine = BacktestEngine()
