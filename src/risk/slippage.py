"""G24: Liquidity-aware slippage prediction.

Before placing a large order, estimates slippage from the order book depth
and adjusts take-profit downward to account for fill cost.

Usage:
    from src.risk.slippage import estimate_slippage_pct, adjust_tp_for_slippage
    slip_pct = await estimate_slippage_pct(venue, symbol, qty_usd)
    tp = adjust_tp_for_slippage(raw_tp, current_price, action, slip_pct)
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("quantatraderai.slippage")


async def estimate_slippage_pct(
    symbol: str,
    qty_usd: float,
    venue_name: str = "binance",
) -> float:
    """Estimate market-order slippage / spread cost as a fraction (e.g. 0.002 = 0.2%).

    - CEX crypto (Binance/Bybit/OKX): walks the live order book.
    - FOREX (OANDA/MetaTrader): returns a spread-based estimate by pair tier.
    - All others: falls back to 5 bps.
    """
    DEFAULT_SLIP = 0.0005  # 5 bps — conservative for liquid markets
    if qty_usd <= 0:
        return 0.0

    # FOREX: use spread tiers (no CEX order book available).
    # Major pairs (EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD) ~10 bps.
    # XAU/USD and minors: ~20 bps.  Exotics: ~50 bps.
    if venue_name in ("oanda", "metatrader"):
        sym_upper = symbol.upper().replace("_", "").replace("/", "").replace("-", "")
        _MAJORS = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"}
        _METALS = {"XAUUSD", "XAGUSD", "XPTUSD"}
        if sym_upper in _MAJORS:
            return 0.0010  # ~10 bps / 1 pip on a major
        if sym_upper in _METALS:
            return 0.0020  # gold/silver spreads are wider
        return 0.0050  # exotic pairs

    if venue_name not in ("binance", "bybit", "okx"):
        return DEFAULT_SLIP  # only CEX order-book walk is supported

    try:
        import aiohttp as ah
        ticker = symbol.upper().replace("/", "")
        url    = f"https://api.binance.com/api/v3/depth?symbol={ticker}&limit=20"
        async with ah.ClientSession() as session:
            async with session.get(url, timeout=ah.ClientTimeout(total=3)) as resp:
                if resp.status != 200:
                    return DEFAULT_SLIP
                book = await resp.json()

        # Simulate walking the ask side for a buy order
        asks     = [(float(p), float(q)) for p, q in book.get("asks", [])]
        bids     = [(float(p), float(q)) for p, q in book.get("bids", [])]
        if not asks or not bids:
            return DEFAULT_SLIP

        mid_price  = (asks[0][0] + bids[0][0]) / 2
        remaining  = qty_usd
        total_cost = 0.0
        total_qty  = 0.0

        for price, qty_native in asks:
            fill_cost = price * qty_native
            if fill_cost >= remaining:
                partial = remaining / price
                total_cost += remaining
                total_qty  += partial
                remaining   = 0
                break
            total_cost += fill_cost
            total_qty  += qty_native
            remaining  -= fill_cost

        if total_qty <= 0:
            return DEFAULT_SLIP

        avg_fill = total_cost / total_qty
        slippage = abs(avg_fill - mid_price) / mid_price
        return round(min(slippage, 0.05), 6)  # cap at 5% (extreme case)

    except Exception as e:
        logger.debug("Slippage estimate failed: %s — using default", e)
        return DEFAULT_SLIP


def adjust_tp_for_slippage(
    tp_price: float | None,
    entry_price: float,
    action: str,
    slippage_pct: float,
) -> float | None:
    """Nudge TP away from entry by the slippage cost so we still net the intended profit.

    Buy: TP moves up by slippage  (need a higher exit to compensate for fill cost)
    Sell: TP moves down by slippage
    """
    if not tp_price or not entry_price or slippage_pct <= 0:
        return tp_price

    adjustment = entry_price * slippage_pct
    if action == "buy":
        return round(tp_price + adjustment, 6)
    else:
        return round(tp_price - adjustment, 6)
