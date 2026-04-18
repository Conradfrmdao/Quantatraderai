"""Venue registry — resolve a venue name (or `ccxt:<exchange>`) to an adapter."""

from __future__ import annotations

from src.venues.base import Venue


def get_venue(name: str | None) -> Venue:
    """Return an initialized venue adapter for `name`.

    Supported names:
      - "hyperliquid"
      - "ccxt" or "ccxt:<exchange>" (e.g. "ccxt:binance") — CCXT_EXCHANGE falls
        back to the .env value if no suffix is given.
      - "oanda"
    """
    name = (name or "hyperliquid").lower().strip()

    if name == "hyperliquid":
        from src.venues.crypto.hyperliquid import HyperliquidVenue
        return HyperliquidVenue()

    if name in ("binance", "binance:futures", "binance:spot"):
        from src.venues.crypto.binance import BinanceVenue
        market = "spot" if name.endswith("spot") else "futures"
        return BinanceVenue(market=market)

    if name.startswith("ccxt"):
        from src.venues.crypto.ccxt_adapter import CcxtVenue
        exchange = None
        if ":" in name:
            _, exchange = name.split(":", 1)
        return CcxtVenue(exchange_name=exchange)

    if name == "oanda":
        from src.venues.forex.oanda import OandaVenue
        return OandaVenue()

    raise ValueError(
        f"Unknown venue: {name!r}. "
        "Use hyperliquid | binance[:spot|:futures] | ccxt[:<exchange>] | oanda."
    )
