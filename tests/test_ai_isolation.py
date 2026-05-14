from __future__ import annotations

from types import SimpleNamespace

import pytest
from datetime import datetime, timezone


@pytest.fixture(autouse=True)
def reset_isolation_store(monkeypatch):
    import src.ai.limiter as limiter
    monkeypatch.setenv("APP_ENV", "test")
    limiter._STORE = limiter.InMemoryCounterStore()


def _request_for(user_id: str):
    return SimpleNamespace(headers={
        "x-internal-token": "test-internal-token",
        "x-user-id": user_id,
    })


@pytest.mark.asyncio
async def test_get_decisions_reads_only_requested_users_history(monkeypatch):
    import src.server as srv

    async def fake_list_ai_decisions(clerk_user_id: str, limit: int = 20):
        return [{"trace_id": f"trace-{clerk_user_id}", "ts": "2026-05-13T00:00:00+00:00", "trade_decisions": []}]

    monkeypatch.setattr("src.services.supabase_reader.list_ai_decisions", fake_list_ai_decisions)

    user_a = await srv.get_decisions(_request_for("user-a"), limit=5, userId="user-a")
    user_b = await srv.get_decisions(_request_for("user-b"), limit=5, userId="user-b")

    assert user_a["decisions"][0]["trace_id"] == "trace-user-a"
    assert user_b["decisions"][0]["trace_id"] == "trace-user-b"


@pytest.mark.asyncio
async def test_user_token_budget_does_not_affect_other_user():
    from src.ai.limiter import current_budget_periods, read_counter, reserve_counter, ttl_until_end_of_day

    day_id, _ = current_budget_periods()
    await reserve_counter("ai:budget:day", f"user-a:{day_id}", 20_000, ttl_until_end_of_day())
    await reserve_counter("ai:budget:day", f"user-b:{day_id}", 500, ttl_until_end_of_day())

    assert await read_counter("ai:budget:day", f"user-a:{day_id}") == 20_000
    assert await read_counter("ai:budget:day", f"user-b:{day_id}") == 500


@pytest.mark.asyncio
async def test_websocket_broadcast_only_reaches_correct_user_for_ai_events():
    import src.server as srv

    class FakeWs:
        def __init__(self):
            self.events = []

        async def send_json(self, event):
            self.events.append(event)

    user_ws = FakeWs()
    other_ws = FakeWs()
    srv._ws_clients.update({user_ws, other_ws})
    srv._ws_user_map[user_ws] = "iso-user"
    srv._ws_user_map[other_ws] = "other-user"

    try:
        await srv._broadcast({"type": "ai_decision_delta", "trace_id": "trace-1", "partial": "thinking"}, "iso-user")
    finally:
        srv._ws_clients.discard(user_ws)
        srv._ws_clients.discard(other_ws)
        srv._ws_user_map.pop(user_ws, None)
        srv._ws_user_map.pop(other_ws, None)

    assert user_ws.events == [{"type": "ai_decision_delta", "trace_id": "trace-1", "partial": "thinking"}]
    assert other_ws.events == []


@pytest.mark.asyncio
async def test_active_run_filters_out_old_persisted_decisions(monkeypatch):
    import src.server as srv

    async def fake_list_ai_decisions(clerk_user_id: str, limit: int = 20):
        return [
            {"trace_id": "old-trace", "ts": "2026-05-13T10:13:44+00:00", "trade_decisions": [{"asset": "BTC/USDT", "action": "hold", "rationale": "old"}]},
            {"trace_id": "new-trace", "ts": "2026-05-14T10:16:00+00:00", "trade_decisions": [{"asset": "BTC/USDT", "action": "buy", "rationale": "new"}]},
        ]

    monkeypatch.setattr("src.services.supabase_reader.list_ai_decisions", fake_list_ai_decisions)

    state = srv.AgentState()
    state.status = "running"
    state.start_time = datetime(2026, 5, 14, 10, 15, tzinfo=timezone.utc)

    filtered = await srv._load_session_scoped_decisions("user-a", state, 20)

    assert [entry["trace_id"] for entry in filtered] == ["new-trace"]
