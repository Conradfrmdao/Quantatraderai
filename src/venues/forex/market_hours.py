"""Forex market-hours helpers.

Retail FX is usually open from Sunday 22:00 UTC through Friday 22:00 UTC.
This is intentionally conservative and testable; broker-specific holidays can
be layered on later.
"""

from __future__ import annotations

from datetime import datetime, timezone


def is_forex_market_open(at: datetime | None = None) -> bool:
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    weekday = now.weekday()
    hour = now.hour
    if weekday == 5:
        return False
    if weekday == 6:
        return hour >= 22
    if weekday == 4:
        return hour < 22
    return True
