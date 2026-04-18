"""Historical candle loader — uses the same venue adapters as live trading.

Cached to disk as JSON per (venue, symbol, timeframe, lookback) so repeated
backtest runs don't re-hit the exchange.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path

from src.venues.models import Candle
from src.venues.registry import get_venue

CACHE_DIR = Path(os.environ.get("QUNTA_BACKTEST_CACHE", ".backtest_cache"))


def _cache_path(venue: str, symbol: str, timeframe: str, lookback: int) -> Path:
    key = f"{venue}|{symbol}|{timeframe}|{lookback}"
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{digest}.json"


async def load_candles(
    venue_name: str,
    symbol: str,
    timeframe: str,
    lookback: int,
    use_cache: bool = True,
) -> list[Candle]:
    cache_file = _cache_path(venue_name, symbol, timeframe, lookback)
    if use_cache and cache_file.exists():
        raw = json.loads(cache_file.read_text())
        return [Candle(**c) for c in raw]

    venue = get_venue(venue_name)
    candles = await venue.get_candles(symbol, timeframe, lookback)
    if candles:
        cache_file.write_text(
            json.dumps([c.__dict__ for c in candles])
        )
    logging.info("data_loader: fetched %d %s candles for %s on %s", len(candles), timeframe, symbol, venue_name)
    return candles
