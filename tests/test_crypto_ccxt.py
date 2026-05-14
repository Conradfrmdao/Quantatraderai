import sys


class _FakeExchange:
    def __init__(self, cfg):
        self.cfg = cfg
        self.has = {"fetchPositions": False}
        self.markets = {}
        self.sandbox = False

    def set_sandbox_mode(self, value):
        self.sandbox = value


class _FakeCcxt:
    class okx(_FakeExchange):
        pass

    class bybit(_FakeExchange):
        pass


def test_ccxt_runtime_config_includes_passphrase_and_market(monkeypatch):
    monkeypatch.setitem(sys.modules, "ccxt", _FakeCcxt)
    from src.venues.crypto.ccxt_adapter import CcxtVenue

    venue = CcxtVenue(
        exchange_name="okx",
        api_key="k",
        api_secret="s",
        api_passphrase="p",
        market="futures",
        is_paper=True,
    )
    assert venue.exchange_id == "okx"
    assert venue.asset_class == "crypto_perp"
    assert venue.client.cfg["password"] == "p"
    assert venue.client.cfg["options"]["defaultType"] == "swap"
    assert venue.client.sandbox is True
