"""Market sentiment feeds.

Sources:
  - Alternative.me Crypto Fear & Greed Index (free, no auth)
  - Extensible: add VIX, put/call ratio, etc.

Used by the trading agent to enrich LLM context with macro sentiment.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("qunta.intel.sentiment")

_fng_cache: dict[str, Any] = {}
_fng_cache_ts: float = 0.0
_FNG_TTL = 3600.0  # index updates once per day; refresh hourly is enough


async def get_fear_greed() -> dict[str, Any]:
    """Return the current Crypto Fear & Greed index (0–100).

    Returns:
        {
            "value": 72,
            "label": "Greed",          # Extreme Fear / Fear / Neutral / Greed / Extreme Greed
            "normalized": 0.72,        # 0.0–1.0 for LLM injection
            "sentiment_bias": "bullish" | "bearish" | "neutral",
        }
    """
    global _fng_cache, _fng_cache_ts
    now = time.monotonic()
    if _fng_cache and now - _fng_cache_ts < _FNG_TTL:
        return _fng_cache

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.alternative.me/fng/",
                timeout=aiohttp.ClientTimeout(total=6),
            ) as resp:
                data = await resp.json(content_type=None)

        entry     = data["data"][0]
        value     = int(entry["value"])
        label     = entry["value_classification"]
        normalized = round(value / 100, 3)

        if value <= 30:
            bias = "bearish"   # extreme fear = contrarian buy, but risky
        elif value >= 70:
            bias = "bullish"   # greed = momentum, but watch for reversal
        else:
            bias = "neutral"

        _fng_cache = {
            "value":         value,
            "label":         label,
            "normalized":    normalized,
            "sentiment_bias": bias,
        }
        _fng_cache_ts = now
        logger.debug("Fear/Greed: %s (%s) → %s", value, label, bias)
        return _fng_cache

    except Exception as e:
        logger.warning("Fear/Greed fetch failed: %s", e)
        return {"value": 50, "label": "Neutral", "normalized": 0.5, "sentiment_bias": "neutral"}
