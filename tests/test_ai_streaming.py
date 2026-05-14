from __future__ import annotations

import pytest

from tests.test_ai_governance import DummyProvider, _ctx


@pytest.fixture(autouse=True)
def reset_stream_store(monkeypatch):
    import src.ai.limiter as limiter
    monkeypatch.setenv("APP_ENV", "test")
    limiter._STORE = limiter.InMemoryCounterStore()


@pytest.mark.asyncio
async def test_governed_stream_emits_partial_updates_without_trade_side_effects(monkeypatch):
    from src.ai.governance import governed_stream

    async def fake_usage(*args, **kwargs):
        return None

    async def fake_posthog(*args, **kwargs):
        return None

    monkeypatch.setattr("src.ai.governance.write_ai_usage_log", fake_usage)
    monkeypatch.setattr("src.ai.governance.capture_posthog", fake_posthog)

    events = await governed_stream(
        provider=DummyProvider("Momentum improving across the market."),
        system="stream this",
        messages=[{"role": "user", "content": "Explain the setup"}],
        max_tokens=120,
        context=_ctx("stream-user", action="trade_explanation"),
    )

    event_types = [event["type"] for event in events]
    assert "ai_stream_started" in event_types
    assert "ai_stream_delta" in event_types
    assert "ai_stream_completed" in event_types
    assert "trade_executed" not in event_types
    assert any(event.get("partial") for event in events if event["type"] == "ai_stream_delta")


@pytest.mark.asyncio
async def test_governed_stream_failure_returns_safe_terminal_event(monkeypatch):
    from src.ai.governance import governed_stream

    async def fake_usage(*args, **kwargs):
        return None

    async def fake_posthog(*args, **kwargs):
        return None

    monkeypatch.setattr("src.ai.governance.write_ai_usage_log", fake_usage)
    monkeypatch.setattr("src.ai.governance.capture_posthog", fake_posthog)

    events = await governed_stream(
        provider=DummyProvider(fail=True),
        system="stream this",
        messages=[{"role": "user", "content": "Explain the setup"}],
        max_tokens=120,
        context=_ctx("stream-fail", action="trade_explanation"),
    )

    assert events[-1]["type"] == "ai_stream_failed"
    assert "No trade was executed" in events[-1]["message"]
