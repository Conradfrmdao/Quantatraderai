"""Venue registry — resolve a venue name to an adapter instance.

Supported names
---------------
  hyperliquid
  binance | binance:spot | binance:futures
  bybit | okx | kraken | coinbase           (all via CCXT)
  ccxt | ccxt:<exchange>                    (any CCXT exchange)
  oanda
  metatrader | mt4 | mt5                   (via MetaAPI — requires metaapi-cloud-sdk)
  alpaca                                    (US stocks — requires alpaca-py)
  ibkr                                      (stocks/options/futures — requires ib_insync)
"""

from __future__ import annotations

from src.venues.base import Venue

# CCXT exchange IDs for named shortcuts
_CCXT_SHORTCUTS: dict[str, str] = {
    "bybit":    "bybit",
    "okx":      "okx",
    "kraken":   "kraken",
    "coinbase": "coinbaseinternational",
    "kucoin":   "kucoin",
    "gate":     "gate",
    "mexc":     "mexc",
    "bitget":   "bitget",
}


def get_venue(name: str | None) -> Venue:
    name = (name or "hyperliquid").lower().strip()

    # ── Hyperliquid ───────────────────────────────────────────────────────────
    if name == "hyperliquid":
        from src.venues.crypto.hyperliquid import HyperliquidVenue
        return HyperliquidVenue()

    # ── Binance (native adapter) ───────────────────────────────────────────────
    if name in ("binance", "binance:futures", "binance:spot"):
        from src.venues.crypto.binance import BinanceVenue
        market = "spot" if name.endswith("spot") else "futures"
        return BinanceVenue(market=market)

    # ── Named CCXT shortcuts (Bybit / OKX / Kraken / Coinbase / etc.) ─────────
    if name in _CCXT_SHORTCUTS:
        from src.venues.crypto.ccxt_adapter import CcxtVenue
        return CcxtVenue(exchange_name=_CCXT_SHORTCUTS[name])

    # ── Generic CCXT (ccxt or ccxt:<exchange>) ────────────────────────────────
    if name.startswith("ccxt"):
        from src.venues.crypto.ccxt_adapter import CcxtVenue
        exchange = name.split(":", 1)[1] if ":" in name else None
        return CcxtVenue(exchange_name=exchange)

    # ── OANDA (forex) ─────────────────────────────────────────────────────────
    if name == "oanda":
        from src.venues.forex.oanda import OandaVenue
        return OandaVenue()

    # ── MetaTrader via MetaAPI ────────────────────────────────────────────────
    if name in ("metatrader", "mt4", "mt5"):
        from src.venues.forex.metatrader import MetaTraderVenue
        return MetaTraderVenue()

    # ── Alpaca (US stocks/options) ────────────────────────────────────────────
    if name == "alpaca":
        from src.venues.stocks.alpaca import AlpacaVenue
        return AlpacaVenue()

    # ── Interactive Brokers ───────────────────────────────────────────────────
    if name in ("ibkr", "interactivebrokers"):
        from src.venues.stocks.ibkr import IBKRVenue
        return IBKRVenue()

    # ── Polymarket (prediction markets) ────────────────────────────────────────
    if name == "polymarket":
        from src.venues.predictions.polymarket import PolymarketVenue
        return PolymarketVenue()

    raise ValueError(
        f"Unknown venue: {name!r}. "
        "Supported: hyperliquid | binance[:spot|:futures] | bybit | okx | kraken | "
        "coinbase | ccxt[:<exchange>] | oanda | metatrader | alpaca | ibkr"
    )
