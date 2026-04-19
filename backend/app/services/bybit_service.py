"""
Bybit Exchange Service
Handles all interactions with Bybit API (mainnet).
Supports SPOT and FUTURES (linear perpetuals).
"""
from __future__ import annotations

import asyncio
from typing import Optional, Any
from datetime import datetime, timezone
from loguru import logger

from pybit.unified_trading import HTTP, WebSocket
from app.config import settings


class BybitService:
    """
    Bybit API wrapper for VOLTAGE trading bot.
    All methods are async-compatible (run_in_executor for blocking calls).
    """

    SPOT = "spot"
    LINEAR = "linear"  # USDT-margined futures

    def __init__(self):
        self._configure_client(settings.BYBIT_API_KEY, settings.BYBIT_API_SECRET)
        self._loop = None

    def _configure_client(self, api_key: str, api_secret: str) -> None:
        self.client = HTTP(
            testnet=settings.BYBIT_TESTNET,
            api_key=api_key,
            api_secret=api_secret,
        )

    def reload_credentials(self, api_key: str, api_secret: str) -> None:
        self._configure_client(api_key, api_secret)

    async def _call(self, fn, **kwargs) -> dict:
        """Run a blocking pybit call in the thread pool."""
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: fn(**kwargs)),
                timeout=settings.BYBIT_REQUEST_TIMEOUT,
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"Bybit request timed out after {settings.BYBIT_REQUEST_TIMEOUT}s"
            ) from exc
        if result.get("retCode", -1) != 0:
            msg = result.get("retMsg", "Unknown Bybit error")
            raise RuntimeError(f"Bybit API error: {msg} | {result}")
        return result.get("result", {})

    # ─── ACCOUNT ────────────────────────────────────────────

    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict:
        """Get full wallet balance."""
        data = await self._call(
            self.client.get_wallet_balance,
            accountType=account_type,
        )
        coins = {}
        for acc in data.get("list", []):
            for coin in acc.get("coin", []):
                symbol = coin.get("coin", "")
                coins[symbol] = {
                    "equity": float(coin.get("equity", 0)),
                    "available": float(coin.get("availableToWithdraw", 0)),
                    "unrealized_pnl": float(coin.get("unrealisedPnl", 0)),
                    "wallet_balance": float(coin.get("walletBalance", 0)),
                }
        return coins

    async def get_usdt_balance(self) -> float:
        """Get available USDT balance."""
        balances = await self.get_wallet_balance()
        return balances.get("USDT", {}).get("available", 0.0)

    # ─── MARKET DATA ────────────────────────────────────────

    async def get_tickers(self, category: str = "spot") -> list[dict]:
        """Get all available tickers for a category."""
        data = await self._call(self.client.get_tickers, category=category)
        return data.get("list", [])

    async def get_spot_pairs(self) -> list[str]:
        """Get all spot USDT pairs."""
        tickers = await self.get_tickers("spot")
        return sorted([t["symbol"] for t in tickers if t["symbol"].endswith("USDT")])

    async def get_futures_pairs(self) -> list[str]:
        """Get all linear futures USDT pairs."""
        tickers = await self.get_tickers("linear")
        return sorted([t["symbol"] for t in tickers if t["symbol"].endswith("USDT")])

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        category: str = "spot",
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[dict]:
        """
        Get OHLCV klines.
        interval: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M
        """
        kwargs = dict(symbol=symbol, interval=interval, category=category, limit=limit)
        if start_time:
            kwargs["start"] = start_time
        if end_time:
            kwargs["end"] = end_time

        data = await self._call(self.client.get_kline, **kwargs)
        raw = data.get("list", [])
        # Bybit returns: [startTime, open, high, low, close, volume, turnover]
        candles = []
        for c in reversed(raw):  # oldest first
            candles.append({
                "timestamp": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            })
        return candles

    async def get_orderbook(self, symbol: str, category: str = "spot", limit: int = 50) -> dict:
        """Get orderbook (bids and asks)."""
        data = await self._call(
            self.client.get_orderbook,
            symbol=symbol,
            category=category,
            limit=limit,
        )
        return {
            "bids": data.get("b", []),
            "asks": data.get("a", []),
            "timestamp": data.get("ts", 0),
        }

    async def get_ticker_info(self, symbol: str, category: str = "spot") -> dict:
        """Get single ticker with 24h stats."""
        data = await self._call(
            self.client.get_tickers,
            symbol=symbol,
            category=category,
        )
        items = data.get("list", [])
        return items[0] if items else {}

    async def get_instruments_info(self, symbol: str, category: str = "spot") -> dict:
        """Get instrument details (lot size, min qty, tick size)."""
        data = await self._call(
            self.client.get_instruments_info,
            symbol=symbol,
            category=category,
        )
        items = data.get("list", [])
        return items[0] if items else {}

    # ─── ORDER MANAGEMENT ────────────────────────────────────

    async def place_order(
        self,
        symbol: str,
        side: str,  # "Buy" or "Sell"
        order_type: str,  # "Market" or "Limit"
        qty: float,
        category: str = "spot",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        position_idx: int = 0,  # 0=one-way, 1=long, 2=short
        reduce_only: bool = False,
        time_in_force: str = "GTC",
        order_link_id: Optional[str] = None,
        trigger_price: Optional[float] = None,
        trigger_by: str = "LastPrice",
    ) -> dict:
        """Place an order on Bybit."""
        kwargs: dict[str, Any] = dict(
            symbol=symbol,
            side=side,
            orderType=order_type,
            qty=str(qty),
            category=category,
            timeInForce=time_in_force,
        )
        if price and order_type == "Limit":
            kwargs["price"] = str(price)
        if stop_loss:
            kwargs["stopLoss"] = str(stop_loss)
        if take_profit:
            kwargs["takeProfit"] = str(take_profit)
        if position_idx:
            kwargs["positionIdx"] = position_idx
        if reduce_only:
            kwargs["reduceOnly"] = True
        if order_link_id:
            kwargs["orderLinkId"] = order_link_id
        if trigger_price:
            kwargs["triggerPrice"] = str(trigger_price)
            kwargs["triggerBy"] = trigger_by

        data = await self._call(self.client.place_order, **kwargs)
        logger.info(f"Order placed: {symbol} {side} {qty} @ {price or 'market'} | ID: {data.get('orderId')}")
        return data

    async def cancel_order(self, symbol: str, order_id: str, category: str = "spot") -> dict:
        """Cancel an open order."""
        return await self._call(
            self.client.cancel_order,
            symbol=symbol,
            orderId=order_id,
            category=category,
        )

    async def amend_order(
        self,
        symbol: str,
        order_id: str,
        category: str = "spot",
        price: Optional[float] = None,
        qty: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        """Modify an existing order."""
        kwargs: dict[str, Any] = dict(symbol=symbol, orderId=order_id, category=category)
        if price:
            kwargs["price"] = str(price)
        if qty:
            kwargs["qty"] = str(qty)
        if stop_loss:
            kwargs["stopLoss"] = str(stop_loss)
        if take_profit:
            kwargs["takeProfit"] = str(take_profit)
        return await self._call(self.client.amend_order, **kwargs)

    async def get_open_orders(self, symbol: Optional[str] = None, category: str = "spot") -> list[dict]:
        """Get all open orders."""
        kwargs: dict[str, Any] = dict(category=category)
        if symbol:
            kwargs["symbol"] = symbol
        data = await self._call(self.client.get_open_orders, **kwargs)
        return data.get("list", [])

    async def get_order_history(
        self,
        symbol: Optional[str] = None,
        category: str = "spot",
        limit: int = 50,
    ) -> list[dict]:
        """Get order history."""
        kwargs: dict[str, Any] = dict(category=category, limit=limit)
        if symbol:
            kwargs["symbol"] = symbol
        data = await self._call(self.client.get_order_history, **kwargs)
        return data.get("list", [])

    # ─── POSITIONS (FUTURES) ─────────────────────────────────

    async def get_positions(self, symbol: Optional[str] = None, category: str = "linear") -> list[dict]:
        """Get open futures positions."""
        kwargs: dict[str, Any] = dict(category=category)
        if symbol:
            kwargs["symbol"] = symbol
        data = await self._call(self.client.get_positions, **kwargs)
        return data.get("list", [])

    async def set_leverage(self, symbol: str, leverage: int, category: str = "linear") -> dict:
        """Set leverage for a futures symbol."""
        return await self._call(
            self.client.set_leverage,
            symbol=symbol,
            buyLeverage=str(leverage),
            sellLeverage=str(leverage),
            category=category,
        )

    async def set_trading_stop(
        self,
        symbol: str,
        position_idx: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop: Optional[float] = None,
        category: str = "linear",
    ) -> dict:
        """Set SL/TP/Trailing stop on a position."""
        kwargs: dict[str, Any] = dict(
            symbol=symbol,
            positionIdx=position_idx,
            category=category,
        )
        if stop_loss:
            kwargs["stopLoss"] = str(stop_loss)
        if take_profit:
            kwargs["takeProfit"] = str(take_profit)
        if trailing_stop:
            kwargs["trailingStop"] = str(trailing_stop)
        return await self._call(self.client.set_trading_stop, **kwargs)

    async def get_closed_pnl(self, symbol: Optional[str] = None, limit: int = 50, category: str = "linear") -> list[dict]:
        """Get closed PnL records."""
        kwargs: dict[str, Any] = dict(category=category, limit=limit)
        if symbol:
            kwargs["symbol"] = symbol
        data = await self._call(self.client.get_closed_pnl, **kwargs)
        return data.get("list", [])

    async def get_trade_history(self, symbol: Optional[str] = None, limit: int = 50, category: str = "spot") -> list[dict]:
        """Get execution/trade history."""
        kwargs: dict[str, Any] = dict(category=category, limit=limit)
        if symbol:
            kwargs["symbol"] = symbol
        data = await self._call(self.client.get_executions, **kwargs)
        return data.get("list", [])

    # ─── MARKET CONTEXT (for VOLTAGE Filter 1) ───────────────

    async def get_btc_dominance(self) -> float:
        """
        BTC dominance is not directly available via Bybit.
        Returns a reasonable estimate based on BTC/total market cap.
        For production: integrate CoinGlass or CoinMarketCap API.
        """
        # Placeholder — integrate external API in production
        return 50.0

    async def get_fear_greed_index(self) -> int:
        """
        Fetch Fear & Greed index.
        Uses alternative.me API — no key required.
        """
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://api.alternative.me/fng/?limit=1")
                data = resp.json()
                return int(data["data"][0]["value"])
        except Exception as e:
            logger.warning(f"Fear & Greed fetch failed: {e}")
            return 50

    async def get_quantity_precision(self, symbol: str, category: str = "spot") -> tuple[int, int]:
        """Get qty and price precision for a symbol."""
        info = await self.get_instruments_info(symbol, category)
        lot_filter = info.get("lotSizeFilter", {})
        price_filter = info.get("priceFilter", {})
        qty_step = lot_filter.get("qtyStep", "0.001")
        tick_size = price_filter.get("tickSize", "0.01")
        qty_decimals = len(qty_step.rstrip("0").split(".")[-1]) if "." in qty_step else 0
        price_decimals = len(tick_size.rstrip("0").split(".")[-1]) if "." in tick_size else 2
        return qty_decimals, price_decimals

    async def calculate_position_qty(
        self,
        symbol: str,
        entry_price: float,
        risk_amount_usdt: float,
        stop_loss_price: float,
        category: str = "spot",
        leverage: int = 1,
    ) -> float:
        """
        Calculate position size based on VOLTAGE risk management.
        risk_amount_usdt = balance * risk_percent (e.g., 2%)
        """
        risk_per_unit = abs(entry_price - stop_loss_price)
        if risk_per_unit == 0:
            return 0.0
        qty = (risk_amount_usdt * leverage) / risk_per_unit
        qty_dec, _ = await self.get_quantity_precision(symbol, category)
        return round(qty, qty_dec)


# Global singleton
bybit_service = BybitService()
