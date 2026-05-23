from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

import src.services.market_context as market_context
from src.services.market_context import (
    detect_candle_gaps,
    get_market_context,
    market_session_info,
    sync_market_history,
)
from src.services.market_data_store import InMemoryMarketDataStore, set_market_data_store
from src.venues.models import Candle, SymbolMeta, Ticker


class FakeMarketVenue:
    def __init__(self, candles: list[dict], *, price: float | None = None, funding_rate: float | None = None):
        self._candles = candles
        self._price = float(price if price is not None else candles[-1]["close"])
        self._funding_rate = funding_rate

    async def get_candles(self, symbol: str, timeframe: str, lookback: int):
        sample = self._candles[-lookback:]
        return [
            Candle(
                ts=int(item["time"]),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item["volume"]),
            )
            for item in sample
        ]

    async def get_ticker(self, symbol: str):
        return Ticker(symbol=symbol, last=self._price, bid=self._price - 0.5, ask=self._price + 0.5)

    async def get_symbol_info(self, symbol: str):
        return SymbolMeta(
            symbol=symbol,
            asset_class="crypto_perp",
            tick_size=0.01,
            lot_size=0.001,
            min_notional=10.0,
            max_leverage=10.0,
            funding_rate=self._funding_rate,
        )


@pytest.fixture(autouse=True)
def reset_market_store():
    set_market_data_store(InMemoryMarketDataStore())
    yield
    set_market_data_store(None)


def _fresh_candles(count: int, *, timeframe_s: int = 3600, end_ts: int | None = None, start_price: float = 100.0) -> list[dict]:
    end_ts = end_ts or int(datetime.now(timezone.utc).timestamp())
    end_bucket = (end_ts // timeframe_s) * timeframe_s
    candles: list[dict] = []
    for idx in range(count):
        ts = end_bucket - (count - idx - 1) * timeframe_s
        close = start_price + idx * 0.6
        candles.append({
            "time": ts,
            "open": close - 0.3,
            "high": close + 0.8,
            "low": close - 0.9,
            "close": close,
            "volume": 1000 + idx * 5,
        })
    return candles


@pytest.mark.asyncio
async def test_market_history_upserts_without_duplicate_candles():
    store = InMemoryMarketDataStore()
    set_market_data_store(store)
    candles = _fresh_candles(120)
    venue = FakeMarketVenue(candles)

    first = await sync_market_history(
        venue_name="mock",
        asset_class="crypto_spot",
        symbol="BTC/USDT",
        timeframe="1h",
        venue=venue,
        bars=120,
        allow_public_fallback=False,
        store=store,
    )
    second = await sync_market_history(
        venue_name="mock",
        asset_class="crypto_spot",
        symbol="BTC/USDT",
        timeframe="1h",
        venue=venue,
        bars=120,
        allow_public_fallback=False,
        store=store,
    )

    rows = await store.get_candles(venue="mock", symbol="BTCUSDT", timeframe="1h")
    assert first["ok"] is True
    assert second["ok"] is True
    assert len(rows) == 120


@pytest.mark.asyncio
async def test_backfill_pages_history_in_chunks(monkeypatch):
    store = InMemoryMarketDataStore()
    set_market_data_store(store)
    calls: list[tuple[int, int, int]] = []

    async def fake_fetch_history_chunk(**kwargs):
        start_ts = int(kwargs["start_ts"])
        end_ts = int(kwargs["end_ts"])
        limit = int(kwargs["limit"])
        calls.append((start_ts, end_ts, limit))
        rows = []
        ts = start_ts
        while ts <= end_ts and len(rows) < limit:
            rows.append({
                "time": ts,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10.0,
            })
            ts += 60
        return rows, "stub_source"

    monkeypatch.setattr(market_context, "_fetch_history_chunk", fake_fetch_history_chunk)

    end_ts = 60 * 2200
    result = await sync_market_history(
        venue_name="binance",
        asset_class="crypto_spot",
        symbol="BTCUSDT",
        timeframe="1m",
        start_ts=60,
        end_ts=end_ts,
        bars=2200,
        allow_public_fallback=False,
        store=store,
    )

    rows = await store.get_candles(venue="binance", symbol="BTCUSDT", timeframe="1m")
    job = await store.get_backfill_job(venue="binance", symbol="BTCUSDT", timeframe="1m")

    assert result["ok"] is True
    assert len(calls) >= 3
    assert len(rows) >= 2000
    assert job is not None
    assert job["status"] == "completed"


@pytest.mark.asyncio
async def test_market_context_flags_stale_data_for_crypto():
    store = InMemoryMarketDataStore()
    set_market_data_store(store)
    old_end_ts = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    candles = _fresh_candles(100, end_ts=old_end_ts)
    await store.upsert_candles(market_context._rows_to_candles(
        venue="binance",
        asset_class="crypto_spot",
        symbol="BTCUSDT",
        timeframe="1h",
        candles=candles,
        source="seed",
    ))

    ctx = await get_market_context(
        venue_name="binance",
        symbol="BTCUSDT",
        timeframe="1h",
        asset_class="crypto_spot",
        allow_public_fallback=False,
        store=store,
    )

    assert ctx["freshness"]["ready"] is False
    assert ctx["freshness"]["state"] == "stale"
    assert "Market data is stale. Agent paused trading for safety." in ctx["warnings"]


def test_gap_detector_ignores_forex_weekend_closure():
    friday = int(datetime(2026, 5, 22, 21, 0, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2026, 5, 24, 22, 0, tzinfo=timezone.utc).timestamp())
    candles = [
        {"time": friday, "open": 1.08, "high": 1.09, "low": 1.07, "close": 1.085, "volume": 100},
        {"time": sunday, "open": 1.085, "high": 1.09, "low": 1.08, "close": 1.088, "volume": 100},
    ]

    report = detect_candle_gaps(candles, timeframe="1h", asset_class="forex", now_ts=sunday)
    assert report["missing"] == 0
    assert report["critical"] is False


def test_gap_detector_flags_missing_crypto_intervals():
    first = int(datetime(2026, 5, 22, 21, 0, tzinfo=timezone.utc).timestamp())
    later = int(datetime(2026, 5, 24, 22, 0, tzinfo=timezone.utc).timestamp())
    candles = [
        {"time": first, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100},
        {"time": later, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100},
    ]

    report = detect_candle_gaps(candles, timeframe="1h", asset_class="crypto_spot", now_ts=later)
    assert report["missing"] > 0
    assert report["critical"] is True


def test_market_session_info_handles_market_specific_hours():
    sunday = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
    saturday = datetime(2026, 5, 23, 16, 0, tzinfo=timezone.utc)
    crypto = market_session_info("crypto_spot", at=sunday)
    forex = market_session_info("forex", at=sunday)
    stocks = market_session_info("stocks", at=saturday)

    assert crypto["open"] is True
    assert crypto["label"] == "24/7"
    assert forex["open"] is False
    assert stocks["open"] is False


@pytest.mark.asyncio
async def test_market_context_generates_indicator_snapshot_and_trend():
    store = InMemoryMarketDataStore()
    set_market_data_store(store)
    candles = _fresh_candles(160, start_price=100)
    venue = FakeMarketVenue(candles, price=candles[-1]["close"] + 1.0, funding_rate=0.0002)

    ctx = await get_market_context(
        venue_name="mock",
        symbol="BTC",
        timeframe="1h",
        market="futures",
        asset_class="crypto_perp",
        venue=venue,
        candles_limit=140,
        allow_public_fallback=False,
        force_refresh=True,
        store=store,
    )

    assert ctx["freshness"]["ready"] is True
    assert ctx["indicators"]["ema20"]["latest"] is not None
    assert ctx["indicators"]["stoch_rsi"]["latest"] is not None
    assert ctx["indicators"]["volatility_regime"]["regime"] in {"low", "normal", "high"}
    assert ctx["trend_direction"] in {"bullish", "sideways", "bearish"}
    assert math.isclose(float(ctx["funding_rate"] or 0), 0.0002, rel_tol=0, abs_tol=1e-9)
