from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.venues.crypto.binance import BinanceVenue
from src.venues.crypto.ccxt_adapter import CcxtVenue
from src.venues.models import Balance, Ticker


@pytest.mark.asyncio
async def test_binance_spot_positions_are_synthesized_from_balances():
    venue = object.__new__(BinanceVenue)
    venue._market = "spot"
    venue._spot_cost_basis = {}
    venue._spot_balances_cache = []
    venue._spot_balances_at = 0.0
    venue.client = SimpleNamespace(markets={
        "BTC/USDT": {
            "symbol": "BTC/USDT",
            "spot": True,
            "active": True,
            "base": "BTC",
            "quote": "USDT",
        }
    })

    async def fake_load_markets():
        return None

    async def fake_get_spot_balances(force: bool = False):
        return [
            Balance(currency="USDT", total=1500.0, available=1500.0),
            Balance(currency="BTC", total=0.05, available=0.05),
        ]

    async def fake_get_ticker(symbol: str):
        return Ticker(symbol=symbol, last=65000.0)

    venue._load_markets = fake_load_markets
    venue._get_spot_balances = fake_get_spot_balances
    venue.get_ticker = fake_get_ticker

    positions = await venue.get_positions()

    assert len(positions) == 1
    assert positions[0].symbol == "BTC/USDT"
    assert positions[0].quantity == pytest.approx(0.05)
    assert positions[0].entry_price == pytest.approx(65000.0)
    assert positions[0].current_price == pytest.approx(65000.0)
    assert positions[0].unrealized_pnl == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_ccxt_spot_cost_basis_is_weighted_after_buy_fill():
    venue = object.__new__(CcxtVenue)
    venue.asset_class = "crypto_spot"
    venue._spot_cost_basis = {"BTC": {"quantity": 0.05, "entry_price": 60000.0}}
    venue._spot_balances_cache = []
    venue._spot_balances_at = 0.0

    async def fake_get_spot_balances(force: bool = False):
        return [Balance(currency="BTC", total=0.10, available=0.10)]

    venue._get_spot_balances = fake_get_spot_balances

    await venue._sync_spot_cost_basis_after_fill("BTC/USDT", "buy", 65000.0)

    assert venue._spot_cost_basis["BTC"]["quantity"] == pytest.approx(0.10)
    assert venue._spot_cost_basis["BTC"]["entry_price"] == pytest.approx(62500.0)
