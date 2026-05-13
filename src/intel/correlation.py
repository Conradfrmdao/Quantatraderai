"""Rolling cross-asset correlation matrix.

Computes pairwise Pearson correlation of daily returns over a 30-bar window.
Before placing a new trade the agent checks: if the new symbol's correlation
with any existing open position exceeds MAX_CORRELATION, allocation is halved.

Runs locally — no external data fetched (uses what's already in candle_cache).
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

logger = logging.getLogger("quantatraderai.intel.correlation")

MAX_CORRELATION = 0.8   # above this, halve the allocation
WINDOW          = 30    # bars for rolling correlation


def _cache_key(symbol: str, timeframe: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]", "", symbol.upper())
    return f"{normalized}:{timeframe}"


def _returns(closes: list[float]) -> list[float]:
    return [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1] != 0]


def _pearson(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[-n:], b[-n:]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    num    = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    den_a  = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    den_b  = math.sqrt(sum((x - mean_b) ** 2 for x in b))
    if den_a == 0 or den_b == 0:
        return 0.0
    return num / (den_a * den_b)


def compute_correlation_matrix(
    candle_cache: dict[str, list[dict]],
    symbols: list[str],
    timeframe: str = "1h",
) -> dict[str, dict[str, float]]:
    """Return pairwise correlation dict. Keys are symbol strings."""
    # Extract close series per symbol
    series: dict[str, list[float]] = {}
    for sym in symbols:
        key    = _cache_key(sym, timeframe)
        candles = candle_cache.get(key, [])
        if len(candles) >= WINDOW + 1:
            closes = [c["close"] for c in candles[-WINDOW - 1:]]
            series[sym] = _returns(closes)

    matrix: dict[str, dict[str, float]] = {}
    syms = list(series.keys())
    for i, a in enumerate(syms):
        matrix[a] = {}
        for b in syms:
            if a == b:
                matrix[a][b] = 1.0
            elif b in matrix and a in matrix[b]:
                matrix[a][b] = matrix[b][a]
            else:
                matrix[a][b] = round(_pearson(series[a], series[b]), 4)
    return matrix


def should_reduce_allocation(
    new_symbol: str,
    open_positions: list[dict],
    correlation_matrix: dict[str, dict[str, float]],
) -> tuple[bool, float, str]:
    """Return (should_reduce, multiplier, reason).

    multiplier is 0.5 if any correlated position exceeds threshold, else 1.0.
    """
    corr_row = correlation_matrix.get(new_symbol, {})
    for pos in open_positions:
        pos_sym = pos.get("symbol", "")
        corr    = abs(corr_row.get(pos_sym, 0.0))
        if corr >= MAX_CORRELATION:
            reason = f"{new_symbol}↔{pos_sym} correlation={corr:.2f} ≥ {MAX_CORRELATION}"
            logger.info("CORRELATION: reducing allocation — %s", reason)
            return True, 0.5, reason
    return False, 1.0, ""


def format_matrix_summary(matrix: dict[str, dict[str, float]]) -> str:
    """Compact text for LLM context injection."""
    lines = []
    seen  = set()
    for a, row in matrix.items():
        for b, corr in row.items():
            if a == b: continue
            key = tuple(sorted([a, b]))
            if key in seen: continue
            seen.add(key)
            if abs(corr) > 0.5:
                lines.append(f"{a}↔{b}: {corr:+.2f}")
    return "Correlations: " + ", ".join(lines) if lines else ""
