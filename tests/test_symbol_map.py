"""Unit tests — cross-venue symbol mapping.

Tests that symbols translate correctly between Binance, Hyperliquid, OANDA,
MetaTrader, Alpaca, and that unknowns return None (not crash).
"""
import pytest
from src.copy_trading.symbol_map import map_symbol, detect_asset_family, ASSET_REGISTRY


# ── Family detection ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("symbol,expected_family", [
    ("BTCUSDT",   "btc"),
    ("BTC/USDT",  "btc"),
    ("BTC-USDT",  "btc"),
    ("ETHUSDT",   "eth"),
    ("ETH/USDT",  "eth"),
    ("SOLUSDT",   "sol"),
    ("EURUSD",    "eur_usd"),
    ("EUR_USD",   "eur_usd"),
    ("XAUUSD",    "xau_usd"),
    ("AAPL",      "aapl"),
    ("TSLA",      "tsla"),
])
def test_detect_family(symbol, expected_family):
    assert detect_asset_family(symbol) == expected_family


def test_unknown_symbol_returns_none():
    assert detect_asset_family("NOPE/NOBODY") is None


# ── Symbol mapping ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("leader_sym,follower_venue,expected", [
    ("BTCUSDT",  "binance",     "BTCUSDT"),
    ("BTCUSDT",  "hyperliquid", "BTC"),
    ("BTCUSDT",  "okx",         "BTC-USDT"),
    ("BTCUSDT",  "kraken",      "XBT/USDT"),
    ("BTCUSDT",  "coinbase",    "BTC-USD"),
    ("ETHUSDT",  "bybit",       "ETHUSDT"),
    ("EUR_USD",  "oanda",       "EUR_USD"),
    ("EUR_USD",  "metatrader",  "EURUSD"),
    ("XAUUSD",   "oanda",       "XAU_USD"),
    ("XAUUSD",   "metatrader",  "XAUUSD"),
    ("AAPL",     "alpaca",      "AAPL"),
    ("AAPL",     "ibkr",        "AAPL"),
])
def test_map_symbol_known(leader_sym, follower_venue, expected):
    assert map_symbol(leader_sym, follower_venue) == expected


def test_map_symbol_unknown_family_returns_none():
    assert map_symbol("UNKNOWNCOIN/USDT", "binance") is None


def test_map_symbol_known_family_unknown_venue_returns_none():
    # BTC family exists but "polymarket" is not in it
    assert map_symbol("BTCUSDT", "polymarket") is None


def test_map_symbol_case_insensitive_venue():
    assert map_symbol("BTCUSDT", "BINANCE") == map_symbol("BTCUSDT", "binance")


def test_registry_completeness():
    # Every family must have at least one venue mapping
    for family, mapping in ASSET_REGISTRY.items():
        assert len(mapping) >= 1, f"Family {family!r} has no venues"
