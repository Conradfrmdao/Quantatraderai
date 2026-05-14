from datetime import datetime, timezone

import pytest

from src.risk_manager import RiskManager
from src.venues.forex.market_hours import is_forex_market_open
from src.venues.forex.pips import pip_size, price_distance_pips, spread_pips
from src.venues.forex.position_sizing import notional_to_lots, notional_to_units, units_to_lots
from src.venues.forex.symbols import normalize_forex_symbol, normalize_metatrader_symbol, normalize_oanda_symbol


def test_forex_symbol_normalization():
    assert normalize_forex_symbol("EUR_USD") == "EUR/USD"
    assert normalize_oanda_symbol("eur/usd") == "EUR_USD"
    assert normalize_metatrader_symbol("GBP/USD") == "GBPUSD"
    with pytest.raises(ValueError):
        normalize_forex_symbol("BTC/USDT")


def test_pip_and_spread_math():
    assert pip_size("EUR/USD") == 0.0001
    assert pip_size("USD/JPY") == 0.01
    assert spread_pips("EUR/USD", 1.1000, 1.1002) == pytest.approx(2.0)
    assert price_distance_pips("USD/JPY", 154.20, 154.05) == pytest.approx(15.0)


def test_forex_position_sizing():
    assert notional_to_units(1_100, 1.1) == pytest.approx(1_000)
    assert units_to_lots(1_000) == 0.01
    assert notional_to_lots(110_000, 1.1) == 1.0


def test_forex_market_hours_weekend_guard():
    assert is_forex_market_open(datetime(2026, 5, 14, 12, tzinfo=timezone.utc)) is True
    assert is_forex_market_open(datetime(2026, 5, 16, 12, tzinfo=timezone.utc)) is False
    assert is_forex_market_open(datetime(2026, 5, 17, 21, tzinfo=timezone.utc)) is False
    assert is_forex_market_open(datetime(2026, 5, 17, 22, tzinfo=timezone.utc)) is True


def test_forex_risk_blocks_wide_spread(monkeypatch, account_state_factory):
    monkeypatch.setattr("src.risk_manager.is_forex_market_open", lambda: True)
    risk = RiskManager(venue="oanda", asset_class="forex")
    trade = {
        "asset": "EUR/USD",
        "action": "buy",
        "allocation_usd": 100,
        "current_price": 1.1,
        "spread_pips": 8,
        "sl_price": 1.099,
    }
    ok, reason, _ = risk.validate_trade(trade, account_state_factory(), 10_000)
    assert ok is False
    assert "spread" in reason.lower()
