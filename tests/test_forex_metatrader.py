import pytest

from src.venues.forex.metatrader import MetaTraderVenue


def test_metatrader_lot_sizing():
    assert MetaTraderVenue._to_lots(500) == 0.01
    assert MetaTraderVenue._to_lots(100_000) == 1.0


@pytest.mark.asyncio
async def test_metatrader_paper_order_normalizes_symbol(monkeypatch):
    import src.venues.forex.metatrader as mt_module

    monkeypatch.setattr(mt_module, "_require_metaapi", lambda: None)
    venue = MetaTraderVenue(token="tok", account_id="acct", is_paper=True)
    order = await venue.place_order("EUR/USD", "buy", 100_000, stop_loss=1.09, take_profit=1.12)
    assert order.symbol == "EURUSD"
    assert order.quantity == 1.0
    assert order.status == "paper"
