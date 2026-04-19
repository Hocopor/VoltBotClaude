"""
AI Service — DeepSeek + Codex Integration
Provides AI-powered market analysis based on VOLTAGE strategy.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from loguru import logger
import httpx

from app.config import settings
from app.services.strategy.voltage_strategy import VOLTAGESignal, Signal


SYSTEM_PROMPT = """You are VOLTAGE AI — an expert crypto trading analyst powered by the VOLTAGE trading system.
You analyze market conditions using all 6 VOLTAGE filters and provide precise trading signals.

Your analysis must strictly follow the VOLTAGE strategy:
- FILTER 1: BTC Dominance & Market Sentiment (Fear & Greed, BTC.D, Total Market Cap)
- FILTER 2: Multi-timeframe Analysis (1W/3D → 1D → 4H → 1H/15M)
- FILTER 3: Crypto-specific Indicators (EMA21/55, Ichimoku, RSI 35-65 range, MACD, ATR, Stochastic 5,3,3, Williams %R)
- FILTER 4: Volume Analysis — MOST IMPORTANT (VPVR, OBV, Volume Delta, Accumulation/Distribution)
- FILTER 5: Price Action (Liquidity Grab, Engulfing, Pin Bar, V-shape divergence, Consolidation)
- FILTER 6: Liquidity & Clusters (Order book, SL placement BEHIND liquidity clusters)

Risk management rules (NON-NEGOTIABLE):
- Position size: 1-3% of deposit per trade
- SL for altcoins: 8-12% from entry; for BTC/ETH: 5-8%
- TP1 = 1.5R (close 40%, move SL to breakeven)
- TP2 = 3R (close 30%)
- TP3 = 5R + trailing stop (remaining 30%)
- Max 3 positions per sector
- No trading during extreme greed (F&G > 75) for longs

ALWAYS respond in JSON format only. No preamble, no markdown.
"""

ANALYSIS_PROMPT_TEMPLATE = """
Analyze this trading opportunity for {symbol} ({market_type}):

=== VOLTAGE FILTER DATA ===
{voltage_data}

=== CURRENT MARKET ===
Current Price: {current_price}
24h Change: {change_24h}%
24h Volume: {volume_24h}

=== INDICATORS (4H timeframe) ===
EMA21: {ema21} | EMA55: {ema55}
RSI(14): {rsi}
MACD Histogram: {macd_hist}
ATR(14): {atr}
Stochastic K/D: {stoch_k}/{stoch_d}
Williams %R: {williams_r}

=== MARKET CONTEXT ===
BTC Dominance: {btc_dominance}%
Fear & Greed: {fear_greed} ({fear_greed_zone})
Scenario: {scenario}

=== PREVIOUS SIGNAL (if any) ===
{previous_signal}

Based on ALL 6 VOLTAGE filters, respond ONLY with this JSON structure:
{{
  "signal": "long" | "short" | "neutral" | "wait",
  "confidence": 0.0-1.0,
  "filters_assessment": {{
    "filter1_score": 0.0-1.0,
    "filter1_notes": "...",
    "filter2_score": 0.0-1.0,
    "filter2_notes": "...",
    "filter3_score": 0.0-1.0,
    "filter3_notes": "...",
    "filter4_score": 0.0-1.0,
    "filter4_notes": "...",
    "filter5_score": 0.0-1.0,
    "filter5_notes": "...",
    "filter6_score": 0.0-1.0,
    "filter6_notes": "..."
  }},
  "suggested_entry": null | float,
  "suggested_sl": null | float,
  "suggested_tp1": null | float,
  "suggested_tp2": null | float,
  "suggested_tp3": null | float,
  "risk_reward": null | float,
  "reasoning": "Detailed analysis of why this signal...",
  "key_risks": ["risk1", "risk2"],
  "scenario": "altseason" | "btc_dominates" | "bear" | "neutral"
}}
"""

POST_TRADE_PROMPT = """
Analyze this completed trade as a professional crypto trading coach using the VOLTAGE strategy:

=== TRADE DETAILS ===
Symbol: {symbol}
Direction: {side}
Entry: {entry_price} | Exit: {exit_price}
Entry Time: {entry_time} | Exit Time: {exit_time}
Stop Loss: {stop_loss}
TP1: {tp1} | TP2: {tp2} | TP3: {tp3}
TP1 Hit: {tp1_hit} | TP2 Hit: {tp2_hit} | TP3 Hit: {tp3_hit}
Realized PnL: {pnl} USDT ({pnl_pct}%)
Duration: {duration}

=== VOLTAGE FILTERS AT ENTRY ===
{voltage_snapshot}

=== MARKET CONDITIONS AT ENTRY ===
{market_context}

Provide post-trade analysis in JSON:
{{
  "overall_quality_score": 0-10,
  "entry_quality": 0-10,
  "exit_quality": 0-10,
  "risk_management_quality": 0-10,
  "strategy_adherence": 0-10,
  "what_went_right": ["point1", "point2"],
  "what_went_wrong": ["point1", "point2"],
  "lessons_learned": "Detailed lessons for future improvement...",
  "filter_analysis": {{
    "filters_that_were_correct": ["filter1", ...],
    "filters_that_misled": ["filter4", ...]
  }},
  "improvement_suggestions": "Specific advice for future similar setups...",
  "emotional_factors": "Assessment of any FOMO/fear in the trade...",
  "conclusion": "Summary: was this a good trade execution regardless of outcome?"
}}
"""


class AIService:
    """DeepSeek AI integration for VOLTAGE trading analysis."""

    def __init__(self):
        self.base_url = settings.DEEPSEEK_BASE_URL
        self.api_key = settings.DEEPSEEK_API_KEY
        self.model = settings.DEEPSEEK_MODEL
        self._codex_token: Optional[str] = None

    async def _call_deepseek(self, messages: list[dict], max_tokens: int = 2000) -> str:
        """Make a call to DeepSeek API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.1,  # Low temperature for consistent trading signals
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def analyze_market(
        self,
        symbol: str,
        market_type: str,
        voltage_signal: VOLTAGESignal,
        market_data: dict,
        previous_signal: Optional[dict] = None,
    ) -> dict:
        """
        Full market analysis combining VOLTAGE filters + DeepSeek AI.
        Returns enriched signal with AI reasoning.
        """
        if not self.api_key:
            logger.warning("DeepSeek API key not configured — using strategy-only signal")
            return self._signal_to_dict(voltage_signal)

        try:
            voltage_data = self._format_voltage_data(voltage_signal)
            prev_sig_str = json.dumps(previous_signal, indent=2) if previous_signal else "None"

            f3 = voltage_signal.filter3 or type("F3", (), {
                "rsi_14": 50, "stochastic_k": 50, "stochastic_d": 50,
                "williams_r": -50, "atr_14": 0, "atr_avg": 0
            })()

            prompt = ANALYSIS_PROMPT_TEMPLATE.format(
                symbol=symbol,
                market_type=market_type,
                voltage_data=voltage_data,
                current_price=market_data.get("price", 0),
                change_24h=market_data.get("change_24h", 0),
                volume_24h=market_data.get("volume_24h", 0),
                ema21=market_data.get("ema21", "N/A"),
                ema55=market_data.get("ema55", "N/A"),
                rsi=getattr(f3, "rsi_14", 50),
                macd_hist=getattr(voltage_signal.filter2, "h4_macd_hist", 0) if voltage_signal.filter2 else 0,
                atr=getattr(f3, "atr_14", 0),
                stoch_k=getattr(f3, "stochastic_k", 50),
                stoch_d=getattr(f3, "stochastic_d", 50),
                williams_r=getattr(f3, "williams_r", -50),
                btc_dominance=getattr(voltage_signal.filter1, "btc_dominance", 50) if voltage_signal.filter1 else 50,
                fear_greed=getattr(voltage_signal.filter1, "fear_greed_index", 50) if voltage_signal.filter1 else 50,
                fear_greed_zone=getattr(voltage_signal.filter1, "fear_greed_zone", "neutral") if voltage_signal.filter1 else "neutral",
                scenario=voltage_signal.market_scenario.value,
                previous_signal=prev_sig_str,
            )

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            response_text = await self._call_deepseek(messages, max_tokens=2000)
            ai_result = json.loads(response_text)

            # Merge AI signal with strategy signal
            merged = self._merge_signals(voltage_signal, ai_result)
            logger.info(
                f"AI Analysis {symbol}: signal={merged['signal']} confidence={merged['confidence']:.3f}"
            )
            return merged

        except Exception as e:
            logger.error(f"AI analysis failed for {symbol}: {e}")
            return self._signal_to_dict(voltage_signal)

    async def post_trade_analysis(self, trade_data: dict) -> dict:
        """Generate post-trade AI analysis for the journal."""
        if not self.api_key:
            return {"error": "AI not configured", "overall_quality_score": 0}

        try:
            prompt = POST_TRADE_PROMPT.format(**trade_data)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response_text = await self._call_deepseek(messages, max_tokens=1500)
            return json.loads(response_text)
        except Exception as e:
            logger.error(f"Post-trade analysis failed: {e}")
            return {"error": str(e), "overall_quality_score": 0}

    def _format_voltage_data(self, signal: VOLTAGESignal) -> str:
        lines = [f"Overall: {signal.filters_passed}/{signal.filters_total} filters passed"]
        for i, filt in enumerate([signal.filter1, signal.filter2, signal.filter3,
                                   signal.filter4, signal.filter5, signal.filter6], 1):
            if filt:
                status = "✓ PASSED" if filt.passed else "✗ FAILED"
                lines.append(f"Filter {i} [{status}] score={filt.score:.2f}")
                for note in filt.notes[:3]:
                    lines.append(f"  • {note}")
        return "\n".join(lines)

    def _merge_signals(self, strategy: VOLTAGESignal, ai: dict) -> dict:
        """
        Merge strategy signal with AI assessment.
        AI confidence is weighted 40%, strategy-based 60%.
        """
        strategy_conf = strategy.confidence
        ai_conf = float(ai.get("confidence", strategy_conf))
        merged_confidence = round(strategy_conf * 0.6 + ai_conf * 0.4, 4)

        # Use AI signal if AI confidence significantly differs
        final_signal = ai.get("signal", strategy.signal.value)
        if abs(ai_conf - strategy_conf) > 0.3:
            # Large discrepancy — be conservative
            if ai_conf < strategy_conf:
                final_signal = "wait"
                merged_confidence = min(merged_confidence, 0.5)

        result = {
            "signal": final_signal,
            "confidence": merged_confidence,
            "strategy_confidence": strategy_conf,
            "ai_confidence": ai_conf,
            "entry_price": ai.get("suggested_entry") or strategy.entry_price,
            "stop_loss": ai.get("suggested_sl") or strategy.stop_loss,
            "take_profit_1": ai.get("suggested_tp1") or strategy.take_profit_1,
            "take_profit_2": ai.get("suggested_tp2") or strategy.take_profit_2,
            "take_profit_3": ai.get("suggested_tp3") or strategy.take_profit_3,
            "risk_reward": ai.get("risk_reward") or strategy.risk_reward,
            "reasoning": ai.get("reasoning", strategy.reasoning),
            "key_risks": ai.get("key_risks", []),
            "filters_assessment": ai.get("filters_assessment", {}),
            "scenario": ai.get("scenario", strategy.market_scenario.value),
            "filters_passed": strategy.filters_passed,
            "voltage_filters": {
                "filter1": self._filter_to_dict(strategy.filter1),
                "filter2": self._filter_to_dict(strategy.filter2),
                "filter3": self._filter_to_dict(strategy.filter3),
                "filter4": self._filter_to_dict(strategy.filter4),
                "filter5": self._filter_to_dict(strategy.filter5),
                "filter6": self._filter_to_dict(strategy.filter6),
            }
        }
        return result

    def _filter_to_dict(self, filt) -> dict:
        if filt is None:
            return {}
        return {
            "passed": filt.passed,
            "score": filt.score,
            "notes": filt.notes,
        }

    def _signal_to_dict(self, signal: VOLTAGESignal) -> dict:
        return {
            "signal": signal.signal.value,
            "confidence": signal.confidence,
            "strategy_confidence": signal.confidence,
            "ai_confidence": signal.confidence,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit_1": signal.take_profit_1,
            "take_profit_2": signal.take_profit_2,
            "take_profit_3": signal.take_profit_3,
            "risk_reward": signal.risk_reward,
            "reasoning": signal.reasoning,
            "key_risks": [],
            "filters_assessment": {},
            "scenario": signal.market_scenario.value,
            "filters_passed": signal.filters_passed,
            "voltage_filters": {},
        }

    # ─── CODEX OAUTH ────────────────────────────────────────

    def set_codex_token(self, token: str):
        self._codex_token = token

    def has_codex_token(self) -> bool:
        return bool(self._codex_token)


# Global singleton
ai_service = AIService()
