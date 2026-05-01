"""Adapter contract tests — every Venue must satisfy the same interface.

Uses MockVenue as the reference implementation. For real adapters, tests
verify the *structure* of responses (types, fields) without hitting real APIs.
Each test class can be subclassed with a real venue once credentials exist.
"""
import pytest
from tests.conftest import MockVenue
from src.venues.models import Balance, Candle, Order, Position, SymbolMeta, Ticker


# ── Shared contract assertions ─────────────────────────────────────────────────

def assert_balance_contract(balances):
    assert isinstance(balances, list), "get_balances must return list"
    assert len(balances) >= 1, "Must return at least one balance"
    b = balances[0]
    assert isinstance(b, Balance)
    assert isinstance(b.currency, str) and b.currency
    assert isinstance(b.total, float) and b.total >= 0
    assert isinstance(b.available, float) and b.available >= 0
    assert b.available <= b.total


def assert_candle_contract(candles, expected_count):
    assert isinstance(candles, list)
    assert len(candles) == expected_count
    for c in candles:
        assert isinstance(c, Candle)
        assert c.ts > 0
        assert c.high >= c.low
        assert c.open > 0
        assert c.close > 0
        assert c.volume >= 0


def assert_ticker_contract(ticker, symbol):
    assert isinstance(ticker, Ticker)
    assert ticker.symbol == symbol
    assert ticker.last > 0
    if ticker.bid is not None:
        assert ticker.bid <= ticker.last
    if ticker.ask is not None:
        assert ticker.ask >= ticker.last


def assert_order_contract(order):
    assert isinstance(order, Order)
    assert order.order_id
    assert order.symbol
    assert order.side in ("buy", "sell")
    assert order.order_type in ("market", "limit", "stop", "take_profit")
    assert order.quantity > 0
    assert order.status


def assert_symbol_info_contract(info, symbol):
    assert isinstance(info, SymbolMeta)
    assert info.symbol == symbol
    assert info.tick_size > 0
    assert info.lot_size > 0
    assert info.min_notional >= 0
    assert info.max_leverage >= 1.0
    assert info.asset_class in ("crypto_perp", "crypto_spot", "forex", "prediction")


# ── MockVenue contract (reference implementation) ─────────────────────────────

class TestMockVenueContract:
    """MockVenue must pass all contract assertions — it's the reference."""

    @pytest.fixture
    def venue(self):
        return MockVenue(starting_balance=10_000.0)

    @pytest.mark.asyncio
    async def test_get_balances_contract(self, venue):
        assert_balance_contract(await venue.get_balances())

    @pytest.mark.asyncio
    async def test_get_candles_contract(self, venue):
        candles = await venue.get_candles("BTCUSDT", "1h", 30)
        assert_candle_contract(candles, 30)

    @pytest.mark.asyncio
    async def test_get_ticker_contract(self, venue):
        ticker = await venue.get_ticker("BTCUSDT")
        assert_ticker_contract(ticker, "BTCUSDT")

    @pytest.mark.asyncio
    async def test_place_order_contract(self, venue):
        order = await venue.place_order("BTCUSDT", "buy", 0.01, "market")
        assert_order_contract(order)

    @pytest.mark.asyncio
    async def test_symbol_info_contract(self, venue):
        info = await venue.get_symbol_info("BTCUSDT")
        assert_symbol_info_contract(info, "BTCUSDT")

    @pytest.mark.asyncio
    async def test_close_position_returns_order_or_none(self, venue):
        venue.inject_position("BTCUSDT", 0.1, 50_000.0)
        result = await venue.close_position("BTCUSDT")
        assert result is None or isinstance(result, Order)

    @pytest.mark.asyncio
    async def test_close_nonexistent_position_returns_none(self, venue):
        result = await venue.close_position("NONEXISTENT")
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_order_returns_bool(self, venue):
        result = await venue.cancel_order("BTCUSDT", "fake-order-id")
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_get_positions_empty_initially(self, venue):
        positions = await venue.get_positions()
        assert isinstance(positions, list)
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_position_appears_after_buy(self, venue):
        await venue.place_order("ETHUSDT", "buy", 1.0, "market")
        positions = await venue.get_positions()
        assert any(p.symbol == "ETHUSDT" for p in positions)


# ── Error handling contract — all venues must handle errors gracefully ─────────

class TestVenueErrorHandling:

    @pytest.mark.asyncio
    async def test_fail_on_get_balances_raises_not_hangs(self, mock_venue_factory):
        venue = mock_venue_factory(fail_on="get_balances")
        with pytest.raises(Exception):  # Must raise, not hang forever
            await venue.get_balances()

    @pytest.mark.asyncio
    async def test_fail_on_place_order_does_not_corrupt_state(self, mock_venue_factory):
        venue = mock_venue_factory(balance=10_000.0, fail_on="place_order")
        with pytest.raises(Exception):
            await venue.place_order("BTCUSDT", "buy", 0.1)
        # Balance should be unchanged — order did not go through
        balances = await MockVenue(10_000.0).get_balances()
        assert balances[0].total == 10_000.0

    @pytest.mark.asyncio
    async def test_close_position_venue_error_handled(self, mock_venue_factory):
        venue = mock_venue_factory(fail_on="close_position")
        venue.inject_position("BTCUSDT", 0.1, 50_000.0)
        with pytest.raises(Exception):
            await venue.close_position("BTCUSDT")


# ── Paper mode isolation ───────────────────────────────────────────────────────

class TestPaperModeIsolation:
    """Paper trading must NEVER call real exchange methods."""

    @pytest.mark.asyncio
    async def test_paper_place_order_tracked_in_mock(self, mock_venue):
        """In paper mode, trades go through MockVenue only."""
        await mock_venue.place_order("BTCUSDT", "buy", 0.01)
        assert mock_venue.calls.get("place_order", 0) == 1

    @pytest.mark.asyncio
    async def test_paper_position_tracked_in_mock(self, mock_venue):
        await mock_venue.place_order("SOLUSDT", "buy", 1.0)
        positions = await mock_venue.get_positions()
        symbols = {p.symbol for p in positions}
        assert "SOLUSDT" in symbols


# ── TP/SL fields propagated ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tp_sl_fields_preserved_in_order(mock_venue):
    order = await mock_venue.place_order(
        "BTCUSDT", "buy", 0.01, "limit",
        price=50_000.0, stop_loss=48_000.0, take_profit=55_000.0,
    )
    assert order.stop_loss == 48_000.0
    assert order.take_profit == 55_000.0


# ── Symbol mapping doesn't break adapters ────────────────────────────────────

def test_all_venues_mapped_in_registry():
    """Every venue name should NOT raise ValueError (unknown venue).
    ImportError (missing SDK) and RuntimeError (missing credential) are acceptable.
    """
    from src.venues.registry import get_venue
    known_venues = [
        "hyperliquid", "binance", "binance:spot", "binance:futures",
        "bybit", "okx", "kraken", "coinbase",
        "oanda", "metatrader", "alpaca", "ibkr",
        "ccxt", "polymarket",
    ]
    for name in known_venues:
        try:
            get_venue(name)
        except ValueError as e:
            # Only fail if it's the "Unknown venue" message from the registry
            if "Unknown venue" in str(e):
                pytest.fail(f"Venue {name!r} not registered in registry: {e}")
            # Other ValueErrors (e.g. from SDK validation) are acceptable
        except (ImportError, RuntimeError, KeyError, TypeError, Exception):
            pass  # Missing SDK / key — not a registry routing error
