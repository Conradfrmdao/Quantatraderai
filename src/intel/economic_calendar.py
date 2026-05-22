"""Economic calendar via TwelveData API.

Fetches upcoming high-impact events (NFP, CPI, FOMC, ECB, BoE, payrolls).
The trading agent calls `should_pause()` before each decision tick and holds
all positions flat if a high-impact event is within 5 minutes.

Env vars:
    TWELVEDATA_API_KEY  — free at twelvedata.com (required for live use)

If the key is absent the module returns empty data — the agent trades normally.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("quantatraderai.intel.calendar")

_cache: list[dict[str, Any]] = []
_cache_ts: float = 0.0
_CACHE_TTL = 3600.0  # refresh hourly
_last_fetch_state = "idle"
_last_fetch_error = ""

# High-impact event keywords → relevant currencies.
# None means "always relevant regardless of pair" (e.g. broad USD events affect all USD pairs).
_HIGH_IMPACT_EVENTS: list[tuple[tuple[str, ...], set[str] | None]] = [
    # (keywords, relevant_currencies | None for global)
    (("nonfarm", "non-farm", "payroll"), {"USD"}),
    (("fomc", "federal reserve", "fed funds"), {"USD"}),
    (("cpi",), None),           # CPI exists for every currency — filter at call-site
    (("pce", "ppi"), {"USD"}),
    (("gdp",), None),
    (("ecb", "european central bank"), {"EUR"}),
    (("boe", "bank of england"), {"GBP"}),
    (("boj", "bank of japan"), {"JPY"}),
    (("snb", "swiss national bank"), {"CHF"}),
    (("bank of canada", "boc rate"), {"CAD"}),
    (("rba", "reserve bank of australia"), {"AUD"}),
    (("rbnz", "reserve bank of new zealand"), {"NZD"}),
    (("interest rate",), None),
    (("unemployment",), None),
    (("inflation",), None),
    (("retail sales",), None),
]

# All high-impact keywords flattened (for fast pre-filter)
_ALL_KEYWORDS: tuple[str, ...] = tuple(
    kw for keywords, _ in _HIGH_IMPACT_EVENTS for kw in keywords
)

_PAUSE_WINDOW_SECONDS = 300  # 5 minutes before + 5 minutes after


def _extract_currencies(symbols: list[str]) -> set[str]:
    """Extract 3-letter currency codes from FOREX symbols like EUR_USD → {EUR, USD}."""
    currencies: set[str] = set()
    for sym in symbols:
        clean = sym.upper().replace("_", "").replace("/", "").replace("-", "")
        if len(clean) == 6:
            currencies.add(clean[:3])
            currencies.add(clean[3:])
    return currencies


def _event_affects_symbols(event_name: str, traded_currencies: set[str]) -> bool:
    """Return True if this event is relevant to the traded currency pairs.

    If traded_currencies is empty (non-FOREX or unknown), all events pass through.
    """
    if not traded_currencies:
        return True
    name = event_name.lower()
    for keywords, event_currencies in _HIGH_IMPACT_EVENTS:
        if not any(kw in name for kw in keywords):
            continue
        # Event matched a keyword group
        if event_currencies is None:
            # Global event (CPI, GDP, etc.) — check if any traded currency appears in name
            for cur in traded_currencies:
                if cur.lower() in name:
                    return True
        else:
            # Currency-specific event — relevant only if we trade that currency
            if event_currencies & traded_currencies:
                return True
    return False


async def _fetch_events() -> tuple[list[dict[str, Any]], str | None]:
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        return [], "calendar_key_missing"
    url = (
        f"https://api.twelvedata.com/economic_calendar"
        f"?apikey={api_key}&importance=high&outputsize=50"
    )
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return [], f"twelvedata_http_{resp.status}"
                data = await resp.json()
        return data.get("result", data.get("data", [])), None
    except Exception as e:
        logger.warning("Economic calendar fetch failed: %s", e)
        return [], str(e)


async def get_upcoming_events(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Return the cached list of upcoming high-impact events."""
    global _cache, _cache_ts, _last_fetch_error, _last_fetch_state
    now = time.monotonic()
    if not force_refresh and _cache and now - _cache_ts < _CACHE_TTL:
        _last_fetch_state = "ready"
        _last_fetch_error = ""
        return _cache
    events, error = await _fetch_events()
    if error:
        _last_fetch_error = error
        if _cache:
            _last_fetch_state = "stale"
            return _cache
        _last_fetch_state = "skipped" if error == "calendar_key_missing" else "empty"
        return []
    _cache = events
    _cache_ts = now
    _last_fetch_state = "ready" if events else "empty"
    _last_fetch_error = ""
    return _cache


async def get_calendar_feed_status(force_refresh: bool = False) -> dict[str, Any]:
    events = await get_upcoming_events(force_refresh=force_refresh)
    if _last_fetch_state == "ready":
        return {
            "state": "ready",
            "summary": f"Economic calendar ready with {len(events)} upcoming event(s).",
            "count": len(events),
        }
    if _last_fetch_state == "stale":
        return {
            "state": "stale",
            "summary": "Using cached economic calendar events while the upstream refreshes.",
            "count": len(events),
            "error": _last_fetch_error or None,
        }
    if _last_fetch_state == "skipped":
        return {
            "state": "skipped",
            "summary": "Economic calendar key is not configured.",
            "count": len(events),
        }
    return {
        "state": "empty",
        "summary": "Economic calendar returned no upcoming high-impact events.",
        "count": len(events),
        "error": _last_fetch_error or None,
    }


def _event_ts(event: dict) -> float | None:
    """Parse event timestamp to epoch seconds."""
    for field in ("date", "datetime", "time"):
        val = event.get(field)
        if not val:
            continue
        try:
            dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            pass
    return None


async def should_pause(symbols: list[str] | None = None) -> tuple[bool, str]:
    """Return (True, reason) if the agent should hold flat due to an upcoming event.

    For FOREX symbols (e.g. ["EUR_USD", "GBP_JPY"]), only pauses for events that
    affect the traded currencies.  Non-FOREX / unknown symbols pass all events.
    """
    events = await get_upcoming_events()
    now_ts  = datetime.now(timezone.utc).timestamp()
    traded_currencies = _extract_currencies(symbols or [])

    for event in events:
        name = str(event.get("name", event.get("event", "")))
        name_lc = name.lower()
        # Fast pre-filter: must contain at least one high-impact keyword
        if not any(kw in name_lc for kw in _ALL_KEYWORDS):
            continue
        # Currency-aware relevance check
        if not _event_affects_symbols(name_lc, traded_currencies):
            continue

        evt_ts = _event_ts(event)
        if evt_ts is None:
            continue

        secs_away = evt_ts - now_ts
        if abs(secs_away) <= _PAUSE_WINDOW_SECONDS:
            if secs_away >= 0:
                reason = f"Pausing: '{name}' in {secs_away/60:.1f}min"
            else:
                reason = f"Pausing: '{name}' just released ({abs(secs_away)/60:.1f}min ago)"
            logger.info("CALENDAR: %s", reason)
            return True, reason

    return False, ""


async def next_event_summary() -> str:
    """Short string for the dashboard status bar (e.g. 'NFP in 2h 14m')."""
    events  = await get_upcoming_events()
    now_ts  = datetime.now(timezone.utc).timestamp()
    upcoming = []
    for event in events:
        evt_ts = _event_ts(event)
        if evt_ts and evt_ts > now_ts:
            secs = evt_ts - now_ts
            upcoming.append((secs, str(event.get("name", "Event"))))
    if not upcoming:
        return ""
    upcoming.sort()
    secs, name = upcoming[0]
    if secs < 3600:
        return f"{name} in {secs/60:.0f}m"
    return f"{name} in {secs/3600:.1f}h"
