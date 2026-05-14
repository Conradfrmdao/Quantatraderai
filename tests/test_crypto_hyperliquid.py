import pytest

from src.ai.redaction import redact_text
from src.venues.crypto.hyperliquid import HyperliquidVenue


class _FakeHyperliquidApi:
    def __init__(self):
        self.order_calls = 0

    async def place_buy_order(self, *_args, **_kwargs):
        self.order_calls += 1
        return {}


@pytest.mark.asyncio
async def test_hyperliquid_paper_order_never_calls_api():
    api = _FakeHyperliquidApi()
    venue = HyperliquidVenue(api=api, is_paper=True)
    order = await venue.place_order("BTC", "buy", 0.01)
    assert order.status == "filled"
    assert api.order_calls == 0


def test_hyperliquid_private_key_redaction():
    text = "private=0x" + "a" * 64
    assert "a" * 64 not in redact_text(text)
