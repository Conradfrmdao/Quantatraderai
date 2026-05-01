"""Concurrency tests (test_concurrency_*) — multi-user parallel state isolation.

Requirements:
  - 10–50 concurrent users
  - Every user has isolated AgentState
  - No equity/position/venue leakage between users
  - get_state(user_id) is safe under asyncio concurrency
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from tests.conftest import MockVenue


NUM_USERS = 20   # fast enough for CI, meaningful for isolation


async def _simulate_user_trading(user_index: int) -> dict[str, Any]:
    """One user's complete mini-session: start state, trade, assert balance."""
    from src.server import get_state
    from src.risk_manager import RiskManager

    uid    = f"concurrent_user_{user_index:04d}_{uuid.uuid4().hex[:6]}"
    budget = 10_000.0 + user_index * 100.0  # each user gets unique balance

    venue = MockVenue(starting_balance=budget)
    venue.set_price(50_000.0 + user_index)  # slightly different price per user

    s = get_state(uid)
    s.user_id        = uid
    s.venue          = venue
    s.is_paper       = True
    s.status         = "running"
    s.account        = {"equity": budget, "balance": budget}
    s.initial_equity = budget
    s.positions      = []
    s.risk_mgr       = RiskManager(venue="mock", asset_class="crypto_spot")

    # Simulate 3 rapid trades
    for i in range(3):
        alloc = budget * 0.01   # 1% each
        price = 50_000.0 + user_index + i
        qty   = alloc / price
        await venue.place_order("BTCUSDT", "buy", qty, "market", price=price)
        await asyncio.sleep(0)  # yield — allow other users to run

    positions  = await venue.get_positions()
    balances   = await venue.get_balances()
    final_bal  = balances[0].total

    return {
        "user_id":     uid,
        "user_index":  user_index,
        "initial_bal": budget,
        "final_bal":   final_bal,
        "positions":   len(positions),
        "venue_calls": venue.calls,
    }


@pytest.mark.asyncio
async def test_concurrency_isolated_state_per_user():
    """Each user's AgentState is isolated — writing to one never affects another."""
    from src.server import get_state

    users = [f"isolation_u{i}" for i in range(10)]
    states = {uid: get_state(uid) for uid in users}

    # Write unique equity to each state
    for i, uid in enumerate(users):
        states[uid].account = {"equity": 10_000.0 + i * 1000.0}

    # Verify no bleed
    for i, uid in enumerate(users):
        expected = 10_000.0 + i * 1000.0
        assert states[uid].account["equity"] == expected, \
            f"State bleed: user {uid} has wrong equity"


@pytest.mark.asyncio
async def test_concurrency_parallel_trading_no_cross_contamination(mock_env):
    """50 users trade simultaneously — verify each user's balance is correct."""
    tasks = [_simulate_user_trading(i) for i in range(NUM_USERS)]
    results = await asyncio.gather(*tasks)

    assert len(results) == NUM_USERS

    for r in results:
        # Every user should have made trades (place_order was called)
        assert r["venue_calls"].get("place_order", 0) == 3, \
            f"User {r['user_index']} expected 3 trades, got {r['venue_calls']}"

        # Balance must have decreased (trades consumed funds)
        assert r["final_bal"] < r["initial_bal"], \
            f"User {r['user_index']} balance didn't decrease after trades"

        # Balance must be specific to this user (not cross-contaminated)
        # Initial balance is 10_000 + user_index * 100, so uniqueness is proven
        # if no two users end with the same exact balance
        pass  # cross-check done below

    # No two users should share the same final balance (proves isolation)
    final_bals = [r["final_bal"] for r in results]
    assert len(set(round(b, 2) for b in final_bals)) == NUM_USERS, \
        "Duplicate final balances detected — possible state bleed between users"


@pytest.mark.asyncio
async def test_concurrency_positions_not_shared_between_users(mock_env):
    """Position lists must be completely separate per user."""
    from src.server import get_state

    uid_a = f"pos_isolation_a_{uuid.uuid4().hex[:6]}"
    uid_b = f"pos_isolation_b_{uuid.uuid4().hex[:6]}"

    venue_a = MockVenue(10_000.0)
    venue_b = MockVenue(10_000.0)

    sa = get_state(uid_a)
    sa.user_id  = uid_a
    sa.venue    = venue_a
    sa.positions = []

    sb = get_state(uid_b)
    sb.user_id  = uid_b
    sb.venue    = venue_b
    sb.positions = []

    # User A buys BTC
    await venue_a.place_order("BTCUSDT", "buy", 0.01)
    sa.positions = [p.__dict__ for p in await venue_a.get_positions()]

    # User B's positions must be unaffected
    sb_positions = await venue_b.get_positions()
    assert len(sb_positions) == 0, \
        "User B sees User A's positions — critical state bleed!"


@pytest.mark.asyncio
async def test_concurrency_get_state_is_reentrant(mock_env):
    """Calling get_state(uid) from multiple coroutines simultaneously is safe."""
    from src.server import get_state

    uid = f"reentrant_{uuid.uuid4().hex}"

    async def read_state(_):
        s = get_state(uid)
        await asyncio.sleep(0)
        return id(s)

    results = await asyncio.gather(*[read_state(i) for i in range(50)])

    # All coroutines must get the SAME object (same id)
    assert len(set(results)) == 1, \
        f"get_state returned different objects in concurrent calls: {len(set(results))} unique IDs"


@pytest.mark.asyncio
async def test_concurrency_kill_switch_only_affects_correct_user(mock_env):
    """Kill switch for user A must not affect user B's running state."""
    import time
    from src.server import kill_switch, KillSwitchRequest, get_state
    from unittest.mock import AsyncMock, patch

    uid_a = f"ks_a_{uuid.uuid4().hex[:6]}"
    uid_b = f"ks_b_{uuid.uuid4().hex[:6]}"

    venue_a = MockVenue(10_000.0)
    venue_b = MockVenue(10_000.0)
    venue_a.inject_position("BTCUSDT", 0.1, 50_000.0)

    sa = get_state(uid_a)
    sa.user_id  = uid_a
    sa.venue    = venue_a
    sa.is_paper = False
    sa.status   = "running"
    sa.positions = [{"symbol": "BTCUSDT", "quantity": 0.1}]

    sb = get_state(uid_b)
    sb.user_id  = uid_b
    sb.venue    = venue_b
    sb.is_paper = False
    sb.status   = "running"
    sb.positions = [{"symbol": "ETHUSDT", "quantity": 1.0}]
    venue_b.inject_position("ETHUSDT", 1.0, 3_000.0)

    # Kill switch ONLY for user A
    with patch("src.services.supabase_reader.upsert_agent_run", new=AsyncMock()):
        with patch("src.server._persist_audit", new=AsyncMock()):
            result = await kill_switch(KillSwitchRequest(
                confirm=True, ts=time.time(), userId=uid_a))

    assert result["ok"] is True

    # User A: venue.close_position called
    assert venue_a.calls.get("close_position", 0) >= 1

    # User B: completely untouched
    assert venue_b.calls.get("close_position", 0) == 0, \
        "User B's positions were affected by User A's kill switch!"
    assert sb.status == "running", "User B's agent was stopped by User A's kill switch!"


@pytest.mark.asyncio
async def test_concurrency_50_users_no_crash(mock_env):
    """Stress test: 50 users each do 5 operations concurrently. No crash."""
    from src.server import get_state

    async def user_session(i: int) -> str:
        uid = f"stress_{i:04d}"
        s = get_state(uid)
        s.user_id = uid
        venue = MockVenue(10_000.0)
        s.venue = venue

        # 5 lightweight ops
        for _ in range(5):
            await venue.get_balances()
            await asyncio.sleep(0)

        return uid

    results = await asyncio.gather(*[user_session(i) for i in range(50)])
    assert len(results) == 50
    assert len(set(results)) == 50  # all unique


@pytest.mark.asyncio
async def test_concurrency_equity_history_isolated_per_user(mock_env):
    """equityHistory built in dashboard must be separate per session."""
    from src.server import get_state

    histories: dict[str, list] = {}

    async def build_history(uid: str, n_points: int):
        s = get_state(uid)
        for i in range(n_points):
            s.account = {"equity": 10_000.0 + i * uid_seed(uid)}
            await asyncio.sleep(0)
        histories[uid] = [s.account["equity"]]

    def uid_seed(uid: str) -> float:
        return float(sum(ord(c) for c in uid) % 100)

    uids = [f"hist_user_{i}" for i in range(10)]
    await asyncio.gather(*[build_history(uid, 5) for uid in uids])

    # Each user's last equity is based on their own seed — no bleed
    for uid in uids:
        seed = uid_seed(uid)
        expected = 10_000.0 + 4 * seed  # n_points - 1 = 4
        assert abs(histories[uid][-1] - expected) < 0.1
