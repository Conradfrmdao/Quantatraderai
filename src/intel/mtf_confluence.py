"""Multi-timeframe (MTF) confluence analysis.

Computes indicators on 3 timeframes (1h, 4h, 1d) and returns an alignment
score 0–1. A score ≥ 0.67 means ≥ 2/3 timeframes agree — agent uses this
as a conviction multiplier before sizing.

Used in: server.py _tick() context payload → LLM context injection.
"""

from __future__ import annotations

import logging
from typing import Any

from src.indicators.local_indicators import compute_all, latest

logger = logging.getLogger("quantatraderai.intel.mtf")

_TIMEFRAMES = ("1h", "4h", "1d")


def _bias(inds: dict) -> str:
    """Simple bullish/bearish/neutral read from indicators."""
    rsi  = latest(inds.get("rsi14", []))
    macd = latest(inds.get("macd", []))
    sig  = latest(inds.get("macd_signal", []))
    ema20 = latest(inds.get("ema20", []))
    ema50 = latest(inds.get("ema50", []))

    bull = 0
    bear = 0

    if rsi is not None:
        # RSI > 55 = bullish momentum; RSI < 45 = bearish momentum
        # Neutral band 45-55 to avoid noise at midpoint
        if rsi > 55: bull += 1
        elif rsi < 45: bear += 1

    if macd is not None and sig is not None:
        if macd > sig: bull += 1
        elif macd < sig: bear += 1

    if ema20 is not None and ema50 is not None:
        if ema20 > ema50: bull += 1
        elif ema20 < ema50: bear += 1

    if bull > bear: return "bullish"
    if bear > bull: return "bearish"
    return "neutral"


async def compute_mtf_confluence(
    venue,
    symbol: str,
    lookback: int = 100,
) -> dict[str, Any]:
    """Fetch candles on 3 TFs and compute bias per TF + alignment score."""
    results: dict[str, str] = {}
    for tf in _TIMEFRAMES:
        try:
            candles = await venue.get_candles(symbol, tf, lookback)
            raw     = [{"time": c.ts, "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume} for c in candles]
            inds    = compute_all(raw)
            results[tf] = _bias(inds)
        except Exception as e:
            logger.warning("MTF %s %s error: %s", symbol, tf, e)
            results[tf] = "neutral"

    votes   = list(results.values())
    bullish = votes.count("bullish")
    bearish = votes.count("bearish")
    n       = len(votes)

    if bullish >= 2:
        overall = "bullish"
        score   = bullish / n
    elif bearish >= 2:
        overall = "bearish"
        score   = bearish / n
    else:
        overall = "neutral"
        score   = 0.33

    return {
        "timeframes":    results,
        "overall_bias":  overall,
        "alignment":     round(score, 3),
        "strong_signal": score >= 0.67,
    }
