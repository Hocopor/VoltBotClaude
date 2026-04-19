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
    BacktestSession, Trade, TradingMode, MarketType
)
from app.services.strategy.voltage_strategy import VoltageStrategy, Signal
from app.services.bybit_service import bybit_service
from app.database import AsyncSessionLocal


class BacktestEngine:
    def __init__(self):
        self._active: dict[int, bool] = {}

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
            balance = initial_balance
            equity_curve = [{"time": start_date.isoformat(), "equity": balance}]
            total = len(symbols)

            for idx, symbol in enumerate(symbols):
                if not self._active.get(session_id):
                    break
                logger.info(f"Backtest {symbol} ({idx+1}/{total}) [{session_id}]")

                klines_map = await self._fetch_historical(symbol, cat, start_date, end_date)
                if not klines_map or "4H" not in klines_map or len(klines_map["4H"]) < 60:
                    logger.warning(f"Insufficient data for {symbol}")
                    continue

                sym_trades = await self._simulate_symbol(
                    symbol=symbol,
                    market_type=market_type,
                    klines_map=klines_map,
                    start_date=start_date,
                    end_date=end_date,
                    balance=balance,
                    risk_pct=risk_per_trade_pct,
                    conf_threshold=ai_confidence_threshold,
                    leverage=leverage,
                    session_id=session_id,
                )

                for t in sym_trades:
                    balance += t["net_pnl"]
                    equity_curve.append({"time": t["exit_time"] or "", "equity": round(balance, 2)})

                all_trades.extend(sym_trades)

                progress = (idx + 1) / total
                async with AsyncSessionLocal() as db:
                    r = await db.execute(select(BacktestSession).where(BacktestSession.id == session_id))
                    s = r.scalar_one_or_none()
                    if s:
                        s.progress = progress
                        await db.commit()

            metrics = self._calc_metrics(all_trades, initial_balance, balance)
            metrics["equity_curve"] = equity_curve

            async with AsyncSessionLocal() as db:
                r = await db.execute(select(BacktestSession).where(BacktestSession.id == session_id))
                s = r.scalar_one_or_none()
                if s:
                    s.status = "done"
                    s.final_balance = balance
                    s.total_trades = metrics["total_trades"]
                    s.winning_trades = metrics["winning_trades"]
                    s.losing_trades = metrics["losing_trades"]
                    s.win_rate = metrics["win_rate"]
                    s.profit_factor = metrics["profit_factor"]
                    s.max_drawdown = metrics["max_drawdown"]
                    s.total_pnl = metrics["total_pnl"]
                    s.avg_rr = metrics["avg_rr"]
                    s.progress = 1.0
                    s.results_data = {
                        "equity_curve": equity_curve,
                        "monthly_pnl": metrics.get("monthly_pnl", {}),
                        "trades_summary": [self._summary(t) for t in all_trades[:500]],
                    }
                    s.completed_at = datetime.now(timezone.utc)
                    await db.commit()

            from app.websocket.manager import manager, Events
            await manager.broadcast(Events.BACKTEST_COMPLETE, {
                "session_id": session_id,
                "session_name": "",
                "total_trades": metrics["total_trades"],
                "win_rate": metrics["win_rate"],
                "total_pnl": metrics["total_pnl"],
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
        start_date: datetime,
        end_date: datetime,
        balance: float,
        risk_pct: float,
        conf_threshold: float,
        leverage: int,
        session_id: int,
    ) -> list[dict]:
        trades: list[dict] = []
        h4 = klines_map["4H"]
        is_major = symbol.replace("USDT", "") in {"BTC", "ETH"}
        strategy = VoltageStrategy(symbol, is_major=is_major)
        open_trade: Optional[dict] = None
        min_bars = 60

        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)

        for i in range(min_bars, len(h4)):
            if not self._active.get(session_id):
                break

            bar = h4.iloc[i]
            ts = int(bar["timestamp"])
            if ts < start_ms or ts > end_ms:
                continue

            current_close = float(bar["close"])

            # Check existing trade first
            if open_trade:
                closed = self._check_exit(open_trade, bar)
                if closed:
                    trades.append(closed)
                    open_trade = None
                continue

            # Only one position at a time per symbol
            h4_slice = h4.iloc[max(0, i - 200): i + 1].copy()
            w_slice = klines_map.get("1W", pd.DataFrame())
            d_slice = klines_map.get("1D", pd.DataFrame())
            h1_slice = klines_map.get("1H", pd.DataFrame())

            if len(h4_slice) < min_bars:
                continue

            try:
                sig = strategy.run_all_filters(
                    ohlcv_1w=w_slice, ohlcv_1d=d_slice,
                    ohlcv_4h=h4_slice, ohlcv_1h=h1_slice,
                    btc_dominance=50.0, fear_greed=50,
                )
            except Exception:
                continue

            if (
                sig.signal in [Signal.LONG, Signal.SHORT]
                and sig.confidence >= conf_threshold
                and sig.filters_passed >= 4
                and sig.entry_price
                and sig.stop_loss
            ):
                risk_amount = balance * (risk_pct / 100)
                risk_per_unit = abs(sig.entry_price - sig.stop_loss)
                if risk_per_unit < 1e-10:
                    continue
                qty = (risk_amount * leverage) / risk_per_unit

                open_trade = {
                    "symbol": symbol,
                    "market_type": market_type.value,
                    "side": sig.signal.value,
                    "entry_price": current_close,
                    "entry_time": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                    "qty": qty,
                    "stop_loss": sig.stop_loss,
                    "tp1": sig.take_profit_1,
                    "tp2": sig.take_profit_2,
                    "tp3": sig.take_profit_3,
                    "tp1_filled": False, "tp2_filled": False, "tp3_filled": False,
                    "tp1_price_filled": None, "tp2_price_filled": None, "tp3_price_filled": None,
                    "trailing_stop": None, "trailing_active": False,
                    "realized_pnl": 0.0, "fees": 0.0, "exit_qty": 0.0,
                    "confidence": sig.confidence,
                    "filters_passed": sig.filters_passed,
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

        return trades

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
        return {
            "symbol": t.get("symbol"),
            "side": t.get("side"),
            "entry": t.get("entry_price"),
            "exit": t.get("exit_price"),
            "entry_time": t.get("entry_time"),
            "exit_time": t.get("exit_time"),
            "pnl": round(t.get("net_pnl", 0), 4),
            "reason": t.get("exit_reason"),
            "confidence": t.get("confidence"),
            "filters_passed": t.get("filters_passed"),
        }

    def stop_session(self, session_id: int):
        self._active[session_id] = False


backtest_engine = BacktestEngine()
