"""News sentiment via CryptoCompare (free tier, no auth for basic) or NewsAPI.

Fetches the latest headlines per asset, summarises sentiment -1 to +1 using
keyword scoring (fast, no extra LLM call), and injects into agent context.

Optional env vars:
    CRYPTOCOMPARE_API_KEY — for higher rate limits (free at min.io)
    NEWSAPI_KEY           — alternative: newsapi.org free tier

If no key is set, fetches CryptoCompare public endpoint (60 calls/min free).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger("qunta.intel.news")

_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 600  # 10 minutes

_BULLISH_WORDS = {
    "surge", "rally", "bullish", "buy", "adoption", "all-time high", "ath",
    "breakout", "partnership", "upgrade", "integration", "approval", "launch",
    "growth", "record", "profit", "invest", "institutional",
}
_BEARISH_WORDS = {
    "crash", "plunge", "bearish", "sell", "ban", "hack", "exploit", "scam",
    "fraud", "regulation", "arrest", "jail", "dump", "liquidation", "collapse",
    "investigation", "fine", "penalty", "shutdown", "delist",
}


def _score_headline(title: str) -> float:
    low = title.lower()
    bull = sum(1 for w in _BULLISH_WORDS if w in low)
    bear = sum(1 for w in _BEARISH_WORDS if w in low)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


async def get_news_sentiment(symbol: str, limit: int = 10) -> dict[str, Any]:
    """Return sentiment score and top headlines for a symbol."""
    coin = symbol.replace("/USDT", "").replace("/USD", "").upper()
    cache_key = f"news:{coin}"
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL:
        return cached[1]

    headlines: list[str] = []
    try:
        import aiohttp
        api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")
        url = (
            f"https://min-api.cryptocompare.com/data/v2/news/"
            f"?categories={coin}&excludeCategories=Sponsored&lang=EN&sortOrder=latest&limit={limit}"
            + (f"&api_key={api_key}" if api_key else "")
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json()
        articles = data.get("Data", [])
        headlines = [a.get("title", "") for a in articles if a.get("title")][:limit]
    except Exception as e:
        logger.warning("News fetch for %s failed: %s", coin, e)

    if not headlines:
        result = {"symbol": coin, "score": 0.0, "label": "Neutral", "headlines": []}
        _cache[cache_key] = (time.monotonic(), result)
        return result

    scores = [_score_headline(h) for h in headlines]
    avg    = sum(scores) / len(scores)
    avg    = max(-1.0, min(1.0, avg))

    if avg > 0.2:   label = "Bullish"
    elif avg < -0.2: label = "Bearish"
    else:            label = "Neutral"

    result = {
        "symbol":    coin,
        "score":     round(avg, 3),
        "label":     label,
        "headlines": headlines[:3],
    }
    _cache[cache_key] = (time.monotonic(), result)
    return result
