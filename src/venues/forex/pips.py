"""Pip and spread utilities for forex venues."""

from __future__ import annotations

from src.venues.forex.symbols import normalize_forex_symbol


def pip_size(symbol: str) -> float:
    normalized = normalize_forex_symbol(symbol, separator="/")
    quote = normalized.split("/")[1]
    return 0.01 if quote == "JPY" else 0.0001


def spread_pips(symbol: str, bid: float | None, ask: float | None) -> float:
    if not bid or not ask or ask <= bid:
        return 0.0
    return (ask - bid) / pip_size(symbol)


def price_distance_pips(symbol: str, price_a: float, price_b: float) -> float:
    return abs(float(price_a) - float(price_b)) / pip_size(symbol)
