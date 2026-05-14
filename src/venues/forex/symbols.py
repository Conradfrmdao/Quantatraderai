"""Forex symbol normalization helpers."""

from __future__ import annotations

import re


_SYMBOL_RE = re.compile(r"^([A-Z]{3})[/_\-]?([A-Z]{3})$")


def normalize_forex_symbol(symbol: str, separator: str = "/") -> str:
    raw = str(symbol or "").strip().upper()
    match = _SYMBOL_RE.match(raw)
    if not match:
        raise ValueError(f"Unsupported forex symbol format: {symbol!r}")
    return f"{match.group(1)}{separator}{match.group(2)}"


def normalize_oanda_symbol(symbol: str) -> str:
    return normalize_forex_symbol(symbol, separator="_")


def normalize_metatrader_symbol(symbol: str) -> str:
    # Brokers may suffix symbols (EURUSD.r, EURUSDm). We only normalize plain
    # majors/minors here and let the MetaAPI broker spec reject exotic variants.
    return normalize_forex_symbol(symbol, separator="")
