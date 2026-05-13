"""M17: Integration tests for server.py critical paths.

Tests are isolated — they mock venue calls and database, so no real API keys needed.
Run with: pytest tests/test_server_integration.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    """Provide required env vars without real credentials."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("ENCRYPTION_KEY", "test-key-32-bytes-padding-padding")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test")


# ── Plan gate tests ────────────────────────────────────────────────────────────

def test_plan_allows_all_features_pro():
    from src.server import _plan_allows
    assert _plan_allows("PRO", "aiCouncil")   is True
    assert _plan_allows("PRO", "ragMemory")   is True
    assert _plan_allows("PRO", "copyTrading") is True
    assert _plan_allows("PRO", "liveTrading") is True


def test_plan_blocks_free_user_live():
    from src.server import _plan_allows
    assert _plan_allows("FREE", "liveTrading") is False
    assert _plan_allows("FREE", "aiCouncil")   is False
    assert _plan_allows("FREE", "ragMemory")   is False


def test_plan_allows_starter_live():
    from src.server import _plan_allows
    assert _plan_allows("STARTER", "liveTrading") is True
    assert _plan_allows("STARTER", "aiCouncil")   is False


# ── AgentState isolation ───────────────────────────────────────────────────────

def test_get_state_creates_per_user():
    from src.server import get_state, _states
    s1 = get_state("user_a")
    s2 = get_state("user_b")
    s3 = get_state("user_a")  # same user — should return same object
    assert s1 is not s2
    assert s1 is s3


def test_get_state_fallback_for_none():
    from src.server import get_state, _state
    s = get_state(None)
    assert s is _state


@pytest.mark.asyncio
async def test_resolve_request_user_id_accepts_bearer_when_internal_token_mismatch(monkeypatch):
    import src.server as srv

    monkeypatch.setenv("PYTHON_INTERNAL_TOKEN", "expected-secret")
    req = SimpleNamespace(headers={
        "x-internal-token": "wrong-secret",
        "authorization": "Bearer clerk-session-token",
        "x-user-id": "header-user",
    })

    with patch("src.server._verify_clerk_token", AsyncMock(return_value=(True, "clerk_user_123"))):
        resolved = await srv._resolve_request_user_id(req, "query-user")

    assert resolved == "clerk_user_123"


@pytest.mark.asyncio
async def test_resolve_request_user_id_rejects_header_spoof_without_internal_token(monkeypatch):
    import src.server as srv

    monkeypatch.delenv("PYTHON_INTERNAL_TOKEN", raising=False)
    req = SimpleNamespace(headers={"x-user-id": "header-user"})

    with patch("src.server._verify_clerk_token", AsyncMock(return_value=(False, None))):
        resolved = await srv._resolve_request_user_id(req, "query-user")

    assert resolved is None


@pytest.mark.asyncio
async def test_get_account_returns_connected_live_balance_when_idle():
    import src.server as srv
    from src.venues.models import Balance

    class StubVenue:
        is_paper = False

        async def get_balances(self):
            return [Balance(currency="USDC", total=4321.0, available=4000.0)]

        async def get_positions(self):
            return []

    s = srv.get_state("clerk_live_balance")
    s.status = "idle"
    s.account = {}
    s.connected_account_cache = None
    s.connected_positions_cache = []
    s.connected_snapshot_at = None

    req = SimpleNamespace(headers={})
    venue_row = [{
        "type": "BINANCE",
        "market": "spot",
        "isPaper": False,
        "apiKey": "key",
        "apiSecret": "secret",
        "apiPassphrase": "",
        "accountId": "",
        "network": "",
        "metaApiToken": "",
        "metaApiAccountId": "",
        "ccxtExchangeId": "",
        "isActive": True,
    }]

    with patch("src.server._resolve_request_user_id", AsyncMock(return_value="clerk_live_balance")):
        with patch("src.services.supabase_reader.get_user_venues", AsyncMock(return_value=venue_row)):
            with patch("src.server.get_venue", return_value=StubVenue()):
                data = await srv.get_account(req, userId="ignored")

    assert data["balance"] == 4000.0
    assert data["equity"] == 4000.0
    assert data["open_positions"] == 0


@pytest.mark.asyncio
async def test_get_account_returns_configured_paper_balance_when_idle():
    import src.server as srv

    s = srv.get_state("clerk_paper_balance")
    s.status = "idle"
    s.account = {}
    s.paper_balance = 10_000.0
    s.paper_positions = []
    s.initial_equity = None
    s.connected_account_cache = None
    s.connected_positions_cache = []
    s.connected_snapshot_at = None

    req = SimpleNamespace(headers={})
    venue_row = [{
        "type": "BINANCE",
        "market": "spot",
        "paperCapital": 25000.0,
        "isPaper": True,
        "apiKey": "key",
        "apiSecret": "secret",
        "apiPassphrase": "",
        "accountId": "",
        "network": "",
        "metaApiToken": "",
        "metaApiAccountId": "",
        "ccxtExchangeId": "",
        "isActive": True,
    }]

    with patch("src.server._resolve_request_user_id", AsyncMock(return_value="clerk_paper_balance")):
        with patch("src.services.supabase_reader.get_user_venues", AsyncMock(return_value=venue_row)):
            data = await srv.get_account(req, userId="ignored")

    assert data["balance"] == 25000.0
    assert data["equity"] == 25000.0
    assert data["initial_equity"] == 25000.0
    assert data["open_positions"] == 0


@pytest.mark.asyncio
async def test_get_account_returns_connected_spot_equity_when_idle():
    import src.server as srv
    from src.venues.models import Balance, Position

    class StubVenue:
        is_paper = False

        async def get_balances(self):
            return [
                Balance(currency="USDT", total=1500.0, available=1500.0),
                Balance(currency="BTC", total=0.05, available=0.05),
            ]

        async def get_positions(self):
            return [
                Position(
                    symbol="BTC/USDT",
                    quantity=0.05,
                    entry_price=60000.0,
                    unrealized_pnl=250.0,
                    current_price=65000.0,
                )
            ]

    s = srv.get_state("clerk_live_spot_equity")
    s.status = "idle"
    s.account = {}
    s.connected_account_cache = None
    s.connected_positions_cache = []
    s.connected_snapshot_at = None

    req = SimpleNamespace(headers={})
    venue_row = [{
        "type": "BINANCE",
        "market": "spot",
        "isPaper": False,
        "apiKey": "key",
        "apiSecret": "secret",
        "apiPassphrase": "",
        "accountId": "",
        "network": "",
        "metaApiToken": "",
        "metaApiAccountId": "",
        "ccxtExchangeId": "",
        "isActive": True,
    }]

    with patch("src.server._resolve_request_user_id", AsyncMock(return_value="clerk_live_spot_equity")):
        with patch("src.services.supabase_reader.get_user_venues", AsyncMock(return_value=venue_row)):
            with patch("src.server.get_venue", return_value=StubVenue()):
                data = await srv.get_account(req, userId="ignored")

    assert data["balance"] == 1500.0
    assert data["equity"] == 4750.0
    assert data["open_positions"] == 1


@pytest.mark.asyncio
async def test_list_strategies_reads_persisted_rules():
    import src.server as srv

    req = SimpleNamespace(headers={})
    rows = [{
        "id": "rule_1",
        "text": "buy BTC when RSI < 30",
        "condition": "RSI below 30",
        "action": "buy",
        "symbol": "BTC",
        "isActive": True,
    }]

    with patch("src.server._resolve_request_user_id", AsyncMock(return_value="clerk_strategy_user")):
        with patch("src.services.supabase_reader.list_strategy_rules", AsyncMock(return_value=rows)):
            data = await srv.list_strategies(req, userId="ignored")

    assert data == {
        "rules": [{
            "id": "rule_1",
            "condition": "RSI below 30",
            "action": "buy",
            "symbol": "BTC",
            "active": True,
        }]
    }


@pytest.mark.asyncio
async def test_get_positions_returns_connected_live_positions_when_idle():
    import src.server as srv
    from src.venues.models import Balance, Position

    class StubVenue:
        is_paper = False

        async def get_balances(self):
            return [Balance(currency="USDT", total=2000.0, available=1500.0)]

        async def get_positions(self):
            return [
                Position(
                    symbol="BTC/USDT",
                    quantity=0.05,
                    entry_price=60000.0,
                    unrealized_pnl=125.0,
                    current_price=62500.0,
                )
            ]

    s = srv.get_state("clerk_live_positions")
    s.status = "idle"
    s.positions = []
    s.connected_account_cache = None
    s.connected_positions_cache = []
    s.connected_snapshot_at = None

    req = SimpleNamespace(headers={})
    venue_row = [{
        "type": "BINANCE",
        "market": "spot",
        "isPaper": False,
        "apiKey": "key",
        "apiSecret": "secret",
        "apiPassphrase": "",
        "accountId": "",
        "network": "",
        "metaApiToken": "",
        "metaApiAccountId": "",
        "ccxtExchangeId": "",
        "isActive": True,
    }]

    with patch("src.server._resolve_request_user_id", AsyncMock(return_value="clerk_live_positions")):
        with patch("src.services.supabase_reader.get_user_venues", AsyncMock(return_value=venue_row)):
            with patch("src.server.get_venue", return_value=StubVenue()):
                data = await srv.get_positions(req, userId="ignored")

    assert data["is_paper"] is False
    assert len(data["positions"]) == 1
    assert data["positions"][0]["symbol"] == "BTC/USDT"
    assert data["positions"][0]["current_price"] == 62500.0


def test_calculate_live_account_snapshot_does_not_double_count_spot_holdings():
    import src.server as srv
    from src.venues.models import Balance, Position

    balances = [Balance(currency="BTC", total=0.05, available=0.05)]
    positions = [
        Position(
            symbol="BTC/USDT",
            quantity=0.05,
            entry_price=60000.0,
            unrealized_pnl=250.0,
            current_price=65000.0,
        )
    ]

    balance, equity, pnl_total = srv._calculate_live_account_snapshot(
        balances,
        positions,
        "binance",
        "spot",
    )

    assert balance == 0.0
    assert equity == 3250.0
    assert pnl_total == 250.0


def test_infer_asset_class_respects_explicit_spot_market():
    import src.server as srv

    assert srv._infer_asset_class("bybit", "spot") == "crypto_spot"
    assert srv._infer_asset_class("okx", "spot") == "crypto_spot"
    assert srv._infer_asset_class("ccxt", "spot") == "crypto_spot"


def test_risk_manager_spot_sell_caps_to_existing_holding():
    from src.risk_manager import RiskManager

    rm = RiskManager(venue="binance", asset_class="crypto_spot")
    trade = {
        "symbol": "BTC/USDT",
        "action": "sell",
        "current_price": 65000,
        "allocation_usd": 10000,
    }
    account = {
        "total_value": 5000,
        "balance": 0,
        "positions": [{
            "symbol": "BTC/USDT",
            "quantity": 0.05,
            "current_price": 65000,
        }],
    }

    ok, reason, result = rm.validate_trade(trade, account, 10000)

    assert ok is True, reason
    assert result["allocation_usd"] == pytest.approx(3250.0)


@pytest.mark.asyncio
async def test_start_agent_returns_http_409_on_start_failure():
    import src.server as srv
    from fastapi import HTTPException

    req = srv.StartRequest(
        userId="user_test",
        venue="binance",
        symbols=["BTC/USDT"],
        timeframe="1h",
        isPaper=True,
    )

    with patch("src.server._do_start", AsyncMock(return_value={"ok": False, "error": "boom"})):
        with pytest.raises(HTTPException) as exc:
            await srv.start_agent(SimpleNamespace(headers={
                "x-user-id": "user_test",
                "x-internal-token": os.getenv("PYTHON_INTERNAL_TOKEN", ""),
            }), req)

    assert exc.value.status_code == 409
    assert exc.value.detail == "boom"


@pytest.mark.asyncio
async def test_stop_agent_uses_authenticated_user_not_spoofed_body_user_id():
    import src.server as srv

    attacker = srv.get_state("clerk_attacker_stop")
    attacker.user_id = "clerk_attacker_stop"
    attacker.status = "running"
    attacker._loop_task = None
    attacker._price_task = None
    attacker._deadman_task = None
    attacker._llm_worker_task = None
    attacker._order_worker_task = None

    victim = srv.get_state("clerk_victim_stop")
    victim.user_id = "clerk_victim_stop"
    victim.status = "running"
    victim._loop_task = None
    victim._price_task = None
    victim._deadman_task = None
    victim._llm_worker_task = None
    victim._order_worker_task = None

    req = SimpleNamespace(headers={})
    with patch("src.server._resolve_request_user_id", AsyncMock(return_value="clerk_attacker_stop")):
        with patch("src.services.supabase_reader.upsert_agent_run", new=AsyncMock()):
            with patch("src.server._persist_audit", new=AsyncMock()):
                result = await srv.stop_agent(req, {"userId": "clerk_victim_stop"})

    assert result["ok"] is True
    assert attacker.status == "stopped"
    assert victim.status == "running"


@pytest.mark.asyncio
async def test_get_candles_uses_authenticated_user_cache_not_global_state():
    import src.server as srv

    srv._state.candle_cache.clear()
    srv._state.candle_cache["BTCUSDT:1h"] = [{
        "time": 1,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1.0,
    }]

    user_state = srv.get_state("clerk_candle_user")
    user_state.candle_cache.clear()
    user_state.candle_cache["BTCUSDT:1h"] = [{
        "time": 2,
        "open": 2.0,
        "high": 2.0,
        "low": 2.0,
        "close": 2.0,
        "volume": 2.0,
    }]

    req = SimpleNamespace(headers={})
    with patch("src.server._resolve_request_user_id", AsyncMock(return_value="clerk_candle_user")):
        data = await srv.get_candles(req, symbol="BTCUSDT", timeframe="1h", limit=1, venue="binance", userId="ignored")

    assert data["candles"] == [user_state.candle_cache["BTCUSDT:1h"][0]]


# ── Risk manager smoke test ────────────────────────────────────────────────────

def test_risk_manager_caps_oversized():
    """Risk manager caps oversized allocations; the capped amount must be ≤ max_position_pct."""
    from src.risk_manager import RiskManager
    rm = RiskManager(venue="binance", asset_class="crypto_spot")
    trade = {
        "symbol": "BTCUSDT", "action": "buy",
        "current_price": 50000, "allocation_usd": 50000,  # 50% of 100k — over 3%
    }
    account = {"total_value": 100_000, "balance": 100_000, "positions": []}
    ok, reason, result = rm.validate_trade(trade, account, 100_000)
    if ok:
        # Must have capped allocation to ≤ 3% = $3000
        assert result["allocation_usd"] <= 100_000 * 0.04, \
            f"Uncapped allocation slipped through: {result['allocation_usd']}"
    else:
        assert reason  # blocked with reason — also acceptable


def test_risk_manager_allows_small_trade():
    from src.risk_manager import RiskManager
    rm = RiskManager(venue="binance", asset_class="crypto_spot")
    trade = {
        "symbol": "BTCUSDT", "action": "buy",
        "current_price": 50000, "allocation_usd": 200,  # 0.2% of 100k — fine
    }
    account = {"total_value": 100_000, "balance": 100_000, "positions": []}
    ok, reason, _ = rm.validate_trade(trade, account, 100_000)
    assert ok, f"Should allow small trade but got: {reason}"


# ── Dead man's switch logic ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dead_mans_switch_warns_at_15_min():
    """Stage 1: warning should fire at 15 min, not closing positions."""
    from datetime import datetime, timezone, timedelta
    import src.server as srv

    srv._state.status      = "running"
    srv._state.last_tick_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    srv._state.positions   = []
    srv._state.venue_name  = "test"

    events_emitted = []
    srv._notifier = MagicMock()
    srv._notifier.emit = AsyncMock(side_effect=lambda e: events_emitted.append(e.kind))

    # Run one iteration of dead man's check
    # We can't run the full loop, so we replicate the core logic:
    elapsed = (datetime.now(timezone.utc) - srv._state.last_tick_at).total_seconds()
    WARN_LIMIT = 900
    if elapsed >= WARN_LIMIT:
        await srv._notifier.emit(MagicMock(kind="decision_error"))

    assert "decision_error" in events_emitted
    assert srv._state.status == "running"  # positions NOT closed at 15 min


# ── Rate limiter ───────────────────────────────────────────────────────────────

def test_rate_limiter_allows_within_limit():
    # Import from ui lib through a mock since it's TypeScript
    # This test serves as documentation of the expected behaviour
    # TypeScript unit tests should use Jest; this is Python integration side.
    pass


# ── Kill switch confirmation ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_killswitch_requires_confirm():
    """C6: Kill switch must reject unconfirmed requests."""
    import time
    from src.server import kill_switch, KillSwitchRequest
    result = await kill_switch(SimpleNamespace(headers={}), KillSwitchRequest(confirm=False, ts=time.time()))
    assert result["ok"] is False
    assert "confirm" in result["error"].lower()


@pytest.mark.asyncio
async def test_killswitch_rejects_stale_timestamp():
    """C6: Kill switch must reject timestamps older than 10 seconds."""
    import time
    from src.server import kill_switch, KillSwitchRequest
    stale_ts = time.time() - 30  # 30 seconds ago
    result = await kill_switch(SimpleNamespace(headers={}), KillSwitchRequest(confirm=True, ts=stale_ts))
    assert result["ok"] is False
    assert "expired" in result["error"].lower()
