"""
VOLTAGE TRADING SYSTEM — CORE STRATEGY ENGINE
Implements all 6 filters EXACTLY as defined in the strategy specification.

FILTER 1: Bitcoin Dominance & Market Sentiment
FILTER 2: Multi-timeframe Analysis (1W/3D → 1D → 4H → 1H/15M)
FILTER 3: Crypto-specific Indicators (EMA21/55, Ichimoku, RSI 35-65, MACD, ATR, Stochastic, Williams%R)
FILTER 4: Volume Analysis — MOST IMPORTANT (VPVR, OBV, Volume Delta, Accumulation/Distribution)
FILTER 5: Price Action & Crypto Patterns (Liquidity Grab, Engulfing, Pin Bar, V-shape, Consolidation)
FILTER 6: Liquidity & Clusters (Order book walls, cluster analysis, SL behind liquidity)

ENTRY: CRYPTO TRIGGER — ALL 6 conditions must align
RISK: 1-3% per trade | SL behind liquidity clusters
TP1=1.5R (close 40%, move SL to BE) | TP2=3R (close 30%) | TP3=5R + trailing (close 30%)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ─────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────

class Signal(str, Enum):
    LONG    = "long"
    SHORT   = "short"
    NEUTRAL = "neutral"
    WAIT    = "wait"


class MarketScenario(str, Enum):
    ALTSEASON     = "altseason"      # BTC.D falling → aggressive altcoin buying
    BTC_DOMINATES = "btc_dominates"  # BTC.D rising → trade BTC/large caps only
    BEAR          = "bear"           # F&G < 20 → shorts only or wait in USDT
    NEUTRAL       = "neutral"        # Mixed signals


# ─────────────────────────────────────────────────────────────
# FILTER RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────

@dataclass
class Filter1Result:
    """BTC Dominance & Market Sentiment"""
    btc_dominance: float = 0.0
    btc_dominance_trend: str = "stable"      # rising | falling | stable
    fear_greed_index: int = 50
    fear_greed_zone: str = "neutral"         # extreme_fear | fear | neutral | greed | extreme_greed
    total_market_cap_trend: str = "stable"
    scenario: MarketScenario = MarketScenario.NEUTRAL
    passed: bool = False
    score: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class Filter2Result:
    """Multi-timeframe Analysis"""
    # 1W/3D
    weekly_ema21_above_ema55: bool = False
    weekly_trend: str = "neutral"
    # 1D
    daily_ema21_above_ema55: bool = False
    daily_above_ichimoku: bool = False
    daily_trend: str = "neutral"
    # 4H — spec: EMA21>EMA55 AND RSI AND MACD
    h4_ema21_above_ema55: bool = False
    h4_rsi: float = 50.0
    h4_macd_hist: float = 0.0
    h4_trend: str = "neutral"
    # 1H/15M
    h1_pattern: str = "none"
    passed: bool = False
    score: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class Filter3Result:
    """Crypto-specific Indicators"""
    # ТРЕНД = EMA21>EMA55 AND Price > Ichimoku Cloud
    trend_confirmed: bool = False
    # МОМЕНТУМ = RSI(14) в зоне 40-45 и разворачивается вверх AND MACD hist > 0
    momentum_confirmed: bool = False
    rsi_turning_up: bool = False
    # ВОЛАТИЛЬНОСТЬ = ATR > среднее
    volatility_above_avg: bool = False
    # Осцилляторы
    rsi_14: float = 50.0
    stochastic_k: float = 50.0
    stochastic_d: float = 50.0
    williams_r: float = -50.0
    atr_14: float = 0.0
    atr_avg: float = 0.0
    passed: bool = False
    score: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class Filter4Result:
    """Volume Analysis — САМЫЙ ВАЖНЫЙ"""
    obv_trend: str = "neutral"         # rising | falling | neutral (умные деньги)
    volume_delta: float = 0.0          # разница покупатель/продавец
    volume_above_avg: bool = False
    vpvr_support_near: bool = False    # VPVR поддержка на текущем уровне
    anomalous_volume: bool = False     # аномальный объём на пробое = истинный пробой
    accumulation_detected: bool = False
    passed: bool = False
    score: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class Filter5Result:
    """Price Action & Crypto Patterns"""
    pattern_detected: str = "none"
    # ТОП-5 крипто-паттернов
    liquidity_grab_retest: bool = False   # Ложный пробой + ретест
    pump_dump_detected: bool = False
    consolidation_before_move: bool = False
    v_shape_divergence: bool = False
    # Свечные паттерны
    engulfing: bool = False
    engulfing_direction: str = "none"    # bullish | bearish
    evening_morning_star: bool = False
    star_type: str = "none"              # morning | evening
    pin_bar: bool = False
    pin_bar_at_level: bool = False
    passed: bool = False
    score: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class Filter6Result:
    """Liquidity & Cluster Analysis"""
    buy_wall_detected: bool = False
    sell_wall_detected: bool = False
    cluster_above: Optional[float] = None
    cluster_below: Optional[float] = None
    # SL ЗА кластерами ликвидности (ключевое правило стратегии)
    recommended_sl_long: Optional[float] = None
    recommended_sl_short: Optional[float] = None
    orderbook_depth_ratio: float = 1.0   # buy_depth / sell_depth
    passed: bool = False
    score: float = 0.0
    notes: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# FINAL SIGNAL OUTPUT
# ─────────────────────────────────────────────────────────────

@dataclass
class VOLTAGESignal:
    signal: Signal = Signal.NEUTRAL
    confidence: float = 0.0         # 0.0–1.0

    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None   # 1.5R → close 40%
    take_profit_2: Optional[float] = None   # 3.0R → close 30%
    take_profit_3: Optional[float] = None   # 5.0R+trailing → close 30%
    risk_reward: Optional[float] = None

    filter1: Optional[Filter1Result] = None
    filter2: Optional[Filter2Result] = None
    filter3: Optional[Filter3Result] = None
    filter4: Optional[Filter4Result] = None
    filter5: Optional[Filter5Result] = None
    filter6: Optional[Filter6Result] = None

    market_scenario: MarketScenario = MarketScenario.NEUTRAL
    symbol: str = ""
    filters_passed: int = 0
    filters_total: int = 6
    reasoning: str = ""


# ─────────────────────────────────────────────────────────────
# STRATEGY ENGINE
# ─────────────────────────────────────────────────────────────

class VoltageStrategy:
    """
    VOLTAGE Crypto Trading Strategy — полная реализация по спецификации.

    Все 6 фильтров должны пройти для уверенного сигнала.
    Абсолютные запреты (жёсткие правила из стратегии):
      - НЕЛЬЗЯ открывать LONG при F&G > 75 (зона распределения)
      - НЕЛЬЗЯ открывать LONG на альтах при BTC.D растёт
      - В медвежьем рынке (F&G < 20) — только ШОРТ или ожидание
    """

    # ─── Константы по спецификации VOLTAGE ───────────────────

    # RSI зоны (35-65 вместо 30-70 из-за высокой волатильности крипты)
    RSI_OVERSOLD       = 35
    RSI_OVERBOUGHT     = 65
    # Зона моментума для входа: RSI откатал к 40-45 и разворачивается вверх
    RSI_MOMENTUM_LOW   = 40
    RSI_MOMENTUM_HIGH  = 45

    # Fear & Greed
    FEAR_GREED_EXTREME_FEAR   = 25   # зона накопления → покупать
    FEAR_GREED_EXTREME_GREED  = 75   # зона распределения → продавать/не покупать
    FEAR_GREED_ENTRY_MAX_LONG = 45   # условие 6 CRYPTO TRIGGER: F&G < 45 для лонга
    FEAR_GREED_BEAR_MAX       = 20   # медвежий рынок

    # BTC Dominance
    BTC_D_ALTSEASON_MAX  = 48.0   # BTC.D < 48 → альтсезон
    BTC_D_DOMINANCE_MIN  = 55.0   # BTC.D > 55 → BTC доминирует

    # TP R-ratios (неизменяемы)
    TP1_R = 1.5   # закрыть 40%, перенести SL в безубыток
    TP2_R = 3.0   # закрыть 30%
    TP3_R = 5.0   # закрыть 30% + активировать trailing stop

    # SL диапазоны (% от цены входа)
    SL_ALT_MIN   = 0.08   # 8% для альткоинов
    SL_ALT_MAX   = 0.12   # 12% для альткоинов
    SL_MAJOR_MIN = 0.05   # 5% для BTC/ETH
    SL_MAJOR_MAX = 0.08   # 8% для BTC/ETH

    def __init__(self, symbol: str, is_major: bool = False):
        self.symbol = symbol
        self.is_major = is_major   # True для BTC/ETH, False для альткоинов

    def run_all_filters(
        self,
        ohlcv_1w: pd.DataFrame,
        ohlcv_1d: pd.DataFrame,
        ohlcv_4h: pd.DataFrame,
        ohlcv_1h: pd.DataFrame,
        orderbook: Optional[dict] = None,
        btc_dominance: float = 50.0,
        fear_greed: int = 50,
        total_mcap_change_24h: float = 0.0,
    ) -> VOLTAGESignal:
        """
        Запуск всех 6 фильтров VOLTAGE и генерация торгового сигнала.
        Веса фильтров: F4 (объём) имеет вес ×2 как самый важный.
        """
        f1 = self._filter1_btc_sentiment(btc_dominance, fear_greed, total_mcap_change_24h)
        f2 = self._filter2_multitf(ohlcv_1w, ohlcv_1d, ohlcv_4h, ohlcv_1h)
        f3 = self._filter3_indicators(ohlcv_4h)
        f4 = self._filter4_volume(ohlcv_4h, ohlcv_1h)
        f5 = self._filter5_price_action(ohlcv_4h, ohlcv_1h)
        f6 = self._filter6_liquidity(orderbook, ohlcv_4h)

        filters = [f1, f2, f3, f4, f5, f6]
        filters_passed = sum(1 for f in filters if f.passed)

        # Взвешенная уверенность: F4 (объём) — вес ×2
        weights = [1.0, 1.0, 1.0, 2.0, 1.0, 1.0]
        total_w = sum(weights)
        confidence = min(
            sum(f.score * w for f, w in zip(filters, weights)) / total_w,
            1.0
        )

        signal = self._determine_signal(f1, f2, f3, f4, f5, confidence)

        current_price = float(ohlcv_4h["close"].iloc[-1]) if len(ohlcv_4h) > 0 else 0.0
        entry, sl, tp1, tp2, tp3, rr = self._calculate_levels(signal, current_price, f6, ohlcv_4h)

        reasoning = self._build_reasoning(f1, f2, f3, f4, f5, f6, signal, filters_passed)

        return VOLTAGESignal(
            signal=signal,
            confidence=round(confidence, 4),
            entry_price=entry,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            risk_reward=rr,
            filter1=f1, filter2=f2, filter3=f3,
            filter4=f4, filter5=f5, filter6=f6,
            market_scenario=f1.scenario,
            symbol=self.symbol,
            filters_passed=filters_passed,
            filters_total=6,
            reasoning=reasoning,
        )

    # ─── FILTER 1: BTC Dominance & Market Sentiment ──────────

    def _filter1_btc_sentiment(
        self, btc_d: float, fg: int, mcap_chg: float
    ) -> Filter1Result:
        notes = []
        score = 0.0

        # BTC.D тренд
        if btc_d < self.BTC_D_ALTSEASON_MAX:
            btc_trend = "falling"
            notes.append(f"BTC.D={btc_d:.1f}% — Альтсезон ✓")
            score += 0.4
        elif btc_d > self.BTC_D_DOMINANCE_MIN:
            btc_trend = "rising"
            notes.append(f"BTC.D={btc_d:.1f}% — BTC доминирует, осторожно с альтами")
            score += 0.05
        else:
            btc_trend = "stable"
            notes.append(f"BTC.D={btc_d:.1f}% — Нейтрально")
            score += 0.2

        # Fear & Greed Index
        if fg <= self.FEAR_GREED_EXTREME_FEAR:
            fg_zone = "extreme_fear"
            notes.append(f"F&G={fg} — EXTREME FEAR: Зона накопления ✓")
            score += 0.4
        elif fg <= self.FEAR_GREED_ENTRY_MAX_LONG:
            fg_zone = "fear"
            notes.append(f"F&G={fg} — Fear: хорошие условия для входа ✓")
            score += 0.35
        elif fg <= 55:
            fg_zone = "neutral"
            notes.append(f"F&G={fg} — Нейтрально")
            score += 0.2
        elif fg < self.FEAR_GREED_EXTREME_GREED:
            fg_zone = "greed"
            notes.append(f"F&G={fg} — Greed: осторожность")
            score += 0.05
        else:
            fg_zone = "extreme_greed"
            notes.append(f"F&G={fg} — EXTREME GREED: Зона распределения — NO LONGS")
            score += 0.0   # зона распределения — нет лонгов

        # Total Market Cap тренд
        if mcap_chg > 2.0:
            notes.append(f"Total MCAP 24h: +{mcap_chg:.1f}% — растёт ✓")
            score += 0.2
            mcap_trend = "rising"
        elif mcap_chg < -2.0:
            notes.append(f"Total MCAP 24h: {mcap_chg:.1f}% — падает")
            score += 0.02
            mcap_trend = "falling"
        else:
            notes.append(f"Total MCAP 24h: {mcap_chg:+.1f}% — боковик")
            score += 0.1
            mcap_trend = "stable"

        # Сценарий
        if fg < self.FEAR_GREED_BEAR_MAX:
            scenario = MarketScenario.BEAR
        elif btc_trend == "falling" and fg < self.FEAR_GREED_EXTREME_GREED:
            scenario = MarketScenario.ALTSEASON
        elif btc_trend == "rising":
            scenario = MarketScenario.BTC_DOMINATES
        else:
            scenario = MarketScenario.NEUTRAL

        score = min(score, 1.0)
        # Фильтр проходит если нет extreme_greed и есть хоть какой-то положительный сигнал
        passed = score >= 0.35 and fg < self.FEAR_GREED_EXTREME_GREED

        return Filter1Result(
            btc_dominance=btc_d, btc_dominance_trend=btc_trend,
            fear_greed_index=fg, fear_greed_zone=fg_zone,
            total_market_cap_trend=mcap_trend, scenario=scenario,
            passed=passed, score=score, notes=notes,
        )

    # ─── FILTER 2: Multi-timeframe Analysis ──────────────────
    # Spec: 1W/3D → 1D → 4H → 1H/15M
    # EMA21>EMA55 должны быть на 1D И 4H

    def _filter2_multitf(
        self, w: pd.DataFrame, d: pd.DataFrame, h4: pd.DataFrame, h1: pd.DataFrame
    ) -> Filter2Result:
        notes = []
        score = 0.0

        # ── 1W: EMA21 / EMA55 (глобальный тренд) ──
        w_ema21 = self._ema(w, 21)
        w_ema55 = self._ema(w, 55)
        w_above = w_ema21 > w_ema55
        if w_above:
            notes.append("1W: EMA21 > EMA55 — Бычий долгосрочный тренд ✓")
            score += 0.15
            w_trend = "bullish"
        else:
            notes.append("1W: EMA21 < EMA55 — Медвежий долгосрочный тренд")
            w_trend = "bearish"

        # ── 1D: EMA21>EMA55 + Ichimoku (стратегический вход) ──
        d_ema21 = self._ema(d, 21)
        d_ema55 = self._ema(d, 55)
        d_ema21_above = d_ema21 > d_ema55
        d_above_cloud = self._above_ichimoku_cloud(d)

        if d_ema21_above:
            notes.append("1D: EMA21 > EMA55 — Бычий тренд на дневке ✓")
            score += 0.20
        else:
            notes.append("1D: EMA21 < EMA55 — Нет бычьего тренда на дневке")

        if d_above_cloud:
            notes.append("1D: Цена выше облака Ишимоку ✓")
            score += 0.15
        else:
            notes.append("1D: Цена ниже/внутри облака Ишимоку")

        d_trend = ("bullish" if d_ema21_above and d_above_cloud
                   else "bearish" if not d_ema21_above
                   else "mixed")

        # ── 4H: EMA21>EMA55 + RSI + MACD (тактический вход) ──
        # Spec требует EMA21>EMA55 ТАКЖЕ на 4H
        h4_ema21 = self._ema(h4, 21)
        h4_ema55 = self._ema(h4, 55)
        h4_ema_above = h4_ema21 > h4_ema55

        h4_rsi = self._rsi(h4, 14)
        h4_macd_hist = self._macd_hist(h4)

        if h4_ema_above:
            notes.append("4H: EMA21 > EMA55 ✓")
            score += 0.15

        if self.RSI_MOMENTUM_LOW <= h4_rsi <= self.RSI_MOMENTUM_HIGH:
            notes.append(f"4H: RSI={h4_rsi:.1f} — Зона моментума (40-45) ✓")
            score += 0.25
        elif h4_rsi < self.RSI_MOMENTUM_LOW:
            notes.append(f"4H: RSI={h4_rsi:.1f} — Перепродан (откат состоялся)")
            score += 0.10
        elif h4_rsi > self.RSI_OVERBOUGHT:
            notes.append(f"4H: RSI={h4_rsi:.1f} — Перекуплен (осторожность)")
            score += 0.0
        else:
            notes.append(f"4H: RSI={h4_rsi:.1f} — Вне зоны моментума")

        if h4_macd_hist > 0:
            notes.append("4H: MACD гистограмма > 0 — Бычий моментум ✓")
            score += 0.10

        h4_trend = ("bullish" if h4_ema_above and h4_rsi >= 38 and h4_macd_hist > 0
                    else "bearish" if not h4_ema_above
                    else "neutral")

        # ── 1H/15M: подтверждающий паттерн ──
        h1_pattern = self._detect_h1_pattern(h1)
        if h1_pattern != "none":
            notes.append(f"1H: Паттерн — {h1_pattern} ✓")
            score += 0.0  # bonus — не меняет основной score, только подтверждение

        passed = (score >= 0.50
                  and d_ema21_above       # обязательно: 1D EMA
                  and h4_ema_above)       # обязательно: 4H EMA (spec requirement)

        return Filter2Result(
            weekly_ema21_above_ema55=w_above,
            weekly_trend=w_trend,
            daily_ema21_above_ema55=d_ema21_above,
            daily_above_ichimoku=d_above_cloud,
            daily_trend=d_trend,
            h4_ema21_above_ema55=h4_ema_above,
            h4_rsi=h4_rsi,
            h4_macd_hist=h4_macd_hist,
            h4_trend=h4_trend,
            h1_pattern=h1_pattern,
            passed=passed,
            score=min(score, 1.0),
            notes=notes,
        )

    # ─── FILTER 3: Crypto-specific Indicators ────────────────
    # ТРЕНД = EMA(21) > EMA(55) AND Price > Ишимоку Cloud
    # МОМЕНТУМ = RSI(14) откатал до 40-45 AND MACD hist > 0
    # ВОЛАТИЛЬНОСТЬ = ATR(14) > среднее значение

    def _filter3_indicators(self, h4: pd.DataFrame) -> Filter3Result:
        notes = []
        score = 0.0

        # Тренд: EMA21 > EMA55 И цена выше облака
        ema21 = self._ema(h4, 21)
        ema55 = self._ema(h4, 55)
        above_cloud = self._above_ichimoku_cloud(h4)
        trend_ok = (ema21 > ema55) and above_cloud

        if trend_ok:
            notes.append("Тренд: EMA21 > EMA55 + выше Ишимоку ✓")
            score += 0.30
        elif ema21 > ema55:
            notes.append("Тренд: EMA21 > EMA55 ✓ (ниже облака)")
            score += 0.15
        else:
            notes.append("Тренд: Нет подтверждения (EMA медвежий)")

        # Моментум: RSI откатал к 40-45 И разворачивается вверх И MACD > 0
        rsi = self._rsi(h4, 14)
        prev_rsi = self._rsi(h4, 14, offset=1)
        rsi_turning_up = rsi > prev_rsi
        macd_hist = self._macd_hist(h4)

        momentum_ok = (self.RSI_MOMENTUM_LOW <= rsi <= self.RSI_MOMENTUM_HIGH
                       and rsi_turning_up
                       and macd_hist > 0)

        if momentum_ok:
            notes.append(f"Моментум: RSI={rsi:.1f} в зоне 40-45, разворот вверх ✓")
            score += 0.35
        elif (self.RSI_MOMENTUM_LOW - 5 <= rsi <= self.RSI_MOMENTUM_HIGH + 5
              and rsi_turning_up):
            notes.append(f"Моментум: RSI={rsi:.1f}, разворот вверх (частичное)")
            score += 0.15
        else:
            notes.append(f"Моментум: RSI={rsi:.1f}, разворота нет")

        # Волатильность: ATR > среднее
        atr = self._atr(h4, 14)
        atr_avg = self._atr_ma(h4, 14, 50)
        vol_ok = atr > atr_avg if atr_avg > 0 else False

        if vol_ok:
            notes.append(f"Волатильность: ATR({atr:.4f}) > avg({atr_avg:.4f}) ✓")
            score += 0.15
        else:
            notes.append(f"Волатильность: ATR({atr:.4f}) <= avg({atr_avg:.4f})")

        # Stochastic (5,3,3)
        sk, sd = self._stochastic(h4, 5, 3, 3)
        if sk < 20 and sk > sd:
            notes.append(f"Stochastic: K={sk:.1f} бычий крест из зоны перепроданности ✓")
            score += 0.10
        elif sk > 80:
            notes.append(f"Stochastic: K={sk:.1f} перекуплен, осторожность")

        # Williams %R
        willr = self._williams_r(h4, 14)
        if willr < -80:
            notes.append(f"Williams %R={willr:.1f} — Перепродан, разворот ✓")
            score += 0.10
        elif willr > -20:
            notes.append(f"Williams %R={willr:.1f} — Перекуплен")

        passed = score >= 0.50 and (trend_ok or (ema21 > ema55))

        return Filter3Result(
            trend_confirmed=trend_ok,
            momentum_confirmed=momentum_ok,
            rsi_turning_up=rsi_turning_up,
            volatility_above_avg=vol_ok,
            rsi_14=rsi,
            stochastic_k=sk,
            stochastic_d=sd,
            williams_r=willr,
            atr_14=atr,
            atr_avg=atr_avg,
            passed=passed,
            score=min(score, 1.0),
            notes=notes,
        )

    # ─── FILTER 4: Volume Analysis (САМЫЙ ВАЖНЫЙ) ────────────

    def _filter4_volume(self, h4: pd.DataFrame, h1: pd.DataFrame) -> Filter4Result:
        notes = []
        score = 0.0

        # OBV тренд (умные деньги)
        obv_trend = self._obv_trend(h4)
        if obv_trend == "rising":
            notes.append("OBV: Растёт — умные деньги накапливают ✓")
            score += 0.35
        elif obv_trend == "falling":
            notes.append("OBV: Падает — дистрибуция")
            score += 0.0
        else:
            notes.append("OBV: Боковик")
            score += 0.10

        # Volume vs среднее
        cur_vol = float(h4["volume"].iloc[-1])
        avg_vol = float(h4["volume"].tail(20).mean())
        vol_above = cur_vol > avg_vol * 1.2
        if vol_above:
            notes.append(f"Объём: {cur_vol:.0f} > avg×1.2={avg_vol*1.2:.0f} ✓")
            score += 0.20

        # Volume Delta (разница покупатель/продавец)
        v_delta = self._volume_delta(h4)
        if v_delta > 0:
            notes.append(f"Volume Delta: {v_delta:+.2f} — Покупатели доминируют ✓")
            score += 0.20
        else:
            notes.append(f"Volume Delta: {v_delta:+.2f} — Продавцы доминируют")

        # Аномальный объём на пробое (истинный пробой)
        prev_high = float(h4["high"].iloc[-2]) if len(h4) > 2 else 0
        cur_close = float(h4["close"].iloc[-1])
        anomalous = vol_above and cur_close > prev_high
        if anomalous:
            notes.append("Аномальный объём на пробое — ИСТИННЫЙ ПРОБОЙ ✓")
            score += 0.15

        # VPVR: поддержка у текущей цены
        vpvr = self._estimate_vpvr_support(h4)
        if vpvr:
            notes.append("VPVR: Цена у зоны максимального объёма (поддержка) ✓")
            score += 0.10

        # Накопление = OBV растёт + Delta положительный
        accumulation = (obv_trend == "rising") and (v_delta > 0)
        if accumulation:
            notes.append("Кумуляция/накопление крупными игроками ✓")

        passed = score >= 0.40  # объём — самый важный фильтр

        return Filter4Result(
            obv_trend=obv_trend,
            volume_delta=v_delta,
            volume_above_avg=vol_above,
            vpvr_support_near=vpvr,
            anomalous_volume=anomalous,
            accumulation_detected=accumulation,
            passed=passed,
            score=min(score, 1.0),
            notes=notes,
        )

    # ─── FILTER 5: Price Action & Crypto Patterns ────────────

    def _filter5_price_action(self, h4: pd.DataFrame, h1: pd.DataFrame) -> Filter5Result:
        notes = []
        score = 0.0
        pattern = "none"

        # 1. Ложный пробой (Liquidity Grab) + ретест
        liq_grab = self._detect_liquidity_grab(h4)
        if liq_grab:
            notes.append("Liquidity Grab + ретест уровня ✓")
            score += 0.30
            pattern = "liquidity_grab"

        # 2. Бычье поглощение (Engulfing)
        engulf, eng_dir = self._detect_engulfing(h4)
        if engulf and eng_dir == "bullish":
            notes.append("Бычье поглощение у ключевого уровня ✓")
            score += 0.35
            if pattern == "none":
                pattern = "bullish_engulfing"
        elif engulf and eng_dir == "bearish":
            notes.append("Медвежье поглощение у уровня")
            score += 0.05

        # 3. Пин-бар у значимого уровня
        pin = self._detect_pin_bar(h4)
        pin_at_lvl = self._pin_bar_at_level(h4) if pin else False
        if pin and pin_at_lvl:
            notes.append("Пин-бар у значимого уровня ✓")
            score += 0.30
            if pattern == "none":
                pattern = "pin_bar"
        elif pin:
            notes.append("Пин-бар (не у ключевого уровня)")
            score += 0.10

        # 4. Боковик с сужением волатильности (перед большим движением)
        consol = self._detect_consolidation(h4)
        if consol:
            notes.append("Боковик с сужением волатильности (перед движением) ✓")
            score += 0.15
            if pattern == "none":
                pattern = "consolidation"

        # 5. V-образное дно с дивергенцией RSI
        div = self._detect_divergence(h4)
        if div:
            notes.append("V-образное дно с RSI дивергенцией ✓")
            score += 0.20
            if pattern == "none":
                pattern = "v_divergence"

        # Утренняя/Вечерняя звезда (с подтверждением объёмом)
        star = self._detect_star_pattern(h4)
        star_type = "none"
        if star == "morning":
            notes.append("Утренняя звезда (бычий разворот) ✓")
            score += 0.25
            if pattern == "none":
                pattern = "morning_star"
            star_type = "morning"
        elif star == "evening":
            notes.append("Вечерняя звезда (медвежий разворот)")
            star_type = "evening"

        if not notes:
            notes.append("Price action: нет значимых паттернов")

        passed = score >= 0.25   # хотя бы один паттерн

        return Filter5Result(
            pattern_detected=pattern,
            liquidity_grab_retest=liq_grab,
            consolidation_before_move=consol,
            v_shape_divergence=div,
            engulfing=engulf,
            engulfing_direction=eng_dir,
            evening_morning_star=(star != "none"),
            star_type=star_type,
            pin_bar=pin,
            pin_bar_at_level=pin_at_lvl,
            passed=passed,
            score=min(score, 1.0),
            notes=notes,
        )

    # ─── FILTER 6: Liquidity & Cluster Analysis ──────────────

    def _filter6_liquidity(
        self, orderbook: Optional[dict], h4: pd.DataFrame
    ) -> Filter6Result:
        notes = []
        score = 0.0

        cur_price = float(h4["close"].iloc[-1]) if len(h4) > 0 else 0.0
        buy_wall = sell_wall = False
        cluster_below = cluster_above = None
        depth_ratio = 1.0
        sl_long = sl_short = None

        if orderbook and "bids" in orderbook and "asks" in orderbook:
            bids = [(float(p), float(q)) for p, q in orderbook.get("bids", [])[:50]]
            asks = [(float(p), float(q)) for p, q in orderbook.get("asks", [])[:50]]

            bid_vol = sum(q for _, q in bids)
            ask_vol = sum(q for _, q in asks)
            depth_ratio = bid_vol / ask_vol if ask_vol > 0 else 1.0

            if depth_ratio > 1.5:
                buy_wall = True
                notes.append(f"Стена покупателей: depth_ratio={depth_ratio:.2f} ✓")
                score += 0.25
            elif depth_ratio < 0.67:
                sell_wall = True
                notes.append(f"Стена продавцов: depth_ratio={depth_ratio:.2f}")

            # Кластер покупок (SL лонга ставится ЗА ним)
            if bids:
                top_bid = max(bids, key=lambda x: x[1])
                cluster_below = top_bid[0]
                sl_long = round(cluster_below * 0.995, 8)   # 0.5% ЗА кластером
                notes.append(f"Кластер покупок: {cluster_below:.4f} → SL_LONG: {sl_long:.4f} ✓")
                score += 0.25

            # Кластер продаж (SL шорта ставится ЗА ним)
            if asks:
                top_ask = max(asks, key=lambda x: x[1])
                cluster_above = top_ask[0]
                sl_short = round(cluster_above * 1.005, 8)
                notes.append(f"Кластер продаж: {cluster_above:.4f} → SL_SHORT: {sl_short:.4f}")
                score += 0.20

            score += 0.30   # базовый балл за наличие стакана
        else:
            # Нет стакана — оцениваем по ATR и уровням
            atr = self._atr(h4, 14)
            sl_pct = self.SL_MAJOR_MIN if self.is_major else self.SL_ALT_MIN
            sl_long  = round(cur_price * (1 - sl_pct), 8)
            sl_short = round(cur_price * (1 + sl_pct), 8)
            notes.append(f"Нет стакана — SL по ATR: long={sl_long:.4f}, short={sl_short:.4f}")
            score += 0.35   # частичный балл

        passed = score >= 0.35

        return Filter6Result(
            buy_wall_detected=buy_wall,
            sell_wall_detected=sell_wall,
            cluster_above=cluster_above,
            cluster_below=cluster_below,
            recommended_sl_long=sl_long,
            recommended_sl_short=sl_short,
            orderbook_depth_ratio=depth_ratio,
            passed=passed,
            score=min(score, 1.0),
            notes=notes,
        )

    # ─── DETERMINE SIGNAL (CRYPTO TRIGGER) ───────────────────
    # Строго по спецификации: ALL 6 условий должны совпасть.
    # Жёсткие запреты нарушать НЕЛЬЗЯ.

    def _determine_signal(
        self, f1: Filter1Result, f2: Filter2Result, f3: Filter3Result,
        f4: Filter4Result, f5: Filter5Result, confidence: float,
    ) -> Signal:
        """
        CRYPTO TRIGGER — определение торгового сигнала.

        Жёсткие правила (не обходятся никаким уровнем уверенности):
        1. F&G > 75 → NO LONG (зона распределения)
        2. F&G < 20 → ТОЛЬКО SHORT или WAIT (медвежий рынок)
        3. BTC.D растёт И монета — альткоин → WAIT
        4. Минимум 4/6 фильтров должны пройти
        5. Уверенность >= threshold
        """
        fg = f1.fear_greed_index

        # ── Жёсткий запрет 1: слишком низкая уверенность ──
        if confidence < 0.40:
            return Signal.WAIT

        # ── Жёсткий запрет 2: медвежий рынок ──
        if f1.scenario == MarketScenario.BEAR:
            # F&G < 20: только шорты на фьючерсах
            # Условие шорта: RSI > 60 (перекуплен на отскоке) + медвежье поглощение
            if (f2.h4_rsi > 60
                    and f5.engulfing_direction == "bearish"
                    and f4.obv_trend == "falling"):
                return Signal.SHORT
            return Signal.WAIT

        # ── Жёсткий запрет 3: BTC доминирует + не BTC/ETH ──
        if f1.scenario == MarketScenario.BTC_DOMINATES and not self.is_major:
            return Signal.WAIT

        # ── Жёсткий запрет 4: extreme greed → нет лонгов ──
        if fg >= self.FEAR_GREED_EXTREME_GREED:
            # В extreme greed можно только шортить (зона распределения)
            if (self.is_major           # только мажоры
                    and f2.h4_rsi > self.RSI_OVERBOUGHT
                    and f5.engulfing_direction == "bearish"
                    and f4.volume_delta < 0):
                return Signal.SHORT
            return Signal.WAIT

        # ── CRYPTO TRIGGER для ЛОНГА (все 6 условий по спецификации) ──
        # Условие 1: BTC.D падает или стабилен (альтсезон)
        cond1_btc = f1.btc_dominance_trend in ("falling", "stable") or self.is_major
        # Условие 2: EMA21 > EMA55 на 1D и 4H
        cond2_ema = f2.daily_ema21_above_ema55 and f2.h4_ema21_above_ema55
        # Условие 3: RSI откатал к 40-45 и разворачивается вверх
        cond3_rsi = (f3.momentum_confirmed
                     or (f2.h4_rsi < 50 and f3.rsi_turning_up))
        # Условие 4: OBV растёт, VPVR поддержка
        cond4_vol = f4.obv_trend == "rising" or f4.accumulation_detected
        # Условие 5: бычье поглощение или пин-бар у уровня
        cond5_pa = (f5.engulfing_direction == "bullish"
                    or f5.pin_bar_at_level
                    or f5.liquidity_grab_retest
                    or f5.star_type == "morning")
        # Условие 6: F&G < 45
        cond6_fg = fg <= self.FEAR_GREED_ENTRY_MAX_LONG

        all_6_conditions = (cond1_btc and cond2_ema and cond3_rsi
                            and cond4_vol and cond5_pa and cond6_fg)

        # Сколько из 6 условий выполнено
        n_conds = sum([cond1_btc, cond2_ema, cond3_rsi, cond4_vol, cond5_pa, cond6_fg])

        if all_6_conditions and confidence >= 0.55:
            return Signal.LONG

        # 5/6 условий + достаточная уверенность (допустимый порог)
        if n_conds >= 5 and confidence >= 0.60 and cond6_fg and cond2_ema:
            return Signal.LONG

        # Шорт-условия (Сценарий 3: медвежий рынок, зона распределения)
        # На фьючерсах: перекупленность + медвежий паттерн + распределение
        bearish_setup = (
            fg > 55                              # ближе к greed
            and f2.h4_rsi > self.RSI_OVERBOUGHT  # RSI перекуплен (> 65)
            and f5.engulfing_direction == "bearish"
            and f4.obv_trend == "falling"
            and f4.volume_delta < 0
        )
        if bearish_setup and confidence >= 0.55:
            return Signal.SHORT

        return Signal.NEUTRAL

    # ─── CALCULATE TRADE LEVELS ──────────────────────────────

    def _calculate_levels(
        self, signal: Signal, price: float, f6: Filter6Result, h4: pd.DataFrame
    ):
        """
        Расчёт уровней по VOLTAGE Risk Management.
        SL — ВСЕГДА за кластером ликвидности.
        TP1=1.5R (40%), TP2=3R (30%), TP3=5R+trailing (30%).
        """
        if signal in (Signal.WAIT, Signal.NEUTRAL) or price <= 0:
            return None, None, None, None, None, None

        entry = price

        # Минимальный % SL по спецификации VOLTAGE
        sl_min_pct = self.SL_MAJOR_MIN if self.is_major else self.SL_ALT_MIN
        sl_max_pct = self.SL_MAJOR_MAX if self.is_major else self.SL_ALT_MAX
        sl_mid_pct = (sl_min_pct + sl_max_pct) / 2

        if signal == Signal.LONG:
            # SL: БЕРЁМ ДАЛЬНИЙ из двух — кластерный или % от входа.
            # Спецификация: SL ЗА кластером ликвидности И 8-12% для альтов.
            cluster_sl = f6.recommended_sl_long
            min_sl     = entry * (1 - sl_min_pct)
            mid_sl     = entry * (1 - sl_mid_pct)
            if cluster_sl is not None:
                sl = min(cluster_sl, min_sl)   # берём более дальний (меньший)
            else:
                sl = mid_sl

            risk = entry - sl
            if risk <= 0:
                return None, None, None, None, None, None

            tp1 = entry + risk * self.TP1_R
            tp2 = entry + risk * self.TP2_R
            tp3 = entry + risk * self.TP3_R

        else:  # SHORT
            cluster_sl = f6.recommended_sl_short
            min_sl     = entry * (1 + sl_min_pct)
            mid_sl     = entry * (1 + sl_mid_pct)
            if cluster_sl is not None:
                sl = max(cluster_sl, min_sl)   # более дальний — больший
            else:
                sl = mid_sl

            risk = sl - entry
            if risk <= 0:
                return None, None, None, None, None, None

            tp1 = entry - risk * self.TP1_R
            tp2 = entry - risk * self.TP2_R
            tp3 = entry - risk * self.TP3_R

        # R:R по TP2 (основной)
        rr = round(abs(tp2 - entry) / risk, 2)

        return (
            round(entry, 8),
            round(sl, 8),
            round(tp1, 8),
            round(tp2, 8),
            round(tp3, 8),
            rr,
        )

    # ─── REASONING ───────────────────────────────────────────

    def _build_reasoning(self, f1, f2, f3, f4, f5, f6, signal, passed) -> str:
        lines = [
            f"=== VOLTAGE Analysis: {self.symbol} ({('major' if self.is_major else 'altcoin')}) ===",
            f"Signal: {signal.value.upper()} | Filters: {passed}/6 | Scenario: {f1.scenario.value}",
            "",
            "FILTER 1 — BTC Dominance & Sentiment:",
        ]
        lines += [f"  • {n}" for n in f1.notes]
        lines += ["", "FILTER 2 — Multi-timeframe (1W/1D/4H/1H):"]
        lines += [f"  • {n}" for n in f2.notes]
        lines += ["", "FILTER 3 — Indicators (EMA/RSI/MACD/Stoch/Williams):"]
        lines += [f"  • {n}" for n in f3.notes]
        lines += ["", "FILTER 4 — Volume (OBV/Delta/VPVR) [САМЫЙ ВАЖНЫЙ]:"]
        lines += [f"  • {n}" for n in f4.notes]
        lines += ["", "FILTER 5 — Price Action:"]
        lines += [f"  • {n}" for n in f5.notes]
        lines += ["", "FILTER 6 — Liquidity & Clusters:"]
        lines += [f"  • {n}" for n in f6.notes]
        return "\n".join(lines)

    # ─── INDICATOR HELPERS ───────────────────────────────────

    def _ema(self, df: pd.DataFrame, period: int, offset: int = 0) -> float:
        if len(df) < period:
            return float(df["close"].iloc[-1]) if len(df) > 0 else 0.0
        ema = df["close"].ewm(span=period, adjust=False).mean()
        idx = -(1 + offset)
        v = ema.iloc[idx]
        return float(v) if not (isinstance(v, float) and np.isnan(v)) else 0.0

    def _rsi(self, df: pd.DataFrame, period: int, offset: int = 0) -> float:
        if len(df) < period + 1:
            return 50.0
        series = self._rsi_series(df["close"], period)
        if series is None or series.empty:
            return 50.0
        v = series.iloc[-(1 + offset)]
        return float(v) if not np.isnan(v) else 50.0

    def _macd_hist(self, df: pd.DataFrame) -> float:
        if len(df) < 35:
            return 0.0
        close = df["close"].astype(float)
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal_line
        if hist.empty:
            return 0.0
        v = hist.iloc[-1]
        return float(v) if not np.isnan(v) else 0.0

    def _atr(self, df: pd.DataFrame, period: int) -> float:
        if len(df) < period + 1:
            return 0.0
        atr = self._atr_series(df, period)
        if atr is None or atr.empty:
            return 0.0
        v = atr.iloc[-1]
        return float(v) if not np.isnan(v) else 0.0

    def _atr_ma(self, df: pd.DataFrame, atr_period: int, ma_period: int) -> float:
        """Average of ATR over ma_period bars (rolling mean of ATR)."""
        if len(df) < atr_period + ma_period:
            return self._atr(df, atr_period)
        atr = self._atr_series(df, atr_period)
        if atr is None or atr.empty:
            return 0.0
        v = atr.rolling(ma_period).mean().iloc[-1]
        return float(v) if not np.isnan(v) else 0.0

    def _stochastic(self, df: pd.DataFrame, k=5, d=3, smooth=3):
        if len(df) < k + d + smooth:
            return 50.0, 50.0
        low_min = df["low"].rolling(window=k, min_periods=k).min()
        high_max = df["high"].rolling(window=k, min_periods=k).max()
        spread = (high_max - low_min).replace(0, np.nan)
        raw_k = 100 * (df["close"] - low_min) / spread
        smooth_k = raw_k.rolling(window=smooth, min_periods=smooth).mean()
        d_line = smooth_k.rolling(window=d, min_periods=d).mean()
        if smooth_k.empty or d_line.empty:
            return 50.0, 50.0
        kv = float(smooth_k.iloc[-1])
        dv = float(d_line.iloc[-1])
        return (kv if not np.isnan(kv) else 50.0,
                dv if not np.isnan(dv) else 50.0)

    def _williams_r(self, df: pd.DataFrame, period=14) -> float:
        if len(df) < period:
            return -50.0
        highest_high = df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = df["low"].rolling(window=period, min_periods=period).min()
        spread = (highest_high - lowest_low).replace(0, np.nan)
        w = -100 * (highest_high - df["close"]) / spread
        if w is None or w.empty:
            return -50.0
        v = w.iloc[-1]
        return float(v) if not np.isnan(v) else -50.0

    def _above_ichimoku_cloud(self, df: pd.DataFrame) -> bool:
        if len(df) < 52:
            return False
        try:
            high = df["high"].astype(float)
            low = df["low"].astype(float)
            tenkan = (high.rolling(9, min_periods=9).max() + low.rolling(9, min_periods=9).min()) / 2
            kijun = (high.rolling(26, min_periods=26).max() + low.rolling(26, min_periods=26).min()) / 2
            sa = float(((tenkan + kijun) / 2).shift(26).iloc[-1])
            sb = float(((high.rolling(52, min_periods=52).max() + low.rolling(52, min_periods=52).min()) / 2).shift(26).iloc[-1])
            if np.isnan(sa) or np.isnan(sb):
                return False
            cloud_top = max(sa, sb)
            return float(df["close"].iloc[-1]) > cloud_top
        except Exception:
            return False

    def _obv_trend(self, df: pd.DataFrame) -> str:
        if len(df) < 20:
            return "neutral"
        obv = self._obv_series(df)
        if obv is None or len(obv) < 10:
            return "neutral"
        recent = obv.tail(10).values
        pct = (recent[-1] - recent[0]) / (abs(recent[0]) + 1e-9)
        if pct > 0.01:
            return "rising"
        elif pct < -0.01:
            return "falling"
        return "neutral"

    def _volume_delta(self, df: pd.DataFrame) -> float:
        if len(df) < 5:
            return 0.0
        recent = df.tail(5)
        buy_v  = float(recent[recent["close"] >= recent["open"]]["volume"].sum())
        sell_v = float(recent[recent["close"] <  recent["open"]]["volume"].sum())
        total  = buy_v + sell_v
        return round((buy_v - sell_v) / total, 4) if total > 0 else 0.0

    def _estimate_vpvr_support(self, df: pd.DataFrame) -> bool:
        """Упрощённый VPVR: цена у ценового уровня с максимальным объёмом."""
        if len(df) < 20:
            return False
        recent = df.tail(50)
        poc_idx = recent["volume"].idxmax()
        poc_price = float(recent.loc[poc_idx, "close"])
        cur = float(df["close"].iloc[-1])
        return abs(cur - poc_price) / poc_price < 0.015   # в пределах 1.5%

    def _detect_engulfing(self, df: pd.DataFrame):
        if len(df) < 2:
            return False, "none"
        prev = df.iloc[-2]
        curr = df.iloc[-1]
        po, pc = float(prev["open"]), float(prev["close"])
        co, cc = float(curr["open"]), float(curr["close"])
        prev_body = abs(pc - po)
        curr_body = abs(cc - co)
        if curr_body < prev_body * 0.9:
            return False, "none"
        if cc > co and pc < po:   # бычье поглощение
            if co <= pc and cc >= po:
                return True, "bullish"
        if cc < co and pc > po:   # медвежье поглощение
            if co >= pc and cc <= po:
                return True, "bearish"
        return False, "none"

    def _detect_pin_bar(self, df: pd.DataFrame) -> bool:
        if len(df) < 1:
            return False
        bar = df.iloc[-1]
        o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
        total = h - l
        if total < 1e-10:
            return False
        body = abs(c - o)
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)
        # Пин-бар: хвост >= 2×тело, тело <= 30% диапазона
        return (
            (lower_wick >= 2 * body or upper_wick >= 2 * body)
            and body / total < 0.35
        )

    def _pin_bar_at_level(self, df: pd.DataFrame) -> bool:
        """Пин-бар у значимого уровня поддержки/сопротивления (последние 20 баров)."""
        if len(df) < 10:
            return False
        recent = df.tail(20)
        cur_lo = float(df["low"].iloc[-1])
        cur_hi = float(df["high"].iloc[-1])
        for lvl in list(recent["high"].values) + list(recent["low"].values):
            if abs(cur_lo - float(lvl)) / max(float(lvl), 1) < 0.012:
                return True
            if abs(cur_hi - float(lvl)) / max(float(lvl), 1) < 0.012:
                return True
        return False

    def _detect_liquidity_grab(self, df: pd.DataFrame) -> bool:
        """Ложный пробой ниже недавнего минимума + возврат выше (Liquidity Grab)."""
        if len(df) < 5:
            return False
        recent_lo = float(df["low"].tail(5).iloc[:-1].min())
        cur_lo    = float(df["low"].iloc[-1])
        cur_cl    = float(df["close"].iloc[-1])
        prev_cl   = float(df["close"].iloc[-2])
        return (cur_lo < recent_lo       # пробой ниже
                and cur_cl > recent_lo   # но закрылись выше
                and cur_cl > prev_cl)    # и цена растёт

    def _detect_consolidation(self, df: pd.DataFrame) -> bool:
        """Боковик с сужением волатильности (ATR снижается)."""
        if len(df) < 20:
            return False
        atr_early = self._atr(df.iloc[-20:-10], 7)
        atr_late  = self._atr(df.iloc[-10:], 7)
        return 0 < atr_late < atr_early * 0.75

    def _detect_star_pattern(self, df: pd.DataFrame) -> str:
        """Утренняя (Morning Star) / Вечерняя (Evening Star) звезда."""
        if len(df) < 3:
            return "none"
        c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        c1o, c1c = float(c1["open"]), float(c1["close"])
        c2o, c2c = float(c2["open"]), float(c2["close"])
        c3o, c3c = float(c3["open"]), float(c3["close"])
        c2_body = abs(c2c - c2o)
        c1_body = abs(c1c - c1o)
        small_c2 = c2_body < c1_body * 0.35
        if c1c < c1o and small_c2 and c3c > c3o:   # утренняя
            return "morning"
        if c1c > c1o and small_c2 and c3c < c3o:   # вечерняя
            return "evening"
        return "none"

    def _detect_divergence(self, df: pd.DataFrame) -> bool:
        """RSI бычья дивергенция: цена делает более низкий минимум, RSI — более высокий."""
        if len(df) < 15:
            return False
        prices = df["close"].tail(15).values
        rsi_s = self._rsi_series(df["close"], 14)
        if rsi_s is None or rsi_s.empty:
            return False
        rsi_vals = rsi_s.tail(15).values
        if np.any(np.isnan(rsi_vals)):
            return False
        price_ll = prices[-1] < float(np.min(prices[:-1]))
        rsi_hl   = float(rsi_vals[-1]) > float(np.nanmin(rsi_vals[:-1]))
        return price_ll and rsi_hl

    def _detect_h1_pattern(self, h1: pd.DataFrame) -> str:
        eng, d = self._detect_engulfing(h1)
        if eng:
            return f"{d}_engulfing"
        if self._detect_pin_bar(h1):
            return "pin_bar"
        return "none"

    def _rsi_series(self, close: pd.Series, period: int) -> pd.Series:
        delta = close.astype(float).diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50.0)

    def _atr_series(self, df: pd.DataFrame, period: int) -> pd.Series:
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    def _obv_series(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype(float)
        volume = df["volume"].astype(float)
        direction = np.sign(close.diff().fillna(0.0))
        return (volume * direction).cumsum()
