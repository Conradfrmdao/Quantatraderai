"""Shared market-data ingestion, caching, and context assembly.

This module is the single source of truth for:
  - historical candle persistence
  - background backfill / live-sync loops
  - freshness / gap safety checks
  - indicator snapshot generation
  - agent / chart / backtest market context payloads
"""

from __future__ import annotations

import asyncio
import logging
import math
import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import aiohttp

from src.indicators.local_indicators import compute_all, last_n, latest, rsi, sma
from src.services.market_data_store import (
    InMemoryMarketDataStore,
    MarketCandleRow,
    MarketDataStore,
    get_market_data_store,
    set_market_data_store,
    utc_dt,
)
from src.venues.base import Venue
from src.venues.forex.market_hours import is_forex_market_open
from src.venues.forex.symbols import normalize_oanda_symbol
from src.venues.models import Candle, Ticker

logger = logging.getLogger("quantatraderai.market.context")

TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

LIVE_UPDATE_SECONDS: dict[str, int] = {
    "1m": 15,
    "5m": 45,
    "15m": 90,
    "30m": 120,
    "1h": 180,
    "4h": 300,
    "1d": 600,
}

BINANCE_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}
YAHOO_INTERVALS: dict[str, tuple[str, str]] = {
    "1m": ("1m", "7d"),
    "5m": ("5m", "30d"),
    "15m": ("15m", "60d"),
    "30m": ("30m", "60d"),
    "1h": ("60m", "730d"),
    "4h": ("1d", "730d"),
    "1d": ("1d", "730d"),
}

_KNOWN_CRYPTO_QUOTES = (
    "USDT", "USDC", "BUSD", "USD", "BTC", "ETH", "EUR", "TRY", "FDUSD", "USDP",
)
_STOCKS_TZ = ZoneInfo("America/New_York")
_DEFAULT_BOOTSTRAP_BARS = 240
_MIN_READY_BARS = 60
_MAX_CANDLE_RESPONSE = 500


def _normalize_venue_name(venue_name: str | None) -> str:
    return str(venue_name or "binance").lower().strip().split(":", 1)[0]


def _normalize_asset_class(asset_class: str | None, venue_name: str | None, market: str | None) -> str:
    requested = str(asset_class or "").lower().strip()
    if requested:
        return requested
    venue = _normalize_venue_name(venue_name)
    venue_market = str(market or "").lower().strip()
    if venue in {"oanda", "metatrader", "mt4", "mt5"}:
        return "forex"
    if venue in {"alpaca", "ibkr"}:
        return "stocks"
    if venue == "polymarket":
        return "prediction"
    if venue == "hyperliquid" or venue_market == "futures":
        return "crypto_perp"
    return "crypto_spot"


def _timeframe_seconds(timeframe: str | None) -> int:
    return TIMEFRAME_SECONDS.get(str(timeframe or "1h").lower(), 3600)


def _canonical_symbol(symbol: str, asset_class: str, venue_name: str | None = None) -> str:
    raw = str(symbol or "").strip().upper()
    if not raw:
        return raw
    if ":" in raw:
        head, tail = raw.split(":", 1)
        return f"{head}:{_canonical_symbol(tail, asset_class, venue_name)}"
    compact = raw.replace("/", "").replace("_", "").replace("-", "").replace(" ", "")
    if asset_class == "forex":
        return compact
    if asset_class.startswith("crypto") and compact.endswith(_KNOWN_CRYPTO_QUOTES):
        return compact
    return compact


def _display_symbol(symbol: str, asset_class: str) -> str:
    compact = _canonical_symbol(symbol, asset_class)
    if asset_class == "forex" and len(compact) == 6 and compact.isalpha():
        return f"{compact[:3]}/{compact[3:]}"
    return symbol


def _market_continuous(asset_class: str) -> bool:
    return asset_class in {"crypto_spot", "crypto_perp", "prediction"}


def _history_horizon_days(timeframe: str) -> int:
    if timeframe == "1m":
        return 365
    return 730


def _align_to_bucket(ts: int, timeframe: str) -> int:
    interval = max(_timeframe_seconds(timeframe), 60)
    return (int(ts) // interval) * interval


def _as_candle_dict(candle: Candle | dict[str, Any], *, source: str = "venue") -> dict[str, Any]:
    if isinstance(candle, Candle):
        return {
            "time": int(candle.ts),
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(candle.volume),
            "source": source,
        }
    return {
        "time": int(candle.get("time") or 0),
        "open": float(candle.get("open") or 0),
        "high": float(candle.get("high") or 0),
        "low": float(candle.get("low") or 0),
        "close": float(candle.get("close") or 0),
        "volume": float(candle.get("volume") or 0),
        "source": str(candle.get("source") or source),
    }


def _rows_to_candles(
    *,
    venue: str,
    asset_class: str,
    symbol: str,
    timeframe: str,
    candles: list[dict[str, Any]],
    source: str,
) -> list[MarketCandleRow]:
    out: list[MarketCandleRow] = []
    for candle in candles:
        row = _as_candle_dict(candle, source=source)
        out.append(MarketCandleRow(
            venue=venue,
            asset_class=asset_class,
            symbol=symbol,
            timeframe=timeframe,
            timestamp=int(row["time"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            source=source,
        ))
    return out


def _returns(candles: list[dict[str, Any]], lookback: int = 60) -> list[float]:
    closes = [float(candle.get("close") or 0) for candle in candles[-lookback:]]
    out: list[float] = []
    for idx in range(1, len(closes)):
        prev = closes[idx - 1]
        cur = closes[idx]
        if prev <= 0 or cur <= 0:
            continue
        out.append(math.log(cur / prev))
    return out


def _stoch_rsi(candles: list[dict[str, Any]], period: int = 14) -> list[float | None]:
    base = rsi(candles, period)
    out: list[float | None] = []
    for idx, value in enumerate(base):
        if value is None:
            out.append(None)
            continue
        window = [item for item in base[max(0, idx - period + 1):idx + 1] if item is not None]
        if len(window) < period:
            out.append(None)
            continue
        low = min(window)
        high = max(window)
        if high == low:
            out.append(0.0)
            continue
        out.append((float(value) - low) / (high - low) * 100)
    return out


def _support_resistance(candles: list[dict[str, Any]], window: int) -> dict[str, float | None]:
    sample = candles[-window:]
    if not sample:
        return {"support": None, "resistance": None}
    return {
        "support": round(min(float(candle.get("low") or 0) for candle in sample), 8),
        "resistance": round(max(float(candle.get("high") or 0) for candle in sample), 8),
    }


def _trend_direction(indicators: dict[str, list[Any]], candles: list[dict[str, Any]]) -> str:
    ema20 = latest(indicators.get("ema20", []))
    ema50 = latest(indicators.get("ema50", []))
    macd_val = latest(indicators.get("macd", []))
    if ema20 is None or ema50 is None or macd_val is None or len(candles) < 5:
        return "unknown"
    closes = [float(candle.get("close") or 0) for candle in candles[-5:]]
    slope = closes[-1] - closes[0]
    if ema20 > ema50 and macd_val >= 0 and slope > 0:
        return "bullish"
    if ema20 < ema50 and macd_val <= 0 and slope < 0:
        return "bearish"
    return "sideways"


def _volatility_regime(candles: list[dict[str, Any]], indicators: dict[str, list[Any]]) -> dict[str, Any]:
    atr14 = latest(indicators.get("atr14", []))
    price = float(candles[-1].get("close") or 0) if candles else 0.0
    atr_pct = (float(atr14) / price * 100.0) if atr14 and price > 0 else None
    returns = _returns(candles, lookback=40)
    realized_vol_pct = statistics.pstdev(returns) * 100 if len(returns) > 1 else 0.0
    regime = "unknown"
    if atr_pct is not None:
        if atr_pct >= 4 or realized_vol_pct >= 3:
            regime = "high"
        elif atr_pct <= 1 and realized_vol_pct <= 1:
            regime = "low"
        else:
            regime = "normal"
    return {
        "atr14": round(float(atr14), 8) if atr14 is not None else None,
        "atr_pct": round(atr_pct, 4) if atr_pct is not None else None,
        "realized_vol_pct": round(realized_vol_pct, 4),
        "regime": regime,
    }


def _indicator_snapshot(candles: list[dict[str, Any]]) -> dict[str, Any]:
    if not candles:
        return {}
    indicators = compute_all(candles)
    closes = [float(candle.get("close") or 0) for candle in candles]
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    stoch = _stoch_rsi(candles, 14)
    volatility = _volatility_regime(candles, indicators)
    support20 = _support_resistance(candles, 20)
    support50 = _support_resistance(candles, 50)
    return {
        "ema20": {"latest": latest(indicators.get("ema20", [])), "series": last_n(indicators.get("ema20", []), 20)},
        "ema50": {"latest": latest(indicators.get("ema50", [])), "series": last_n(indicators.get("ema50", []), 20)},
        "sma20": {"latest": latest(sma20), "series": last_n(sma20, 20)},
        "sma50": {"latest": latest(sma50), "series": last_n(sma50, 20)},
        "rsi14": {"latest": latest(indicators.get("rsi14", [])), "series": last_n(indicators.get("rsi14", []), 20)},
        "macd": {
            "latest": latest(indicators.get("macd", [])),
            "signal": latest(indicators.get("macd_signal", [])),
            "histogram": latest(indicators.get("macd_histogram", [])),
        },
        "bollinger": {
            "upper": latest(indicators.get("bbands_upper", [])),
            "middle": latest(indicators.get("bbands_middle", [])),
            "lower": latest(indicators.get("bbands_lower", [])),
        },
        "atr14": {"latest": latest(indicators.get("atr14", [])), "series": last_n(indicators.get("atr14", []), 20)},
        "adx": {"latest": latest(indicators.get("adx", [])), "series": last_n(indicators.get("adx", []), 20)},
        "vwap": {"latest": latest(indicators.get("vwap", [])), "series": last_n(indicators.get("vwap", []), 20)},
        "stoch_rsi": {"latest": latest(stoch), "series": last_n(stoch, 20)},
        "volatility_regime": volatility,
        "trend_direction": _trend_direction(indicators, candles),
        "support_resistance": {
            "swing_20": support20,
            "swing_50": support50,
        },
    }


def _stock_market_open(at: datetime | None = None) -> bool:
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    et = now.astimezone(_STOCKS_TZ)
    if et.weekday() >= 5:
        return False
    open_dt = et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_dt = et.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_dt <= et <= close_dt


def _previous_stock_close_ts(at: datetime | None = None) -> int:
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    et = now.astimezone(_STOCKS_TZ)
    close_dt = et.replace(hour=16, minute=0, second=0, microsecond=0)
    while close_dt.weekday() >= 5 or close_dt > et:
        close_dt = (close_dt - timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
    return int(close_dt.astimezone(timezone.utc).timestamp())


def market_session_info(asset_class: str, *, at: datetime | None = None) -> dict[str, Any]:
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if _market_continuous(asset_class):
        return {
            "asset_class": asset_class,
            "open": True,
            "label": "24/7",
            "timezone": "UTC",
            "continuous": True,
        }
    if asset_class == "forex":
        is_open = is_forex_market_open(now)
        return {
            "asset_class": asset_class,
            "open": is_open,
            "label": "Open" if is_open else "Weekend close",
            "timezone": "UTC",
            "continuous": False,
        }
    if asset_class == "stocks":
        is_open = _stock_market_open(now)
        return {
            "asset_class": asset_class,
            "open": is_open,
            "label": "Regular session" if is_open else "Market closed",
            "timezone": "America/New_York",
            "continuous": False,
        }
    return {
        "asset_class": asset_class,
        "open": True,
        "label": "Open",
        "timezone": "UTC",
        "continuous": False,
    }


def _is_market_open_at(asset_class: str, at_ts: int) -> bool:
    at = datetime.fromtimestamp(at_ts, tz=timezone.utc)
    if _market_continuous(asset_class):
        return True
    if asset_class == "forex":
        return is_forex_market_open(at)
    if asset_class == "stocks":
        return _stock_market_open(at)
    return True


def detect_candle_gaps(
    candles: list[dict[str, Any]],
    *,
    timeframe: str,
    asset_class: str,
    now_ts: int | None = None,
) -> dict[str, Any]:
    interval = max(_timeframe_seconds(timeframe), 60)
    now_ts = int(now_ts or time.time())
    duplicates = 0
    future = 0
    invalid = 0
    negative_volume = 0
    missing = 0
    gap_points: list[int] = []
    unique: set[int] = set()
    sorted_candles = sorted(candles, key=lambda candle: int(candle.get("time") or 0))

    for candle in sorted_candles:
        ts = int(candle.get("time") or 0)
        if ts in unique:
            duplicates += 1
        unique.add(ts)
        if ts > now_ts + interval:
            future += 1
        open_ = float(candle.get("open") or 0)
        high = float(candle.get("high") or 0)
        low = float(candle.get("low") or 0)
        close = float(candle.get("close") or 0)
        volume = float(candle.get("volume") or 0)
        if min(open_, high, low, close) <= 0 or high < max(open_, close) or low > min(open_, close):
            invalid += 1
        if volume < 0:
            negative_volume += 1

    for idx in range(1, len(sorted_candles)):
        prev = int(sorted_candles[idx - 1].get("time") or 0)
        cur = int(sorted_candles[idx].get("time") or 0)
        if cur <= prev:
            continue
        cursor = prev + interval
        while cursor < cur:
            if _is_market_open_at(asset_class, cursor):
                missing += 1
                if len(gap_points) < 20:
                    gap_points.append(cursor)
            cursor += interval

    critical = duplicates > 0 or future > 0 or invalid > 0 or negative_volume > 0
    if _market_continuous(asset_class) and missing > 0:
        critical = True
    return {
        "duplicates": duplicates,
        "future": future,
        "invalid_ohlc": invalid,
        "negative_volume": negative_volume,
        "missing": missing,
        "gap_points": gap_points,
        "critical": critical,
    }


def _candles_fresh(
    candles: list[dict[str, Any]],
    *,
    timeframe: str,
    asset_class: str,
    now_ts: int | None = None,
) -> tuple[bool, str, int | None]:
    if not candles:
        return False, "No candles are stored yet.", None
    now_ts = int(now_ts or time.time())
    last_ts = int(candles[-1].get("time") or 0)
    interval = max(_timeframe_seconds(timeframe), 60)
    age_s = max(0, now_ts - last_ts)
    session = market_session_info(asset_class)

    if session["open"] or _market_continuous(asset_class):
        if last_ts >= _align_to_bucket(now_ts, timeframe) - interval:
            return True, "Fresh candle context is ready.", age_s
        return False, f"Latest candle is {age_s}s old while the market is open.", age_s

    if asset_class == "stocks":
        if last_ts >= _previous_stock_close_ts() - (2 * interval):
            return True, "Market is closed; latest stored stock candle is recent enough.", age_s
    elif asset_class == "forex":
        if age_s <= 60 * 60 * 72:
            return True, "Market is closed; latest stored forex candle is recent enough.", age_s
    else:
        if age_s <= interval * 4:
            return True, "Latest stored candle is recent enough for the closed market session.", age_s

    return False, f"Latest candle is {age_s}s old and outside the last closed session window.", age_s


async def _fetch_binance_candles(
    *,
    symbol: str,
    timeframe: str,
    market: str,
    start_ts: int,
    end_ts: int,
    limit: int,
) -> list[dict[str, Any]]:
    compact = _canonical_symbol(symbol, "crypto_spot")
    endpoint = "https://fapi.binance.com/fapi/v1/klines" if market == "futures" else "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": compact,
        "interval": timeframe if timeframe in BINANCE_INTERVALS else "1h",
        "limit": min(max(limit, 1), 1000),
        "startTime": start_ts * 1000,
        "endTime": end_ts * 1000,
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, params=params, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            data = await resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"binance_candles_unavailable:{data}")
    return [
        {
            "time": int(item[0]) // 1000,
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "volume": float(item[5]),
        }
        for item in data
    ]


async def _fetch_binance_ticker(*, symbol: str, market: str) -> Ticker:
    compact = _canonical_symbol(symbol, "crypto_spot")
    endpoint = "https://fapi.binance.com/fapi/v1/ticker/bookTicker" if market == "futures" else "https://api.binance.com/api/v3/ticker/bookTicker"
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, params={"symbol": compact}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            data = await resp.json()
    bid = float(data.get("bidPrice") or 0)
    ask = float(data.get("askPrice") or 0)
    last = (bid + ask) / 2 if bid and ask else float(data.get("price") or bid or ask or 0)
    return Ticker(symbol=compact, last=last, bid=bid or None, ask=ask or None)


def _yahoo_ticker(symbol: str) -> str:
    upper = _canonical_symbol(symbol, "stocks")
    mapping = {
        "XAUUSD": "GC=F",
        "XAGUSD": "SI=F",
        "USOIL": "CL=F",
        "WTI": "CL=F",
        "US30": "^DJI",
        "NAS100": "^NDX",
        "SPX500": "^GSPC",
        "DE40": "^GDAXI",
        "UK100": "^FTSE",
        "JP225": "^N225",
    }
    if upper in mapping:
        return mapping[upper]
    if len(upper) == 6 and upper.isalpha() and not upper.endswith(("USDT", "BTC", "ETH")):
        return f"{upper}=X"
    return upper


async def _fetch_yahoo_candles(
    *,
    symbol: str,
    timeframe: str,
) -> list[dict[str, Any]]:
    interval, range_value = YAHOO_INTERVALS.get(timeframe, YAHOO_INTERVALS["1h"])
    ticker = _yahoo_ticker(symbol)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{ticker}?interval={interval}&range={range_value}&includePrePost=false"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; QuantatraderAI/1.0)",
        "Accept": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            payload = await resp.json()
    result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
    timestamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [None])[0] or {})
    if not timestamps:
        return []
    out: list[dict[str, Any]] = []
    for idx, ts in enumerate(timestamps):
        open_ = quote.get("open", [None])[idx]
        high = quote.get("high", [None])[idx]
        low = quote.get("low", [None])[idx]
        close = quote.get("close", [None])[idx]
        volume = (quote.get("volume") or [0])[idx] if "volume" in quote else 0
        if open_ is None or high is None or low is None or close is None:
            continue
        out.append({
            "time": int(ts),
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume or 0),
        })
    return out


async def _fetch_oanda_candles(
    *,
    venue: Venue,
    symbol: str,
    timeframe: str,
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    granularity = {
        "1m": "M1",
        "5m": "M5",
        "15m": "M15",
        "30m": "M30",
        "1h": "H1",
        "4h": "H4",
        "1d": "D",
    }.get(timeframe, "H1")
    if not hasattr(venue, "_get"):
        raise RuntimeError("oanda_history_unavailable")
    data = await venue._get(  # type: ignore[attr-defined]
        f"/v3/instruments/{normalize_oanda_symbol(symbol)}/candles",
        params={
            "granularity": granularity,
            "price": "M",
            "from": utc_dt(start_ts).isoformat().replace("+00:00", "Z"),
            "to": utc_dt(end_ts).isoformat().replace("+00:00", "Z"),
        },
    )
    out: list[dict[str, Any]] = []
    for candle in data.get("candles") or []:
        if not candle.get("complete"):
            continue
        mid = candle.get("mid") or {}
        out.append({
            "time": int(datetime.fromisoformat(str(candle["time"]).replace("Z", "+00:00")).timestamp()),
            "open": float(mid.get("o") or 0),
            "high": float(mid.get("h") or 0),
            "low": float(mid.get("l") or 0),
            "close": float(mid.get("c") or 0),
            "volume": float(candle.get("volume") or 0),
        })
    return out


async def _fetch_alpaca_candles(
    *,
    venue: Venue,
    symbol: str,
    timeframe: str,
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    tf_map = {
        "1m": (1, TimeFrameUnit.Minute),
        "5m": (5, TimeFrameUnit.Minute),
        "15m": (15, TimeFrameUnit.Minute),
        "30m": (30, TimeFrameUnit.Minute),
        "1h": (1, TimeFrameUnit.Hour),
        "4h": (4, TimeFrameUnit.Hour),
        "1d": (1, TimeFrameUnit.Day),
    }
    amount, unit = tf_map.get(timeframe, (1, TimeFrameUnit.Hour))
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(amount, unit),
        start=utc_dt(start_ts),
        end=utc_dt(end_ts),
        limit=10_000,
    )
    bars = await asyncio.to_thread(venue._data.get_stock_bars, req)  # type: ignore[attr-defined]
    rows = bars[symbol]
    return [
        {
            "time": int(bar.timestamp.timestamp()),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
        }
        for bar in rows
    ]


async def _fetch_ccxt_history(
    *,
    venue: Venue,
    symbol: str,
    timeframe: str,
    start_ts: int,
    limit: int,
) -> list[dict[str, Any]]:
    client = getattr(venue, "client", None)
    if client is None or not hasattr(client, "fetch_ohlcv"):
        raise RuntimeError("ccxt_history_unavailable")
    rows = await asyncio.to_thread(
        client.fetch_ohlcv,
        symbol,
        timeframe,
        start_ts * 1000,
        min(limit, 1000),
    )
    return [
        {
            "time": int(item[0]) // 1000,
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "volume": float(item[5]),
        }
        for item in rows or []
    ]


async def _fetch_hyperliquid_history(
    *,
    venue: Venue,
    symbol: str,
    timeframe: str,
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    api = getattr(venue, "api", None)
    if api is None:
        raise RuntimeError("hyperliquid_history_unavailable")
    interval_ms = _timeframe_seconds(timeframe) * 1000
    start_ms = start_ts * 1000
    end_ms = end_ts * 1000
    if ":" in symbol:
        raw = await api._retry(lambda: api.info.post("/info", {  # type: ignore[attr-defined]
            "type": "candleSnapshot",
            "req": {"coin": symbol, "interval": timeframe, "startTime": start_ms, "endTime": end_ms},
        }))
    else:
        raw = await api._retry(lambda: api.info.candles_snapshot(symbol, timeframe, start_ms, end_ms))  # type: ignore[attr-defined]
    return [
        {
            "time": int(item.get("t") or 0) // 1000,
            "open": float(item.get("o") or 0),
            "high": float(item.get("h") or 0),
            "low": float(item.get("l") or 0),
            "close": float(item.get("c") or 0),
            "volume": float(item.get("v") or 0),
        }
        for item in raw or []
        if int(item.get("t") or 0) > 0
    ]


async def _fetch_recent_from_venue(venue: Venue, symbol: str, timeframe: str, bars: int) -> list[dict[str, Any]]:
    rows = await venue.get_candles(symbol, timeframe, bars)
    return [_as_candle_dict(row, source="venue") for row in rows]


async def _fetch_history_chunk(
    *,
    venue_name: str,
    asset_class: str,
    symbol: str,
    timeframe: str,
    market: str,
    venue: Venue | None,
    start_ts: int,
    end_ts: int,
    limit: int,
    allow_public_fallback: bool,
    prefer_venue_recent: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    base = _normalize_venue_name(venue_name)
    if venue is not None and prefer_venue_recent:
        return await _fetch_recent_from_venue(venue, symbol, timeframe, max(limit, 1)), "venue_recent"
    if base == "binance" and timeframe in BINANCE_INTERVALS:
        return await _fetch_binance_candles(
            symbol=symbol, timeframe=timeframe, market=market, start_ts=start_ts, end_ts=end_ts, limit=limit
        ), "binance_public"
    if base == "hyperliquid" and venue is not None:
        return await _fetch_hyperliquid_history(
            venue=venue, symbol=symbol, timeframe=timeframe, start_ts=start_ts, end_ts=end_ts
        ), "hyperliquid_api"
    if base in {"bybit", "okx", "kraken", "coinbase", "ccxt"} and venue is not None:
        return await _fetch_ccxt_history(
            venue=venue, symbol=symbol, timeframe=timeframe, start_ts=start_ts, limit=limit
        ), "ccxt_api"
    if base == "oanda" and venue is not None:
        return await _fetch_oanda_candles(
            venue=venue, symbol=symbol, timeframe=timeframe, start_ts=start_ts, end_ts=end_ts
        ), "oanda_api"
    if base == "alpaca" and venue is not None:
        return await _fetch_alpaca_candles(
            venue=venue, symbol=symbol, timeframe=timeframe, start_ts=start_ts, end_ts=end_ts
        ), "alpaca_api"
    if venue is not None:
        return await _fetch_recent_from_venue(venue, symbol, timeframe, max(limit, 1)), "venue_recent"
    if allow_public_fallback and asset_class in {"forex", "stocks"}:
        return await _fetch_yahoo_candles(symbol=symbol, timeframe=timeframe), "yahoo_public"
    raise RuntimeError(f"market_history_unavailable:{venue_name}:{symbol}:{timeframe}")


async def _fetch_live_ticker(
    *,
    venue_name: str,
    asset_class: str,
    symbol: str,
    market: str,
    venue: Venue | None,
    allow_public_fallback: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    if venue is not None:
        try:
            ticker = await venue.get_ticker(symbol)
            return {
                "symbol": ticker.symbol,
                "last": float(ticker.last or 0),
                "bid": float(ticker.bid or 0) if ticker.bid is not None else None,
                "ask": float(ticker.ask or 0) if ticker.ask is not None else None,
                "extra": getattr(ticker, "extra", {}) or {},
                "timestamp": int(time.time()),
            }, "venue"
        except Exception as exc:
            logger.warning("Market ticker fallback for %s %s: %s", venue_name, symbol, exc)
            return None, None
    base = _normalize_venue_name(venue_name)
    if allow_public_fallback and base == "binance":
        ticker = await _fetch_binance_ticker(symbol=symbol, market=market)
        return {
            "symbol": ticker.symbol,
            "last": float(ticker.last or 0),
            "bid": float(ticker.bid or 0) if ticker.bid is not None else None,
            "ask": float(ticker.ask or 0) if ticker.ask is not None else None,
            "extra": getattr(ticker, "extra", {}) or {},
            "timestamp": int(time.time()),
        }, "binance_public"
    return None, None


async def _ensure_indicator_snapshot(
    *,
    store: MarketDataStore,
    venue: str,
    asset_class: str,
    symbol: str,
    timeframe: str,
    candles: list[dict[str, Any]],
) -> dict[str, Any]:
    if not candles:
        return {}
    last_ts = int(candles[-1].get("time") or 0)
    snapshot = await store.get_indicator_snapshot(venue=venue, symbol=symbol, timeframe=timeframe, timestamp=last_ts)
    if snapshot and snapshot.get("indicators"):
        return snapshot["indicators"]
    indicators = _indicator_snapshot(candles)
    await store.upsert_indicator_snapshot(
        venue=venue,
        asset_class=asset_class,
        symbol=symbol,
        timeframe=timeframe,
        timestamp=last_ts,
        indicators=indicators,
    )
    return indicators


async def sync_market_history(
    *,
    venue_name: str,
    asset_class: str,
    symbol: str,
    timeframe: str,
    market: str = "spot",
    venue: Venue | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
    bars: int = _DEFAULT_BOOTSTRAP_BARS,
    allow_public_fallback: bool = True,
    live_sync: bool = False,
    prefer_venue_recent: bool = False,
    store: MarketDataStore | None = None,
) -> dict[str, Any]:
    store = store or await get_market_data_store()
    now_ts = int(time.time())
    end_ts = int(end_ts or now_ts)
    interval = _timeframe_seconds(timeframe)
    horizon_days = _history_horizon_days(timeframe)
    if start_ts is None:
        warm_bars = max(bars, 1) if prefer_venue_recent else max(bars, _MIN_READY_BARS)
        start_ts = max(0, end_ts - warm_bars * interval)
    requested_start_ts = max(start_ts, end_ts - horizon_days * 86400)
    canonical_venue = _normalize_venue_name(venue_name)
    canonical_asset = _normalize_asset_class(asset_class, venue_name, market)
    canonical_symbol = _canonical_symbol(symbol, canonical_asset, canonical_venue)
    if prefer_venue_recent:
        limit = min(max(bars, 1), 1000)
    else:
        limit = min(max(int((end_ts - requested_start_ts) / max(interval, 1)) + 5, bars), 1000)

    job = await store.upsert_backfill_job(
        venue=canonical_venue,
        asset_class=canonical_asset,
        symbol=canonical_symbol,
        timeframe=timeframe,
        start_ts=requested_start_ts,
        end_ts=end_ts,
        status="running",
        last_fetched_ts=None,
        error_message=None,
        source=None,
        live_sync=live_sync,
    )

    try:
        cursor_end = end_ts
        stored_total = 0
        first_stored_ts: int | None = None
        last_stored_ts: int | None = None
        source: str | None = None
        chunk_limit = min(max(limit, 1 if prefer_venue_recent else 100), 1000)

        while cursor_end >= requested_start_ts:
            chunk_start = max(requested_start_ts, cursor_end - (chunk_limit - 1) * interval)
            rows, source = await _fetch_history_chunk(
                venue_name=canonical_venue,
                asset_class=canonical_asset,
                symbol=symbol,
                timeframe=timeframe,
                market=market,
                venue=venue,
                start_ts=chunk_start,
                end_ts=cursor_end,
                limit=chunk_limit,
                allow_public_fallback=allow_public_fallback,
                prefer_venue_recent=prefer_venue_recent,
            )
            if not rows:
                break

            if source == "venue_recent":
                eligible = [row for row in rows if int(row.get("time") or 0) > 0]
            else:
                eligible = [row for row in rows if requested_start_ts <= int(row.get("time") or 0) <= end_ts]
            cleaned = sorted(
                {int(row["time"]): row for row in eligible}.values(),
                key=lambda item: int(item["time"]),
            )
            if not cleaned:
                break

            await store.upsert_candles(_rows_to_candles(
                venue=canonical_venue,
                asset_class=canonical_asset,
                symbol=canonical_symbol,
                timeframe=timeframe,
                candles=cleaned,
                source=source,
            ))

            chunk_first = int(cleaned[0]["time"])
            chunk_last = int(cleaned[-1]["time"])
            first_stored_ts = chunk_first if first_stored_ts is None else min(first_stored_ts, chunk_first)
            last_stored_ts = chunk_last if last_stored_ts is None else max(last_stored_ts, chunk_last)
            stored_total += len(cleaned)

            non_paginated = source in {"venue_recent", "yahoo_public"}
            if non_paginated or chunk_first <= requested_start_ts or len(cleaned) < 2:
                break
            next_cursor = chunk_first - interval
            if next_cursor >= cursor_end:
                break
            cursor_end = next_cursor

        if stored_total <= 0 or first_stored_ts is None or last_stored_ts is None:
            await store.upsert_backfill_job(
                venue=canonical_venue,
                asset_class=canonical_asset,
                symbol=canonical_symbol,
                timeframe=timeframe,
                start_ts=requested_start_ts,
                end_ts=end_ts,
                status="error",
                last_fetched_ts=None,
                error_message="no_candles_returned",
                source=source,
                live_sync=live_sync,
            )
            return {"ok": False, "error": "no_candles_returned", "source": source, "job": job}
        await store.upsert_backfill_job(
            venue=canonical_venue,
            asset_class=canonical_asset,
            symbol=canonical_symbol,
            timeframe=timeframe,
            start_ts=requested_start_ts,
            end_ts=end_ts,
            status="live" if live_sync else "completed",
            last_fetched_ts=first_stored_ts,
            error_message=None,
            source=source,
            live_sync=live_sync,
        )
        return {
            "ok": True,
            "source": source,
            "stored": stored_total,
            "first_ts": first_stored_ts,
            "last_ts": last_stored_ts,
        }
    except Exception as exc:
        logger.warning("Market history sync failed for %s %s %s: %s", canonical_venue, canonical_symbol, timeframe, exc)
        await store.upsert_backfill_job(
            venue=canonical_venue,
            asset_class=canonical_asset,
            symbol=canonical_symbol,
            timeframe=timeframe,
            start_ts=requested_start_ts,
            end_ts=end_ts,
            status="error",
            last_fetched_ts=None,
            error_message=str(exc),
            source=None,
            live_sync=live_sync,
        )
        return {"ok": False, "error": str(exc)}


async def repair_market_gaps(
    *,
    venue_name: str,
    asset_class: str,
    symbol: str,
    timeframe: str,
    market: str = "spot",
    venue: Venue | None = None,
    allow_public_fallback: bool = True,
    store: MarketDataStore | None = None,
) -> dict[str, Any]:
    store = store or await get_market_data_store()
    canonical_venue = _normalize_venue_name(venue_name)
    canonical_asset = _normalize_asset_class(asset_class, venue_name, market)
    canonical_symbol = _canonical_symbol(symbol, canonical_asset, canonical_venue)
    candles = await store.get_candles(
        venue=canonical_venue,
        symbol=canonical_symbol,
        timeframe=timeframe,
        limit=_MAX_CANDLE_RESPONSE,
    )
    gap_report = detect_candle_gaps(candles, timeframe=timeframe, asset_class=canonical_asset)
    if not gap_report["gap_points"] and not gap_report["critical"]:
        return {"ok": True, "repaired": 0, "gap_report": gap_report}

    interval = _timeframe_seconds(timeframe)
    repaired = 0
    for gap_ts in gap_report["gap_points"][:5]:
        result = await sync_market_history(
            venue_name=canonical_venue,
            asset_class=canonical_asset,
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            venue=venue,
            start_ts=max(0, gap_ts - interval * 2),
            end_ts=gap_ts + interval * 2,
            bars=10,
            allow_public_fallback=allow_public_fallback,
            live_sync=False,
            store=store,
        )
        if result.get("ok"):
            repaired += int(result.get("stored") or 0)

    refreshed = await store.get_candles(
        venue=canonical_venue,
        symbol=canonical_symbol,
        timeframe=timeframe,
        limit=_MAX_CANDLE_RESPONSE,
    )
    return {
        "ok": True,
        "repaired": repaired,
        "gap_report": detect_candle_gaps(refreshed, timeframe=timeframe, asset_class=canonical_asset),
    }


_live_tasks: dict[str, asyncio.Task] = {}
_live_task_lock = asyncio.Lock()


def _live_key(venue_name: str, symbol: str, timeframe: str, market: str) -> str:
    return f"{_normalize_venue_name(venue_name)}|{symbol}|{timeframe}|{market}"


async def ensure_live_market_sync(
    *,
    venue_name: str,
    asset_class: str,
    symbol: str,
    timeframe: str,
    market: str = "spot",
    venue_factory: Callable[[], Awaitable[Venue | None]] | None = None,
    allow_public_fallback: bool = True,
) -> None:
    key = _live_key(venue_name, symbol, timeframe, market)
    async with _live_task_lock:
        task = _live_tasks.get(key)
        if task and not task.done():
            return

        async def _loop() -> None:
            interval_s = LIVE_UPDATE_SECONDS.get(timeframe, 180)
            while True:
                venue = await venue_factory() if venue_factory else None
                await sync_market_history(
                    venue_name=venue_name,
                    asset_class=asset_class,
                    symbol=symbol,
                    timeframe=timeframe,
                    market=market,
                    venue=venue,
                    bars=_DEFAULT_BOOTSTRAP_BARS,
                    allow_public_fallback=allow_public_fallback,
                    live_sync=True,
                )
                await asyncio.sleep(interval_s)

        _live_tasks[key] = asyncio.create_task(_loop())


async def get_market_context(
    *,
    venue_name: str,
    symbol: str,
    timeframe: str,
    market: str = "spot",
    asset_class: str | None = None,
    venue: Venue | None = None,
    candles_limit: int = 200,
    allow_public_fallback: bool = True,
    force_refresh: bool = False,
    ensure_live_sync_task: bool = False,
    venue_factory: Callable[[], Awaitable[Venue | None]] | None = None,
    cached_candles: list[dict[str, Any]] | None = None,
    cached_ticker: dict[str, Any] | None = None,
    min_ready_bars: int = _MIN_READY_BARS,
    bootstrap_bars: int | None = None,
    prefer_venue_recent: bool = False,
    raise_on_refresh_failure: bool = False,
    store: MarketDataStore | None = None,
) -> dict[str, Any]:
    store = store or await get_market_data_store()
    canonical_venue = _normalize_venue_name(venue_name)
    canonical_asset = _normalize_asset_class(asset_class, venue_name, market)
    canonical_symbol = _canonical_symbol(symbol, canonical_asset, canonical_venue)
    display_symbol = _display_symbol(symbol, canonical_asset)
    requested_limit = max(1, min(candles_limit, _MAX_CANDLE_RESPONSE))
    bootstrap_limit = max(requested_limit, bootstrap_bars or _DEFAULT_BOOTSTRAP_BARS)
    used_cached_candles = False
    response_source_override: str | None = None
    refreshed_recent_rows: list[dict[str, Any]] | None = None

    if force_refresh:
        refresh = await sync_market_history(
            venue_name=canonical_venue,
            asset_class=canonical_asset,
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            venue=venue,
            bars=bootstrap_limit,
            allow_public_fallback=allow_public_fallback,
            live_sync=False,
            prefer_venue_recent=prefer_venue_recent,
            store=store,
        )
        if raise_on_refresh_failure and not refresh.get("ok"):
            raise RuntimeError(str(refresh.get("error") or "market_refresh_failed"))
        if refresh.get("ok") and prefer_venue_recent and venue is not None:
            rows, response_source_override = await _fetch_history_chunk(
                venue_name=canonical_venue,
                asset_class=canonical_asset,
                symbol=symbol,
                timeframe=timeframe,
                market=market,
                venue=venue,
                start_ts=0,
                end_ts=int(time.time()),
                limit=bootstrap_limit,
                allow_public_fallback=allow_public_fallback,
                prefer_venue_recent=True,
            )
            refreshed_recent_rows = sorted(
                {int(row["time"]): row for row in rows if int(row.get("time") or 0) > 0}.values(),
                key=lambda item: int(item["time"]),
            )[-bootstrap_limit:]

    candles: list[dict[str, Any]] = []
    sorted_cached = sorted(list(cached_candles or []), key=lambda item: int(item.get("time") or 0))
    if sorted_cached and not force_refresh:
        candles = sorted_cached[-bootstrap_limit:]
        used_cached_candles = True
        try:
            await store.upsert_candles(_rows_to_candles(
                venue=canonical_venue,
                asset_class=canonical_asset,
                symbol=canonical_symbol,
                timeframe=timeframe,
                candles=candles,
                source="cache",
            ))
        except Exception as exc:
            logger.debug("Market cache seed skipped for %s %s %s: %s", canonical_venue, canonical_symbol, timeframe, exc)
    elif refreshed_recent_rows is not None:
        candles = list(refreshed_recent_rows)
    else:
        candles = await store.get_candles(
            venue=canonical_venue,
            symbol=canonical_symbol,
            timeframe=timeframe,
            limit=bootstrap_limit,
        )

    candles_fresh = _candles_fresh(candles, timeframe=timeframe, asset_class=canonical_asset)[0]
    needs_sync = force_refresh or not candles or not candles_fresh or (min_ready_bars > 0 and len(candles) < min_ready_bars)
    if needs_sync:
        refresh = await sync_market_history(
            venue_name=canonical_venue,
            asset_class=canonical_asset,
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            venue=venue,
            bars=bootstrap_limit,
            allow_public_fallback=allow_public_fallback,
            live_sync=False,
            prefer_venue_recent=prefer_venue_recent,
            store=store,
        )
        if raise_on_refresh_failure and not refresh.get("ok"):
            raise RuntimeError(str(refresh.get("error") or "market_refresh_failed"))
        if refresh.get("ok") and prefer_venue_recent and venue is not None:
            rows, response_source_override = await _fetch_history_chunk(
                venue_name=canonical_venue,
                asset_class=canonical_asset,
                symbol=symbol,
                timeframe=timeframe,
                market=market,
                venue=venue,
                start_ts=0,
                end_ts=int(time.time()),
                limit=bootstrap_limit,
                allow_public_fallback=allow_public_fallback,
                prefer_venue_recent=True,
            )
            candles = sorted(
                {int(row["time"]): row for row in rows if int(row.get("time") or 0) > 0}.values(),
                key=lambda item: int(item["time"]),
            )[-bootstrap_limit:]
        else:
            candles = await store.get_candles(
                venue=canonical_venue,
                symbol=canonical_symbol,
                timeframe=timeframe,
                limit=bootstrap_limit,
            )
        used_cached_candles = False

    candles = candles[-requested_limit:]
    indicators = await _ensure_indicator_snapshot(
        store=store,
        venue=canonical_venue,
        asset_class=canonical_asset,
        symbol=canonical_symbol,
        timeframe=timeframe,
        candles=candles,
    )
    ticker: dict[str, Any] | None = None
    ticker_source: str | None = None
    if not (used_cached_candles and venue is None and not force_refresh and cached_ticker is None):
        ticker, ticker_source = await _fetch_live_ticker(
            venue_name=canonical_venue,
            asset_class=canonical_asset,
            symbol=symbol,
            market=market,
            venue=venue,
            allow_public_fallback=allow_public_fallback,
        )

    if ticker is None and cached_ticker and float(cached_ticker.get("last") or 0) > 0 and (used_cached_candles or not candles):
        ticker = {
            "symbol": str(cached_ticker.get("symbol") or display_symbol),
            "last": float(cached_ticker.get("last") or 0),
            "bid": float(cached_ticker["bid"]) if cached_ticker.get("bid") is not None else None,
            "ask": float(cached_ticker["ask"]) if cached_ticker.get("ask") is not None else None,
            "extra": dict(cached_ticker.get("extra") or {}),
            "timestamp": int(cached_ticker.get("timestamp") or time.time()),
        }
        ticker_source = "cache"

    if ticker is None and candles:
        ticker = {
            "symbol": display_symbol,
            "last": float(candles[-1].get("close") or 0),
            "bid": None,
            "ask": None,
            "extra": {},
            "timestamp": int(candles[-1].get("time") or 0),
        }
        ticker_source = "cache" if used_cached_candles else str(candles[-1].get("source") or "stored_candle")

    gaps = detect_candle_gaps(candles, timeframe=timeframe, asset_class=canonical_asset)
    candles_fresh, freshness_summary, candle_age_s = _candles_fresh(
        candles,
        timeframe=timeframe,
        asset_class=canonical_asset,
    )

    ticker_fresh = bool(ticker and ticker.get("last") and (time.time() - int(ticker.get("timestamp") or 0) <= max(120, _timeframe_seconds(timeframe))))
    session = market_session_info(canonical_asset)
    warnings: list[str] = []
    if not candles_fresh:
        warnings.append("Market data is stale. Agent paused trading for safety.")
    if gaps["missing"] > 0:
        warnings.append(f"Detected {gaps['missing']} missing candle interval(s).")
    if gaps["critical"]:
        warnings.append("Stored market history failed integrity checks and needs repair.")
    if not ticker_fresh:
        warnings.append("Current ticker is stale or unavailable.")

    ready = candles_fresh and not gaps["critical"] and gaps["missing"] == 0 and bool(ticker and ticker.get("last"))
    source = response_source_override or ticker_source or ("cache" if used_cached_candles else None) or (candles[-1].get("source") if candles else None) or "store"
    latest_candle_ts = int(candles[-1].get("time") or 0) if candles else 0
    funding_rate = None
    spread = None
    if ticker:
        bid = ticker.get("bid")
        ask = ticker.get("ask")
        if bid is not None and ask is not None:
            spread = float(ask) - float(bid)

    if venue is not None:
        try:
            symbol_info = await venue.get_symbol_info(symbol)
            funding_rate = getattr(symbol_info, "funding_rate", None)
            if funding_rate is None:
                funding_rate = (getattr(symbol_info, "extra", {}) or {}).get("fundingRate")
        except Exception:
            pass

    if ensure_live_sync_task:
        await ensure_live_market_sync(
            venue_name=canonical_venue,
            asset_class=canonical_asset,
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            venue_factory=venue_factory,
            allow_public_fallback=allow_public_fallback,
        )

    return {
        "venue": canonical_venue,
        "asset_class": canonical_asset,
        "symbol": display_symbol,
        "symbol_key": canonical_symbol,
        "timeframe": timeframe,
        "candles": candles,
        "ticker": ticker,
        "indicators": indicators,
        "freshness": {
            "ready": ready,
            "state": "ready" if ready else "stale" if not candles_fresh else "unsafe" if gaps["critical"] or gaps["missing"] > 0 else "warming",
            "summary": freshness_summary,
            "latest_candle_ts": latest_candle_ts,
            "candle_age_s": candle_age_s,
            "ticker_fresh": ticker_fresh,
            "ticker_source": ticker_source,
        },
        "volatility": indicators.get("volatility_regime", {}),
        "trend_direction": indicators.get("trend_direction"),
        "spread": spread,
        "funding_rate": funding_rate,
        "market_session": session,
        "warnings": warnings,
        "gap_report": gaps,
        "source": source,
        "last_updated_ts": latest_candle_ts,
        "backfill_job": await store.get_backfill_job(venue=canonical_venue, symbol=canonical_symbol, timeframe=timeframe),
    }


async def market_context_for_agent(
    *,
    venue_name: str,
    symbol: str,
    timeframe: str,
    market: str,
    asset_class: str,
    venue: Venue | None,
    allow_public_fallback: bool = True,
    store: MarketDataStore | None = None,
) -> dict[str, Any]:
    context = await get_market_context(
        venue_name=venue_name,
        symbol=symbol,
        timeframe=timeframe,
        market=market,
        asset_class=asset_class,
        venue=venue,
        candles_limit=200,
        allow_public_fallback=allow_public_fallback,
        force_refresh=False,
        ensure_live_sync_task=False,
        store=store,
    )
    candles = context.get("candles") or []
    ticker = context.get("ticker") or {}
    indicators = context.get("indicators") or {}
    freshness = context.get("freshness") or {}
    return {
        "asset": symbol,
        "current_price": round(float(ticker.get("last") or 0), 8),
        "bid": ticker.get("bid"),
        "ask": ticker.get("ask"),
        "spread": context.get("spread"),
        "funding_rate": context.get("funding_rate"),
        "bars": len(candles),
        "data_ready": bool(freshness.get("ready")),
        "data_state": freshness.get("state"),
        "latest_candle_ts": freshness.get("latest_candle_ts"),
        "data_source": context.get("source"),
        "volatility": context.get("volatility"),
        "trend_direction": context.get("trend_direction"),
        "market_session": context.get("market_session"),
        "warnings": context.get("warnings") or [],
        "indicator_snapshot": indicators,
        "rsi14": ((indicators.get("rsi14") or {}).get("latest")),
        "ema20": ((indicators.get("ema20") or {}).get("latest")),
        "macd": ((indicators.get("macd") or {}).get("latest")),
    }


async def load_market_history_for_backtest(
    *,
    venue_name: str,
    symbol: str,
    timeframe: str,
    lookback: int,
    market: str = "spot",
    asset_class: str | None = None,
    venue: Venue | None = None,
    store: MarketDataStore | None = None,
) -> list[Candle]:
    store = store or await get_market_data_store()
    canonical_venue = _normalize_venue_name(venue_name)
    canonical_asset = _normalize_asset_class(asset_class, venue_name, market)
    canonical_symbol = _canonical_symbol(symbol, canonical_asset, canonical_venue)
    interval = _timeframe_seconds(timeframe)
    await sync_market_history(
        venue_name=canonical_venue,
        asset_class=canonical_asset,
        symbol=symbol,
        timeframe=timeframe,
        market=market,
        venue=venue,
        bars=max(lookback, _DEFAULT_BOOTSTRAP_BARS),
        allow_public_fallback=True,
        live_sync=False,
        store=store,
    )
    candles = await store.get_candles(
        venue=canonical_venue,
        symbol=canonical_symbol,
        timeframe=timeframe,
        start_ts=max(0, int(time.time()) - lookback * interval * 2),
        limit=lookback,
    )
    return [
        Candle(
            ts=int(candle.get("time") or 0),
            open=float(candle.get("open") or 0),
            high=float(candle.get("high") or 0),
            low=float(candle.get("low") or 0),
            close=float(candle.get("close") or 0),
            volume=float(candle.get("volume") or 0),
        )
        for candle in candles
    ]


__all__ = [
    "InMemoryMarketDataStore",
    "LIVE_UPDATE_SECONDS",
    "TIMEFRAME_SECONDS",
    "detect_candle_gaps",
    "ensure_live_market_sync",
    "get_market_context",
    "load_market_history_for_backtest",
    "market_context_for_agent",
    "market_session_info",
    "repair_market_gaps",
    "set_market_data_store",
    "sync_market_history",
]
