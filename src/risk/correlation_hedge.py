"""G23: Cross-venue correlation hedge.

Before placing a new trade, checks if the user already holds a correlated
position on any venue. If so, reduces the new trade size to avoid
doubling concentration risk.

Usage:
    from src.risk.correlation_hedge import compute_hedge_scalar
    scalar = await compute_hedge_scalar(user_id, symbol, action, existing_positions)
    adjusted_alloc = alloc * scalar
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger("quantatraderai.correlation_hedge")

# Hard-coded correlation buckets. 1.0 = same asset, ~0.8 = highly correlated.
# In a future iteration replace with live rolling correlations from price data.
CORRELATION_GROUPS: list[set[str]] = [
    # BTC cluster
    {"BTCUSDT", "BTCUSD", "BTC/USD", "BTC/USDT", "XBTUSDT"},
    # ETH cluster
    {"ETHUSDT", "ETHUSD", "ETH/USD", "ETH/USDT"},
    # Major US indices cluster
    {"US30", "^DJI", "NAS100", "^NDX", "SPX500", "^GSPC"},
    # Gold / safe-haven
    {"XAUUSD", "GC=F", "XAGUSD", "SI=F"},
    # Energy
    {"USOIL", "CL=F", "WTI"},
    # USD-positive pairs (long = long USD): USDCHF, USDJPY, USDCAD move together
    {"USDCHF", "USD_CHF", "USDJPY", "USD_JPY", "USDCAD", "USD_CAD"},
    # USD-negative pairs (long = short USD): EUR, GBP, AUD, NZD move together vs USD
    {"EURUSD", "EUR_USD", "EURUSD=X", "GBPUSD", "GBP_USD", "GBPUSD=X",
     "AUDUSD", "AUD_USD", "NZDUSD", "NZD_USD"},
]


def _same_group(a: str, b: str) -> bool:
    a_up, b_up = a.upper(), b.upper()
    for group in CORRELATION_GROUPS:
        if any(a_up in s or s in a_up for s in group):
            if any(b_up in s or s in b_up for s in group):
                return True
    return False


async def compute_hedge_scalar(
    user_id: str | None,
    new_symbol: str,
    new_action: str,
    existing_positions: list[dict],
) -> float:
    """Return a scalar (0.0–1.0) by which to multiply the proposed allocation.

    - No existing correlation → 1.0 (full size)
    - 1 correlated position in same direction → 0.5 (half size)
    - 2+ correlated positions in same direction → 0.25 (quarter size)
    - Opposite direction (natural hedge) → 1.2 (slight bonus, market-neutral)
    """
    if not existing_positions:
        return 1.0

    same_dir   = 0
    opposite_dir = 0

    for pos in existing_positions:
        sym = pos.get("symbol", "")
        qty = float(pos.get("quantity", 0))
        if not _same_group(new_symbol, sym):
            continue

        pos_direction = "buy" if qty > 0 else "sell"
        if pos_direction == new_action:
            same_dir += 1
        else:
            opposite_dir += 1

    if same_dir == 0:
        scalar = min(1.2, 1.0 + 0.1 * opposite_dir)  # slight bonus for hedging
    elif same_dir == 1:
        scalar = 0.5
    else:
        scalar = 0.25

    if scalar != 1.0:
        logger.info(
            "Correlation hedge: %s %s | same_dir=%d opp=%d → scalar=%.2f",
            new_action, new_symbol, same_dir, opposite_dir, scalar,
        )
    return scalar
