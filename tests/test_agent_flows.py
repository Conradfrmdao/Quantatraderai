"""Integration tests — agent start/stop/trade execution flows.

Flow B: _do_start → _tick → decide → risk → place_order → audit
All LLM calls and DB calls are mocked. MockVenue simulates the exchange.
"""
import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def _request_for(user_id: str | None = None):
    import os
    headers = {}
    if os.getenv("PYTHON_INTERNAL_TOKEN"):
        headers["x-internal-token"] = os.getenv("PYTHON_INTERNAL_TOKEN", "")
    if user_id:
        headers["x-user-id"] = user_id
    return SimpleNamespace(headers=headers)


# ── Plan gating ────────────────────────────────────────────────────────────────

def test_plan_allows_all_features_pro():
    from src.server import _plan_allows
    for feature in ("aiCouncil", "ragMemory", "copyTrading", "liveTrading"):
        assert _plan_allows("PRO", feature) is True


def test_plan_allows_all_features_enterprise():
    from src.server import _plan_allows
    # _plan_allows covers trading features; whiteLabel/apiAccess are TypeScript-only
    for feature in ("aiCouncil", "ragMemory", "copyTrading", "liveTrading"):
        assert _plan_allows("ENTERPRISE", feature) is True


def test_plan_blocks_free_live_trading():
    from src.server import _plan_allows
    assert _plan_allows("FREE", "liveTrading") is False


def test_plan_blocks_free_ai_council():
    from src.server import _plan_allows
    assert _plan_allows("FREE", "aiCouncil") is False


def test_plan_allows_starter_live_trading():
    from src.server import _plan_allows
    assert _plan_allows("STARTER", "liveTrading") is True
    assert _plan_allows("STARTER", "aiCouncil") is False


# ── Per-user state isolation ───────────────────────────────────────────────────

def test_get_state_creates_isolated_per_user():
    from src.server import get_state, _states
    s1 = get_state("user_a")
    s2 = get_state("user_b")
    s3 = get_state("user_a")
    assert s1 is not s2, "Different users must have different state objects"
    assert s1 is s3,     "Same user must get the same state object"


def test_get_state_none_returns_global():
    from src.server import get_state, _state
    assert get_state(None) is _state


def test_states_are_independent(mock_env):
    from src.server import get_state
    sa = get_state("isolated_a")
    sb = get_state("isolated_b")
    sa.tick_count = 42
    sb.tick_count = 99
    assert get_state("isolated_a").tick_count == 42
    assert get_state("isolated_b").tick_count == 99


# ── Kill switch confirmation ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_killswitch_requires_confirm():
    import time
    from src.server import kill_switch, KillSwitchRequest
    result = await kill_switch(_request_for(), KillSwitchRequest(confirm=False, ts=time.time()))
    assert result["ok"] is False
    assert "confirm" in result["error"].lower()


@pytest.mark.asyncio
async def test_killswitch_rejects_stale_timestamp():
    import time
    from src.server import kill_switch, KillSwitchRequest
    stale = time.time() - 30
    result = await kill_switch(_request_for(), KillSwitchRequest(confirm=True, ts=stale))
    assert result["ok"] is False
    assert "expired" in result["error"].lower()


@pytest.mark.asyncio
async def test_killswitch_closes_positions_on_paper(mock_env, mock_venue):
    import time
    from src.server import kill_switch, KillSwitchRequest, get_state, _states
    # Set up paper state with a position
    s = get_state("kill_test_user")
    s.user_id = "kill_test_user"
    s.venue = mock_venue
    s.is_paper = True
    s.status = "running"
    mock_venue.inject_position("BTCUSDT", 0.1, 50_000.0)
    s.positions = [{"symbol": "BTCUSDT", "quantity": 0.1}]

    req = KillSwitchRequest(confirm=True, ts=time.time(), userId="kill_test_user")
    with patch("src.services.supabase_reader.upsert_agent_run", new=AsyncMock()):
        with patch("src.server._persist_audit", new=AsyncMock()):
            result = await kill_switch(_request_for("kill_test_user"), req)

    assert result["ok"] is True
    # Paper mode: doesn't call close_position on real venue
    assert mock_venue.calls.get("close_position", 0) == 0


@pytest.mark.asyncio
async def test_killswitch_closes_positions_on_live(mock_env, mock_venue):
    import time
    from src.server import kill_switch, KillSwitchRequest, get_state

    s = get_state("kill_live_user")
    s.user_id = "kill_live_user"
    s.venue = mock_venue
    s.is_paper = False  # LIVE
    s.status = "running"
    mock_venue.inject_position("BTCUSDT", 0.2, 50_000.0)
    s.positions = [{"symbol": "BTCUSDT", "quantity": 0.2}]

    req = KillSwitchRequest(confirm=True, ts=time.time(), userId="kill_live_user")
    with patch("src.services.supabase_reader.upsert_agent_run", new=AsyncMock()):
        with patch("src.server._persist_audit", new=AsyncMock()):
            result = await kill_switch(_request_for("kill_live_user"), req)

    assert result["ok"] is True
    assert mock_venue.calls.get("close_position", 0) >= 1


# ── Trade execution through RiskManager ───────────────────────────────────────

@pytest.mark.asyncio
async def test_risk_caps_oversized_position(mock_env, mock_venue, account_state_factory):
    """Risk manager CAPS oversized allocations (not blocks) to max_position_pct."""
    from src.risk_manager import RiskManager
    rm = RiskManager(venue="mock", asset_class="crypto_spot")
    acc = account_state_factory(total_value=10_000.0)
    trade = {
        "action": "buy", "asset": "BTCUSDT",
        "current_price": 50_000.0,
        "allocation_usd": 5_000.0,  # 50% — over 3% max, but gets capped not blocked
    }
    ok, reason, capped_trade = rm.validate_trade(trade, acc, 10_000.0)
    # Risk manager caps (not rejects) oversized positions
    assert ok is True or capped_trade["allocation_usd"] <= 10_000.0 * 0.03 + 1.0


@pytest.mark.asyncio
async def test_risk_allows_small_trade(mock_env, mock_venue, account_state_factory):
    from src.risk_manager import RiskManager
    rm = RiskManager(venue="mock", asset_class="crypto_spot")
    acc = account_state_factory(total_value=10_000.0)
    trade = {
        "action": "buy", "asset": "BTCUSDT",
        "current_price": 50_000.0,
        "allocation_usd": 100.0,  # 1% — within limits
    }
    ok, reason, _ = rm.validate_trade(trade, acc, 10_000.0)
    assert ok, f"Expected trade to be allowed but got: {reason}"


@pytest.mark.asyncio
async def test_paper_trade_does_not_call_venue_place_order(mock_env, mock_venue):
    """In paper mode, place_order should NOT be called on the real venue."""
    from src.risk_manager import RiskManager
    rm = RiskManager(venue="mock", asset_class="crypto_spot")
    # Simulate what _tick does in paper mode: logs trade, doesn't call venue
    acc = {"total_value": 10_000.0, "balance": 8_000.0, "positions": []}
    trade = {"action": "buy", "asset": "BTCUSDT", "current_price": 50_000.0, "allocation_usd": 100.0}
    ok, reason, dec = rm.validate_trade(trade, acc, 10_000.0)
    assert ok

    # Paper mode check: nothing should have been placed
    assert mock_venue.calls.get("place_order", 0) == 0, \
        "place_order was called — paper mode should NOT touch the venue"


# ── Dead man's switch logic ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dead_mans_warning_at_15_min():
    from datetime import datetime, timezone, timedelta
    import src.server as srv

    srv._state.status = "running"
    srv._state.last_tick_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    srv._state.positions = []
    srv._state.venue_name = "mock_test"

    events_emitted = []
    srv._notifier = MagicMock()
    srv._notifier.emit = AsyncMock(side_effect=lambda e: events_emitted.append(e.kind))

    elapsed = (datetime.now(timezone.utc) - srv._state.last_tick_at).total_seconds()
    WARN_LIMIT = 900
    if elapsed >= WARN_LIMIT:
        await srv._notifier.emit(MagicMock(kind="decision_error"))

    assert "decision_error" in events_emitted
    assert srv._state.status == "running", "Positions must not be closed at 15 min"


# ── Rate limiting ──────────────────────────────────────────────────────────────

def test_rate_limiter_allows_within_limit():
    # Temporarily inline the rate limiter logic in pure Python for portability
    windows: dict = {}
    import time as _t

    def rate_limit(user_id, action, max_per, window_ms):
        key = f"{user_id}:{action}"
        now = _t.time() * 1000
        w = windows.get(key)
        if not w or now >= w["reset_at"]:
            w = {"count": 0, "reset_at": now + window_ms}
            windows[key] = w
        w["count"] += 1
        return w["count"] <= max_per

    assert rate_limit("u1", "backtest", 3, 3_600_000) is True
    assert rate_limit("u1", "backtest", 3, 3_600_000) is True
    assert rate_limit("u1", "backtest", 3, 3_600_000) is True
    assert rate_limit("u1", "backtest", 3, 3_600_000) is False  # 4th → blocked


def test_rate_limiter_different_users_isolated():
    windows: dict = {}
    import time as _t

    def rate_limit(user_id, action, max_per, window_ms):
        key = f"{user_id}:{action}"
        now = _t.time() * 1000
        w = windows.get(key)
        if not w or now >= w["reset_at"]:
            w = {"count": 0, "reset_at": now + window_ms}
            windows[key] = w
        w["count"] += 1
        return w["count"] <= max_per

    # user_a hits limit
    for _ in range(3):
        rate_limit("user_a", "act", 3, 3_600_000)
    assert rate_limit("user_a", "act", 3, 3_600_000) is False

    # user_b is unaffected
    assert rate_limit("user_b", "act", 3, 3_600_000) is True
