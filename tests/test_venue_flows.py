"""Integration tests — venue connection and test flows.

Flow A: Connect venue → encrypt → store → test connection
Tests _inject_venue_env, get_venue routing, and MockVenue responses.
No real network calls — all venues mocked or stubbed.
"""
import os
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ── _inject_venue_env correctness ─────────────────────────────────────────────

def test_inject_binance_sets_env(monkeypatch, mock_env):
    from src.server import _inject_venue_env
    _inject_venue_env(
        "binance", "futures", is_paper=True,
        api_key="k", api_secret="s",
        api_passphrase="", account_id="", network="",
        meta_token="", meta_account_id="", ccxt_exchange="",
    )
    assert os.environ["BINANCE_API_KEY"] == "k"
    assert os.environ["BINANCE_API_SECRET"] == "s"
    assert os.environ["BINANCE_SANDBOX"] == "true"
    assert os.environ["BINANCE_MARKET"] == "futures"


def test_inject_binance_live_sandbox_false(monkeypatch, mock_env):
    from src.server import _inject_venue_env
    _inject_venue_env("binance", "spot", is_paper=False,
                      api_key="k2", api_secret="s2",
                      api_passphrase="", account_id="", network="",
                      meta_token="", meta_account_id="", ccxt_exchange="")
    assert os.environ["BINANCE_SANDBOX"] == "false"


def test_inject_ccxt_sets_market_env(mock_env):
    from src.server import _inject_venue_env
    _inject_venue_env("ccxt", "futures", is_paper=True,
                      api_key="ck", api_secret="cs",
                      api_passphrase="", account_id="", network="",
                      meta_token="", meta_account_id="", ccxt_exchange="bybit")
    assert os.environ["CCXT_MARKET"] == "futures"
    assert os.environ["CCXT_SANDBOX"] == "true"


def test_inject_oanda_sets_env(mock_env):
    from src.server import _inject_venue_env
    _inject_venue_env("oanda", "spot", is_paper=True,
                      api_key="oanda-token", api_secret="",
                      api_passphrase="", account_id="101-001-12345-001", network="",
                      meta_token="", meta_account_id="", ccxt_exchange="")
    assert os.environ["OANDA_API_TOKEN"] == "oanda-token"
    assert os.environ["OANDA_ACCOUNT_ID"] == "101-001-12345-001"
    assert os.environ["OANDA_ENV"] == "practice"


def test_inject_oanda_live(mock_env):
    from src.server import _inject_venue_env
    _inject_venue_env("oanda", "spot", is_paper=False,
                      api_key="live-token", api_secret="",
                      api_passphrase="", account_id="101-001-99999-001", network="",
                      meta_token="", meta_account_id="", ccxt_exchange="")
    assert os.environ["OANDA_ENV"] == "live"


def test_inject_polymarket_sets_env(mock_env):
    from src.server import _inject_venue_env
    _inject_venue_env("polymarket", "spot", is_paper=True,
                      api_key="0x" + "a" * 62, api_secret="",
                      api_passphrase="", account_id="", network="137",
                      meta_token="", meta_account_id="", ccxt_exchange="")
    assert os.environ["POLYMARKET_ETH_PRIVATE_KEY"].startswith("0x")
    assert os.environ["POLYMARKET_CHAIN_ID"] == "137"
    assert os.environ["POLYMARKET_IS_PAPER"] == "true"


def test_inject_metatrader_sets_env(mock_env):
    from src.server import _inject_venue_env
    _inject_venue_env("metatrader", "spot", is_paper=False,
                      api_key="", api_secret="",
                      api_passphrase="", account_id="", network="",
                      meta_token="mt-cloud-token", meta_account_id="acct-123",
                      ccxt_exchange="")
    assert os.environ["METAAPI_TOKEN"] == "mt-cloud-token"
    assert os.environ["METAAPI_ACCOUNT_ID"] == "acct-123"
    assert os.environ["MT_IS_PAPER"] == "false"


# ── Registry routing ───────────────────────────────────────────────────────────

def test_registry_raises_for_unknown_venue(mock_env):
    from src.venues.registry import get_venue
    with pytest.raises(ValueError, match="Unknown venue"):
        get_venue("not-a-real-venue-xyz")


def test_registry_routes_polymarket(mock_env, monkeypatch):
    """Polymarket entry is in registry and requires private key."""
    from src.venues.registry import get_venue
    monkeypatch.setenv("POLYMARKET_ETH_PRIVATE_KEY", "")
    with pytest.raises(RuntimeError, match="POLYMARKET_ETH_PRIVATE_KEY"):
        get_venue("polymarket")


# ── MockVenue contract tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_venue_get_balances(mock_venue):
    balances = await mock_venue.get_balances()
    assert len(balances) == 1
    assert balances[0].currency == "USDT"
    assert balances[0].total == 10_000.0


@pytest.mark.asyncio
async def test_mock_venue_place_order_reduces_balance(mock_venue):
    await mock_venue.place_order("BTCUSDT", "buy", 0.1, "market")
    balances = await mock_venue.get_balances()
    # cost = 0.1 * 50_000 = 5_000
    assert balances[0].total < 10_000.0


@pytest.mark.asyncio
async def test_mock_venue_position_appears_after_buy(mock_venue):
    await mock_venue.place_order("BTCUSDT", "buy", 0.2, "market")
    positions = await mock_venue.get_positions()
    assert any(p.symbol == "BTCUSDT" for p in positions)


@pytest.mark.asyncio
async def test_mock_venue_close_position_removes_it(mock_venue):
    mock_venue.inject_position("BTCUSDT", 0.1, 50_000.0)
    await mock_venue.close_position("BTCUSDT")
    positions = await mock_venue.get_positions()
    assert not any(p.symbol == "BTCUSDT" for p in positions)


@pytest.mark.asyncio
async def test_mock_venue_fail_on_get_balances(mock_venue_factory):
    venue = mock_venue_factory(fail_on="get_balances")
    with pytest.raises(RuntimeError, match="simulated failure"):
        await venue.get_balances()


@pytest.mark.asyncio
async def test_mock_venue_fail_on_place_order(mock_venue_factory):
    venue = mock_venue_factory(fail_on="place_order")
    with pytest.raises(RuntimeError):
        await venue.place_order("BTCUSDT", "buy", 0.1)


@pytest.mark.asyncio
async def test_mock_venue_candles_return_correct_count(mock_venue):
    candles = await mock_venue.get_candles("BTCUSDT", "1h", 50)
    assert len(candles) == 50


@pytest.mark.asyncio
async def test_mock_venue_symbol_info_fields(mock_venue):
    info = await mock_venue.get_symbol_info("BTCUSDT")
    assert info.tick_size > 0
    assert info.min_notional > 0
    assert info.max_leverage >= 1.0


# ── Test venue pre-flight checks ──────────────────────────────────────────────

_SUPABASE_READER = "src.services.supabase_reader.get_user_venues"


def _request_for(user_id: str | None = None):
    import os
    headers = {}
    if os.getenv("PYTHON_INTERNAL_TOKEN"):
        headers["x-internal-token"] = os.getenv("PYTHON_INTERNAL_TOKEN", "")
    if user_id:
        headers["x-user-id"] = user_id
    return SimpleNamespace(headers=headers)


@pytest.mark.asyncio
async def test_preflight_rejects_binance_missing_key(mock_env):
    """The test_venue endpoint returns helpful errors for missing credentials."""
    from src.server import VenueTestRequest, test_venue

    with patch(_SUPABASE_READER, new=AsyncMock(return_value=[{
        "type": "BINANCE", "apiKey": "", "apiSecret": "",
        "apiPassphrase": "", "accountId": "", "network": "",
        "metaApiToken": "", "metaApiAccountId": "", "ccxtExchangeId": "",
    }])):
        req = VenueTestRequest(userId="clerk-123", venue="binance", isPaper=True)
        result = await test_venue(_request_for("clerk-123"), req)
    assert result["ok"] is False
    assert "apiKey" in result["error"] or "requires" in result["error"] or "key" in result["error"].lower()


@pytest.mark.asyncio
async def test_binance_connection_test_defaults_to_spot_market(mock_env):
    """Generic Binance venue tests should use spot, matching the dashboard start flow."""
    from src.server import VenueTestRequest, test_venue
    from tests.conftest import MockVenue

    venue_row = {
        "type": "BINANCE",
        "apiKey": "BINANCEKEY1234567890ABCDE",
        "apiSecret": "BINANCESECRET1234567890ABCDE",
        "apiPassphrase": "",
        "accountId": "",
        "network": "",
        "market": "spot",
        "metaApiToken": "",
        "metaApiAccountId": "",
        "ccxtExchangeId": "",
    }

    with patch(_SUPABASE_READER, new=AsyncMock(return_value=[venue_row])):
        with patch("src.server.build_venue_from_runtime", return_value=MockVenue(starting_balance=321.0)) as build_mock:
            result = await test_venue(
                _request_for("clerk-123"),
                VenueTestRequest(userId="clerk-123", venue="binance", isPaper=True),
            )

    assert result["ok"] is True
    runtime_config = build_mock.call_args.args[0]
    assert runtime_config.venue_name == "binance"
    assert runtime_config.registry_name == "binance:spot"
    assert runtime_config.market == "spot"


@pytest.mark.asyncio
async def test_binance_connection_test_uses_saved_market_mode(mock_env):
    from src.server import VenueTestRequest, test_venue
    from tests.conftest import MockVenue

    venue_row = {
        "type": "BINANCE",
        "apiKey": "BINANCEKEY1234567890ABCDE",
        "apiSecret": "BINANCESECRET1234567890ABCDE",
        "apiPassphrase": "",
        "accountId": "",
        "network": "",
        "market": "futures",
        "metaApiToken": "",
        "metaApiAccountId": "",
        "ccxtExchangeId": "",
    }

    with patch(_SUPABASE_READER, new=AsyncMock(return_value=[venue_row])):
        with patch("src.server.build_venue_from_runtime", return_value=MockVenue(starting_balance=777.0)) as build_mock:
            result = await test_venue(
                _request_for("clerk-123"),
                VenueTestRequest(userId="clerk-123", venue="binance", isPaper=True),
            )

    assert result["ok"] is True
    runtime_config = build_mock.call_args.args[0]
    assert runtime_config.market == "futures"
    assert runtime_config.registry_name == "binance:futures"


@pytest.mark.asyncio
async def test_binance_connection_test_honors_explicit_futures_suffix(mock_env):
    from src.server import VenueTestRequest, test_venue
    from tests.conftest import MockVenue

    venue_row = {
        "type": "BINANCE",
        "apiKey": "BINANCEKEY1234567890ABCDE",
        "apiSecret": "BINANCESECRET1234567890ABCDE",
        "apiPassphrase": "",
        "accountId": "",
        "network": "",
        "market": "spot",
        "metaApiToken": "",
        "metaApiAccountId": "",
        "ccxtExchangeId": "",
    }

    with patch(_SUPABASE_READER, new=AsyncMock(return_value=[venue_row])):
        with patch("src.server.build_venue_from_runtime", return_value=MockVenue(starting_balance=654.0)) as build_mock:
            result = await test_venue(
                _request_for("clerk-123"),
                VenueTestRequest(userId="clerk-123", venue="binance:futures", isPaper=True),
            )

    assert result["ok"] is True
    runtime_config = build_mock.call_args.args[0]
    assert runtime_config.venue_name == "binance"
    assert runtime_config.market == "futures"
    assert runtime_config.registry_name == "binance:futures"


@pytest.mark.asyncio
async def test_preflight_rejects_oanda_missing_account_id(mock_env):
    from src.server import VenueTestRequest, test_venue
    with patch(_SUPABASE_READER, new=AsyncMock(return_value=[{
        "type": "OANDA", "apiKey": "valid-token", "apiSecret": "",
        "apiPassphrase": "", "accountId": "",  # MISSING
        "network": "", "metaApiToken": "", "metaApiAccountId": "", "ccxtExchangeId": "",
    }])):
        req = VenueTestRequest(userId="clerk-123", venue="oanda", isPaper=True)
        result = await test_venue(_request_for("clerk-123"), req)
    assert result["ok"] is False
    assert "Account ID" in result["error"]


@pytest.mark.asyncio
async def test_preflight_rejects_polymarket_bad_key_format(mock_env):
    from src.server import VenueTestRequest, test_venue
    with patch(_SUPABASE_READER, new=AsyncMock(return_value=[{
        "type": "POLYMARKET", "apiKey": "not-an-eth-key",
        "apiSecret": "", "apiPassphrase": "", "accountId": "",
        "network": "137", "metaApiToken": "", "metaApiAccountId": "", "ccxtExchangeId": "",
    }])):
        req = VenueTestRequest(userId="clerk-123", venue="polymarket", isPaper=True)
        result = await test_venue(_request_for("clerk-123"), req)
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_venue_not_found_returns_error(mock_env):
    from src.server import VenueTestRequest, test_venue
    with patch(_SUPABASE_READER, new=AsyncMock(return_value=[])):
        req = VenueTestRequest(userId="clerk-123", venue="binance", isPaper=True)
        result = await test_venue(_request_for("clerk-123"), req)
    assert result["ok"] is False
    assert "configured" in result["error"]
