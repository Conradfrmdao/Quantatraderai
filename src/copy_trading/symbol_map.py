"""Cross-venue symbol mapping for copy trading.

When a leader trades 'BTCUSDT' on Binance, the follower's venue might use a
different symbol format. This module translates the leader's symbol to the
follower's venue equivalent, or returns None if the asset isn't supported.

Supported asset class mappings (extend as you add venues):
  Crypto    → Binance/Bybit/Kraken/Coinbase/Hyperliquid/OKX
  Forex     → OANDA / MetaTrader
  Stocks    → Alpaca / IBKR
"""
from __future__ import annotations

# Canonical asset → per-venue symbol
# Keys: lowercase asset family, e.g. "btc", "eth", "eur_usd", "aapl"
ASSET_REGISTRY: dict[str, dict[str, str]] = {
    "btc":  {"binance": "BTCUSDT", "bybit": "BTCUSDT", "okx": "BTC-USDT",
             "kraken": "XBT/USDT", "coinbase": "BTC-USD", "hyperliquid": "BTC"},
    "eth":  {"binance": "ETHUSDT", "bybit": "ETHUSDT", "okx": "ETH-USDT",
             "kraken": "ETH/USDT", "coinbase": "ETH-USD", "hyperliquid": "ETH"},
    "sol":  {"binance": "SOLUSDT", "bybit": "SOLUSDT", "okx": "SOL-USDT",
             "coinbase": "SOL-USD", "hyperliquid": "SOL"},
    # Forex — majors
    "eur_usd": {"oanda": "EUR_USD", "metatrader": "EURUSD"},
    "gbp_usd": {"oanda": "GBP_USD", "metatrader": "GBPUSD"},
    "usd_jpy": {"oanda": "USD_JPY", "metatrader": "USDJPY"},
    "aud_usd": {"oanda": "AUD_USD", "metatrader": "AUDUSD"},
    "usd_cad": {"oanda": "USD_CAD", "metatrader": "USDCAD"},
    "usd_chf": {"oanda": "USD_CHF", "metatrader": "USDCHF"},
    "nzd_usd": {"oanda": "NZD_USD", "metatrader": "NZDUSD"},
    # Forex — crosses
    "eur_gbp": {"oanda": "EUR_GBP", "metatrader": "EURGBP"},
    "eur_jpy": {"oanda": "EUR_JPY", "metatrader": "EURJPY"},
    "gbp_jpy": {"oanda": "GBP_JPY", "metatrader": "GBPJPY"},
    "aud_jpy": {"oanda": "AUD_JPY", "metatrader": "AUDJPY"},
    # Metals
    "xau_usd": {"oanda": "XAU_USD", "metatrader": "XAUUSD"},
    "xag_usd": {"oanda": "XAG_USD", "metatrader": "XAGUSD"},
    # Indices (MetaTrader CFDs)
    "us30":    {"metatrader": "US30"},
    "nas100":  {"metatrader": "NAS100"},
    "spx500":  {"metatrader": "SPX500"},
    # Stocks
    "aapl": {"alpaca": "AAPL", "ibkr": "AAPL"},
    "tsla": {"alpaca": "TSLA", "ibkr": "TSLA"},
    "nvda": {"alpaca": "NVDA", "ibkr": "NVDA"},
}


def _normalize(symbol: str) -> str:
    """Strip separators and uppercase for matching."""
    return symbol.upper().replace("/", "").replace("-", "").replace("_", "")


def detect_asset_family(symbol: str) -> str | None:
    """Map any concrete symbol back to its canonical key in ASSET_REGISTRY."""
    norm = _normalize(symbol)
    for key, mapping in ASSET_REGISTRY.items():
        for venue_sym in mapping.values():
            if _normalize(venue_sym) == norm:
                return key
    return None


def map_symbol(leader_symbol: str, follower_venue: str) -> str | None:
    """Translate a leader's symbol into the follower-venue's symbol format.

    Returns None if either:
      - the asset isn't in the registry, or
      - the follower's venue doesn't list that asset.
    """
    family = detect_asset_family(leader_symbol)
    if not family:
        return None
    return ASSET_REGISTRY[family].get(follower_venue.lower())
