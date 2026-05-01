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

logger = logging.getLogger("qunta.intel.calendar")

_cache: list[dict[str, Any]] = []
_cache_ts: float = 0.0
_CACHE_TTL = 3600.0  # refresh hourly

# High-impact event name keywords (case-insensitive)
_HIGH_IMPACT_KEYWORDS = (
    "nonfarm", "non-farm", "cpi", "fomc", "federal reserve",
    "interest rate", "gdp", "ecb", "boe", "bank of england",
    "bank of japan", "boj", "payroll", "unemployment", "inflation",
    "pce", "ppi", "retail sales",
)

_PAUSE_WINDOW_SECONDS = 300  # 5 minutes before + 5 minutes after


async def _fetch_events() -> list[dict[str, Any]]:
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        return []
    url = (
        f"https://api.twelvedata.com/economic_calendar"
        f"?apikey={api_key}&importance=high&outputsize=50"
    )
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json()
        return data.get("result", data.get("data", []))
    except Exception as e:
        logger.warning("Economic calendar fetch failed: %s", e)
        return []


async def get_upcoming_events(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Return the cached list of upcoming high-impact events."""
    global _cache, _cache_ts
    now = time.monotonic()
    if not force_refresh and _cache and now - _cache_ts < _CACHE_TTL:
        return _cache
    _cache = await _fetch_events()
    _cache_ts = now
    return _cache


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

    Checks whether any high-impact event is within ±PAUSE_WINDOW_SECONDS of now.
    `symbols` is reserved for future per-symbol filtering (e.g. skip USD events
    for non-USD pairs).
    """
    events = await get_upcoming_events()
    now_ts  = datetime.now(timezone.utc).timestamp()

    for event in events:
        name = str(event.get("name", event.get("event", ""))).lower()
        if not any(kw in name for kw in _HIGH_IMPACT_KEYWORDS):
            continue

        evt_ts = _event_ts(event)
        if evt_ts is None:
            continue

        secs_away = evt_ts - now_ts
        if abs(secs_away) <= _PAUSE_WINDOW_SECONDS:
            if secs_away >= 0:
                reason = f"Pausing: '{event.get('name', name)}' in {secs_away/60:.1f}min"
            else:
                reason = f"Pausing: '{event.get('name', name)}' just released ({abs(secs_away)/60:.1f}min ago)"
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
