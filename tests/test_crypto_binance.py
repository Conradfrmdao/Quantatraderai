import sys

import pytest


class _FakeBinanceExchange:
    def __init__(self, cfg):
        self.cfg = cfg
        self.has = {"setLeverage": True}
        self.markets = {}


class _FakeCcxt:
    class binance(_FakeBinanceExchange):
        pass

    class binanceusdm(_FakeBinanceExchange):
        pass


def test_binance_uses_direct_runtime_credentials(monkeypatch):
    monkeypatch.setitem(sys.modules, "ccxt", _FakeCcxt)
    from src.venues.crypto.binance import BinanceVenue

    venue = BinanceVenue(market="spot", api_key="direct-key", api_secret="direct-secret", is_paper=True)
    assert venue.name == "binance:spot"
    assert venue.asset_class == "crypto_spot"
    assert venue.client.cfg["apiKey"] == "direct-key"
    assert venue.client.cfg["secret"] == "direct-secret"
    assert venue.is_paper is True


def test_binance_futures_routing(monkeypatch):
    monkeypatch.setitem(sys.modules, "ccxt", _FakeCcxt)
    from src.venues.crypto.binance import BinanceVenue

    venue = BinanceVenue(market="futures", api_key="k", api_secret="s", is_paper=False)
    assert venue.name == "binance:futures"
    assert venue.asset_class == "crypto_perp"
    assert venue.is_paper is False
