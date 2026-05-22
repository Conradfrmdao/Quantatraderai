"""News sentiment for both crypto and FOREX instruments.

For crypto:  CryptoCompare public API (no key needed for basic use).
For FOREX:   NewsAPI.org (free tier — requires NEWSAPI_KEY env var).
             Falls back to FX-aware keyword search via CryptoCompare's
             global finance category when NewsAPI key is absent.

Env vars:
    CRYPTOCOMPARE_API_KEY  — higher rate limits on CryptoCompare (optional)
    NEWSAPI_KEY            — newsapi.org free tier (required for full FOREX news)

Sentiment scoring:
  - Crypto:  generic bullish/bearish vocabulary
  - FOREX:   hawkish/dovish monetary-policy vocabulary, currency-specific
             (rate hike for USD = dollar bullish; rate cut = dollar bearish)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger("quantatraderai.intel.news")

_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 600  # 10 minutes

# ── Crypto sentiment vocabulary ───────────────────────────────────────────────
_CRYPTO_BULL = {
    "surge", "rally", "bullish", "buy", "adoption", "all-time high", "ath",
    "breakout", "partnership", "upgrade", "integration", "approval", "launch",
    "growth", "record", "profit", "invest", "institutional",
}
_CRYPTO_BEAR = {
    "crash", "plunge", "bearish", "sell", "ban", "hack", "exploit", "scam",
    "fraud", "regulation", "arrest", "jail", "dump", "liquidation", "collapse",
    "investigation", "fine", "penalty", "shutdown", "delist",
}

# ── FOREX sentiment vocabulary ────────────────────────────────────────────────
# "Hawkish" = higher rates ahead = currency bullish
# "Dovish"  = lower rates / QE   = currency bearish
_FX_BULL = {
    "hawkish", "rate hike", "rate increase", "tightening", "inflation above",
    "strong employment", "beats expectations", "higher than expected",
    "economic growth", "gdp beat", "dollar strength", "rate rise",
    "monetary tightening", "policy tightening", "above forecast",
    "resilient economy", "labor market strong",
}
_FX_BEAR = {
    "dovish", "rate cut", "rate decrease", "easing", "quantitative easing",
    "recession", "below expectations", "weaker than expected", "unemployment rise",
    "slowdown", "contraction", "inflation falls", "deflation",
    "policy pivot", "below forecast", "economic weakness", "labour market weak",
    "rate reduction", "emergency cut",
}

# ── Currency → search terms for NewsAPI ───────────────────────────────────────
# Maps a 3-letter currency code to terms that surface relevant macro news.
_CURRENCY_SEARCH: dict[str, list[str]] = {
    "USD": ["Federal Reserve", "FOMC", "US dollar", "Fed rate", "US economy"],
    "EUR": ["ECB", "European Central Bank", "euro zone", "eurozone", "euro rate"],
    "GBP": ["Bank of England", "BoE", "British pound", "UK economy", "sterling"],
    "JPY": ["Bank of Japan", "BoJ", "Japanese yen", "BOJ rate", "Japan economy"],
    "CHF": ["Swiss National Bank", "SNB", "Swiss franc", "Switzerland rate"],
    "CAD": ["Bank of Canada", "BoC", "Canadian dollar", "Canada rate"],
    "AUD": ["Reserve Bank of Australia", "RBA", "Australian dollar", "Australia rate"],
    "NZD": ["RBNZ", "Reserve Bank of New Zealand", "New Zealand dollar", "NZD"],
    "XAU": ["gold price", "gold rally", "Fed gold", "gold safe haven"],
    "XAG": ["silver price", "silver rally"],
}


def _is_forex_symbol(symbol: str) -> bool:
    """Return True for 6-char FX pairs like EURUSD, EUR_USD, XAU_USD."""
    clean = symbol.upper().replace("_", "").replace("/", "").replace("-", "")
    if len(clean) != 6:
        return False
    if clean.endswith("USDT") or clean.endswith("BTC"):
        return False
    return clean.isalpha()


def _extract_currencies(symbol: str) -> tuple[str, str]:
    """Split EURUSD / EUR_USD / XAU_USD → ('EUR', 'USD')."""
    clean = symbol.upper().replace("_", "").replace("/", "").replace("-", "")
    return clean[:3], clean[3:]


def _score_headline(title: str, is_forex: bool = False) -> float:
    low = title.lower()
    if is_forex:
        bull = sum(1 for w in _FX_BULL if w in low)
        bear = sum(1 for w in _FX_BEAR if w in low)
    else:
        bull = sum(1 for w in _CRYPTO_BULL if w in low)
        bear = sum(1 for w in _CRYPTO_BEAR if w in low)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


async def _fetch_forex_newsapi(base_ccy: str, quote_ccy: str, limit: int) -> tuple[list[str], str | None]:
    """Fetch FOREX-relevant headlines from NewsAPI.org."""
    api_key = os.getenv("NEWSAPI_KEY", "")
    if not api_key:
        return [], "newsapi_key_missing"

    # Build a query from the most specific terms for both currencies
    base_terms  = _CURRENCY_SEARCH.get(base_ccy,  [base_ccy])
    quote_terms = _CURRENCY_SEARCH.get(quote_ccy, [quote_ccy])
    # Use the first (most specific) term for each currency
    query = f'"{base_terms[0]}" OR "{quote_terms[0]}"'

    url = (
        f"https://newsapi.org/v2/everything"
        f"?q={query}&language=en&sortBy=publishedAt"
        f"&pageSize={limit}&apiKey={api_key}"
    )
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return [], f"newsapi_http_{resp.status}"
                data = await resp.json()
        articles = data.get("articles", [])
        return [a.get("title", "") for a in articles if a.get("title")][:limit], None
    except Exception as e:
        logger.warning("NewsAPI FOREX fetch (%s/%s) failed: %s", base_ccy, quote_ccy, e)
        return [], str(e)


async def _fetch_forex_fallback(base_ccy: str, quote_ccy: str, limit: int) -> tuple[list[str], str | None]:
    """Fallback: use CryptoCompare's Forex category when NewsAPI key is absent."""
    api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")
    # CryptoCompare categories: Forex, Commodities, Economics
    categories = "Forex,Economics,Commodities"
    url = (
        f"https://min-api.cryptocompare.com/data/v2/news/"
        f"?categories={categories}&lang=EN&sortOrder=latest&limit={limit}"
        + (f"&api_key={api_key}" if api_key else "")
    )
    headlines: list[str] = []
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json()
        articles = data.get("Data", [])
        # Filter to headlines that mention at least one of the traded currencies
        currency_terms = (
            _CURRENCY_SEARCH.get(base_ccy, [base_ccy])[:2]
            + _CURRENCY_SEARCH.get(quote_ccy, [quote_ccy])[:2]
        )
        for a in articles:
            title = a.get("title", "")
            body  = (a.get("body", "") or "")[:200]
            text  = (title + " " + body).lower()
            if any(t.lower() in text for t in currency_terms):
                headlines.append(title)
            if len(headlines) >= limit:
                break
        # If nothing matched, return the first N generic finance headlines
        if not headlines:
            headlines = [a.get("title", "") for a in articles if a.get("title")][:limit]
    except Exception as e:
        logger.warning("CryptoCompare FOREX fallback (%s/%s) failed: %s", base_ccy, quote_ccy, e)
        return [], str(e)
    return headlines, None


async def _fetch_crypto_news(coin: str, limit: int) -> tuple[list[str], str | None]:
    """Fetch crypto headlines from CryptoCompare."""
    api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")
    url = (
        f"https://min-api.cryptocompare.com/data/v2/news/"
        f"?categories={coin}&excludeCategories=Sponsored&lang=EN"
        f"&sortOrder=latest&limit={limit}"
        + (f"&api_key={api_key}" if api_key else "")
    )
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return [], f"cryptocompare_http_{resp.status}"
                data = await resp.json()
        return [a.get("title", "") for a in data.get("Data", []) if a.get("title")][:limit], None
    except Exception as e:
        logger.warning("CryptoCompare news fetch (%s) failed: %s", coin, e)
        return [], str(e)


async def get_news_sentiment(symbol: str, limit: int = 10) -> dict[str, Any]:
    """Return sentiment score and top headlines for any symbol (crypto or FOREX).

    Returns:
        {
            "symbol":    str,   # normalised symbol
            "score":     float, # -1.0 (bearish) to +1.0 (bullish)
            "label":     str,   # "Bullish" | "Neutral" | "Bearish"
            "headlines": list[str],
            "source":    str,   # "newsapi" | "cryptocompare_forex" | "cryptocompare_crypto"
        }
    """
    cache_key = f"news:{symbol.upper()}"
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL:
        payload = dict(cached[1])
        payload["stale"] = False
        payload.pop("error", None)
        return payload

    is_fx = _is_forex_symbol(symbol)
    error_detail: str | None = None

    if is_fx:
        base_ccy, quote_ccy = _extract_currencies(symbol)
        # Try NewsAPI first; fall back to CryptoCompare finance category
        headlines, error_detail = await _fetch_forex_newsapi(base_ccy, quote_ccy, limit)
        source = "newsapi"
        if not headlines:
            headlines, fallback_error = await _fetch_forex_fallback(base_ccy, quote_ccy, limit)
            source = "cryptocompare_forex"
            error_detail = fallback_error or error_detail
    else:
        coin = symbol.replace("/USDT", "").replace("/USD", "").upper()
        headlines, error_detail = await _fetch_crypto_news(coin, limit)
        source = "cryptocompare_crypto"
        base_ccy = coin   # for scoring

    if not headlines:
        if cached:
            stale_payload = dict(cached[1])
            stale_payload["stale"] = True
            if error_detail:
                stale_payload["error"] = error_detail
            stale_payload["cache_age_s"] = int(time.monotonic() - cached[0])
            return stale_payload
        result = {
            "symbol":    symbol.upper(),
            "score":     0.0,
            "label":     "Neutral",
            "headlines": [],
            "source":    source,
            "stale":     False,
        }
        if error_detail:
            result["error"] = error_detail
        _cache[cache_key] = (time.monotonic(), result)
        return result

    scores = [_score_headline(h, is_forex=is_fx) for h in headlines]
    avg    = max(-1.0, min(1.0, sum(scores) / len(scores)))

    if   avg >  0.2: label = "Bullish"
    elif avg < -0.2: label = "Bearish"
    else:            label = "Neutral"

    result = {
        "symbol":    symbol.upper(),
        "score":     round(avg, 3),
        "label":     label,
        "headlines": headlines[:3],
        "source":    source,
        "stale":     False,
    }
    _cache[cache_key] = (time.monotonic(), result)
    logger.debug("News sentiment %s → %.3f (%s) via %s", symbol, avg, label, source)
    return result
