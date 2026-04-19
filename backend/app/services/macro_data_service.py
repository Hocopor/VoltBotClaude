from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
from loguru import logger

from app.config import settings


class MacroDataService:
    """Historical macro context for backtests and runtime market filters."""

    def __init__(self) -> None:
        self._coinlore_url = "https://api.coinlore.net/api/global/"
        self._alternative_fng_url = "https://api.alternative.me/fng/"
        self._cmc_historical_url = "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/historical"

    async def get_current_btc_dominance(self) -> float:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self._coinlore_url)
                response.raise_for_status()
                payload = response.json()
                if payload and isinstance(payload, list):
                    return float(payload[0].get("btc_d", 50.0))
        except Exception as exc:
            logger.warning(f"BTC dominance fetch failed, falling back to 50.0: {exc}")
        return 50.0

    async def get_historical_context(self, start: datetime, end: datetime) -> dict:
        fear_greed = await self._get_historical_fear_greed(start, end)
        btc_dominance, btc_source = await self._get_historical_btc_dominance(start, end)
        return {
            "fear_greed": fear_greed,
            "btc_dominance": btc_dominance,
            "btc_dominance_source": btc_source,
        }

    async def _get_historical_fear_greed(self, start: datetime, end: datetime) -> dict[str, int]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    self._alternative_fng_url,
                    params={"limit": 0, "format": "json"},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning(f"Historical Fear & Greed fetch failed, using neutral fallback: {exc}")
            return self._fill_daily_series(start, end, 50)

        values: dict[str, int] = {}
        for item in payload.get("data", []):
            try:
                ts = int(item["timestamp"])
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                value = int(item["value"])
            except (KeyError, TypeError, ValueError):
                continue
            values[dt] = value

        normalized = self._normalize_daily_series(start, end, values, default=50)
        return {key: int(value) for key, value in normalized.items()}

    async def _get_historical_btc_dominance(
        self,
        start: datetime,
        end: datetime,
    ) -> tuple[dict[str, float], str]:
        if settings.COINMARKETCAP_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(
                        self._cmc_historical_url,
                        params={
                            "time_start": start.astimezone(timezone.utc).isoformat(),
                            "time_end": end.astimezone(timezone.utc).isoformat(),
                            "interval": "daily",
                            "convert": "USD",
                        },
                        headers={"X-CMC_PRO_API_KEY": settings.COINMARKETCAP_API_KEY},
                    )
                    response.raise_for_status()
                    payload = response.json()
            except Exception as exc:
                logger.warning(f"Historical BTC dominance fetch failed from CMC, using fallback: {exc}")
            else:
                quotes = payload.get("data", {}).get("quotes", [])
                values: dict[str, float] = {}
                for quote in quotes:
                    timestamp = quote.get("timestamp")
                    dominance = quote.get("btc_dominance")
                    if not timestamp or dominance is None:
                        continue
                    try:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date().isoformat()
                        values[dt] = float(dominance)
                    except (TypeError, ValueError):
                        continue
                if values:
                    return self._normalize_daily_series(start, end, values, default=50.0), "coinmarketcap_historical"

        current = await self.get_current_btc_dominance()
        logger.warning(
            "Historical BTC dominance unavailable, repeating current value in backtest fallback. "
            "Set COINMARKETCAP_API_KEY in .env for real historical BTC dominance."
        )
        return self._fill_daily_series(start, end, current), "coinlore_current_repeated_fallback"

    def value_for_timestamp(
        self,
        series: dict[str, float | int],
        timestamp_ms: int,
        default: float | int,
    ) -> float | int:
        day_key = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date().isoformat()
        return series.get(day_key, default)

    def _normalize_daily_series(
        self,
        start: datetime,
        end: datetime,
        values: dict[str, float | int],
        *,
        default: float | int,
    ) -> dict[str, float | int]:
        normalized: dict[str, float | int] = {}
        current = start.astimezone(timezone.utc).date()
        end_day = end.astimezone(timezone.utc).date()
        last_value: float | int = default

        while current <= end_day:
            key = current.isoformat()
            if key in values:
                last_value = values[key]
            normalized[key] = last_value
            current += timedelta(days=1)

        return normalized

    def _fill_daily_series(
        self,
        start: datetime,
        end: datetime,
        value: float | int,
    ) -> dict[str, float | int]:
        values: dict[str, float | int] = {}
        current = start.astimezone(timezone.utc).date()
        end_day = end.astimezone(timezone.utc).date()
        while current <= end_day:
            values[current.isoformat()] = value
            current += timedelta(days=1)
        return values


macro_data_service = MacroDataService()
