import pytest

from src.venues.forex.oanda import OandaVenue


def test_oanda_practice_and_live_urls():
    practice = OandaVenue(token="tok", account_id="acct", environment="practice")
    live = OandaVenue(token="tok", account_id="acct", environment="live")
    assert practice.base_url.endswith("api-fxpractice.oanda.com")
    assert live.base_url.endswith("api-fxtrade.oanda.com")


@pytest.mark.asyncio
async def test_oanda_ticker_normalizes_symbol_and_spread(monkeypatch):
    venue = OandaVenue(token="tok", account_id="acct", environment="practice")

    async def fake_get(path, params=None):
        assert params["instruments"] == "EUR_USD"
        return {"prices": [{"bids": [{"price": "1.1000"}], "asks": [{"price": "1.1002"}]}]}

    monkeypatch.setattr(venue, "_get", fake_get)
    ticker = await venue.get_ticker("EUR/USD")
    assert ticker.symbol == "EUR_USD"
    assert ticker.last == pytest.approx(1.1001)
    assert ticker.extra["spread_pips"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_oanda_order_payload_attaches_sl_tp(monkeypatch):
    venue = OandaVenue(token="tok", account_id="acct", environment="practice", is_paper=False)
    posted = {}

    async def fake_post(path, body):
        posted["path"] = path
        posted["body"] = body
        return {"orderFillTransaction": {"id": "123", "units": "1000", "price": "1.1010"}}

    monkeypatch.setattr(venue, "_post", fake_post)
    order = await venue.place_order(
        "EUR/USD",
        "buy",
        1000,
        stop_loss=1.095,
        take_profit=1.11,
    )

    payload = posted["body"]["order"]
    assert payload["instrument"] == "EUR_USD"
    assert payload["stopLossOnFill"]["price"] == "1.095"
    assert payload["takeProfitOnFill"]["price"] == "1.11"
    assert order.status == "filled"
