"""Per-request venue construction.

Authenticated users must not share credentials through ``os.environ``.  This
module carries decrypted venue credentials only inside the current backend
process call stack and builds a fresh adapter instance for the requested user.
Environment-based credentials remain a local/dev fallback through the legacy
registry.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.venues.base import Venue
from src.venues.registry import _CCXT_SHORTCUTS, get_venue


@dataclass(frozen=True)
class VenueRuntimeConfig:
    user_id: str | None
    venue_id: str | None
    venue_name: str
    registry_name: str
    market: str
    is_paper: bool
    network: str = ""
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    account_id: str = ""
    meta_api_token: str = ""
    meta_api_account_id: str = ""
    ccxt_exchange_id: str = ""


def _base_name(name: str) -> str:
    return (name or "").lower().strip().split(":", 1)[0]


def build_venue_from_runtime(config: VenueRuntimeConfig) -> Venue:
    """Build a venue adapter without mutating global environment variables."""
    base = _base_name(config.venue_name or config.registry_name)
    registry = (config.registry_name or config.venue_name or "").lower().strip()
    market = (config.market or "spot").lower()

    if base == "binance" or registry.startswith("binance"):
        from src.venues.crypto.binance import BinanceVenue

        venue = BinanceVenue(
            market=market,
            api_key=config.api_key or None,
            api_secret=config.api_secret or None,
            is_paper=config.is_paper,
        )
    elif base == "hyperliquid":
        from src.trading.hyperliquid_api import HyperliquidAPI
        from src.venues.crypto.hyperliquid import HyperliquidVenue

        api = HyperliquidAPI(
            private_key=config.api_key or None,
            network=config.network or None,
        )
        venue = HyperliquidVenue(api=api, is_paper=config.is_paper)
    elif base == "oanda":
        from src.venues.forex.oanda import OandaVenue

        venue = OandaVenue(
            token=config.api_key or None,
            account_id=config.account_id or None,
            environment="practice" if config.is_paper else "live",
            is_paper=config.is_paper,
        )
    elif base in ("metatrader", "mt4", "mt5"):
        from src.venues.forex.metatrader import MetaTraderVenue

        venue = MetaTraderVenue(
            token=config.meta_api_token or None,
            account_id=config.meta_api_account_id or None,
            is_paper=config.is_paper,
        )
    elif base in _CCXT_SHORTCUTS or base == "ccxt" or registry.startswith("ccxt"):
        from src.venues.crypto.ccxt_adapter import CcxtVenue

        exchange = (
            config.ccxt_exchange_id
            or _CCXT_SHORTCUTS.get(base)
            or (registry.split(":", 1)[1] if registry.startswith("ccxt:") else None)
        )
        venue = CcxtVenue(
            exchange_name=exchange,
            api_key=config.api_key or None,
            api_secret=config.api_secret or None,
            api_passphrase=config.api_passphrase or None,
            market=market,
            is_paper=config.is_paper,
        )
    else:
        # Non-sensitive local/dev fallback for adapters that are still env-driven
        # (stocks, prediction markets, and legacy scripts).
        venue = get_venue(registry or config.venue_name)
        if hasattr(venue, "is_paper"):
            venue.is_paper = config.is_paper

    return venue
