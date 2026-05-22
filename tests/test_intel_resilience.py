from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_news_sentiment_uses_stale_cache_when_upstream_fails(monkeypatch):
    import src.intel.news as news

    monkeypatch.setattr(news, "_cache", {
        "news:BTC/USDT": (
            0.0,
            {
                "symbol": "BTC/USDT",
                "score": 0.6,
                "label": "Bullish",
                "headlines": ["Cached headline"],
                "source": "cryptocompare_crypto",
                "stale": False,
            },
        ),
    })
    monkeypatch.setattr(news.time, "monotonic", lambda: news._CACHE_TTL + 1000)
    monkeypatch.setattr(news, "_fetch_crypto_news", AsyncMock(return_value=([], "cryptocompare_http_403")))

    result = await news.get_news_sentiment("BTC/USDT")

    assert result["stale"] is True
    assert result["headlines"] == ["Cached headline"]
    assert "403" in result["error"]


@pytest.mark.asyncio
async def test_fear_greed_uses_stale_cache_when_refresh_fails(monkeypatch):
    import src.intel.sentiment as sentiment

    monkeypatch.setattr(sentiment, "_fng_cache", {
        "value": 72,
        "label": "Greed",
        "normalized": 0.72,
        "sentiment_bias": "bullish",
        "stale": False,
    })
    monkeypatch.setattr(sentiment, "_fng_cache_ts", 0.0)
    monkeypatch.setattr(sentiment.time, "monotonic", lambda: sentiment._FNG_TTL + 1000)

    class FailingSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            raise RuntimeError("sentiment upstream unavailable")

    monkeypatch.setitem(sys.modules, "aiohttp", SimpleNamespace(
        ClientSession=lambda: FailingSession(),
        ClientTimeout=lambda total: total,
    ))

    result = await sentiment.get_fear_greed()

    assert result["stale"] is True
    assert result["value"] == 72
    assert "unavailable" in result["error"]


@pytest.mark.asyncio
async def test_calendar_feed_uses_stale_cache_when_refresh_fails(monkeypatch):
    import src.intel.economic_calendar as calendar

    cached = [{"name": "FOMC", "date": "2026-05-22T12:00:00+00:00"}]
    monkeypatch.setattr(calendar, "_cache", cached)
    monkeypatch.setattr(calendar, "_cache_ts", 0.0)
    monkeypatch.setattr(calendar.time, "monotonic", lambda: calendar._CACHE_TTL + 1000)
    monkeypatch.setattr(calendar, "_fetch_events", AsyncMock(return_value=([], "twelvedata_http_403")))

    events = await calendar.get_upcoming_events(force_refresh=True)
    status = await calendar.get_calendar_feed_status(force_refresh=True)

    assert events == cached
    assert status["state"] == "stale"
    assert "cached economic calendar" in status["summary"].lower()
