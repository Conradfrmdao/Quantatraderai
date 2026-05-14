from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class DummyResponse:
    content: str
    model: str = "dummy-model"
    input_tokens: int = 12
    output_tokens: int = 18
    stop_reason: str = "stop"
    raw: object = None


class DummyProvider:
    name = "groq"
    model = "dummy-model"

    def __init__(self, content: str = '{"trade_decisions":[]}', fail: bool = False):
        self.content = content
        self.fail = fail

    def complete(self, system, messages, max_tokens=4096, tools=None):
        if self.fail:
            raise RuntimeError("provider boom")
        return DummyResponse(content=self.content, model=self.model)


class AsyncOnlyDummyProvider(DummyProvider):
    def complete(self, system, messages, max_tokens=4096, tools=None):
        raise AssertionError("sync complete should not be called when async transport exists")

    async def acomplete(self, system, messages, max_tokens=4096, tools=None):
        return DummyResponse(content=self.content, model=self.model)


@pytest.fixture(autouse=True)
def reset_governance_state(monkeypatch):
    import src.ai.limiter as limiter
    monkeypatch.setenv("APP_ENV", "test")
    limiter._STORE = limiter.InMemoryCounterStore()


def _ctx(user_id: str, *, action: str = "agent_decision"):
    from src.ai.governance import AIRequestContext

    return AIRequestContext(
        user_id=user_id,
        trace_id=f"trace-{user_id}-{action}",
        plan="FREE",
        action=action,  # type: ignore[arg-type]
        provider="groq",
        model="dummy-model",
        mode="paper",
        venue="binance",
        symbol="BTC/USDT",
        endpoint=f"/api/{action}",
    )


@pytest.mark.asyncio
async def test_ai_rate_limit_hits_one_user_only(monkeypatch):
    from src.ai.errors import AIError, AIErrorCode
    from src.ai.governance import governed_complete

    usage_rows: list[dict] = []
    posthog_events: list[tuple[str, dict]] = []

    async def fake_usage(*args, **kwargs):
        usage_rows.append(kwargs)

    async def fake_posthog(event, props):
        posthog_events.append((event, props))

    monkeypatch.setattr("src.ai.governance.write_ai_usage_log", fake_usage)
    monkeypatch.setattr("src.ai.governance.capture_posthog", fake_posthog)

    provider = DummyProvider('{"trade_decisions":[{"asset":"BTC/USDT","action":"hold"}]}')
    for _ in range(12):
        await governed_complete(
            provider=provider,
            system="sys",
            messages=[{"role": "user", "content": "ctx"}],
            max_tokens=50,
            context=_ctx("user-a"),
        )

    with pytest.raises(AIError) as exc:
        await governed_complete(
            provider=provider,
            system="sys",
            messages=[{"role": "user", "content": "ctx"}],
            max_tokens=50,
            context=_ctx("user-a"),
        )

    assert exc.value.code == AIErrorCode.AI_RATE_LIMITED
    assert exc.value.retry_after_seconds and exc.value.retry_after_seconds > 0

    await governed_complete(
        provider=provider,
        system="sys",
        messages=[{"role": "user", "content": "ctx"}],
        max_tokens=50,
        context=_ctx("user-b"),
    )

    assert any(event == "ai_rate_limited" for event, _ in posthog_events)
    assert len(usage_rows) == 13


@pytest.mark.asyncio
async def test_ai_budget_caps_raise_clear_errors(monkeypatch):
    from src.ai.errors import AIError, AIErrorCode
    from src.ai.governance import governed_complete
    from src.ai.limiter import current_budget_periods, reserve_counter, ttl_until_end_of_day, ttl_until_end_of_month

    async def fake_usage(*args, **kwargs):
        return None

    async def fake_posthog(*args, **kwargs):
        return None

    monkeypatch.setattr("src.ai.governance.write_ai_usage_log", fake_usage)
    monkeypatch.setattr("src.ai.governance.capture_posthog", fake_posthog)

    day_id, month_id = current_budget_periods()
    await reserve_counter("ai:budget:day", f"user-cap:{day_id}", 24_950, ttl_until_end_of_day())
    await reserve_counter("ai:budget:month", f"user-cap:{month_id}", 399_950, ttl_until_end_of_month())

    provider = DummyProvider('{"trade_decisions":[]}')

    with pytest.raises(AIError) as day_exc:
        await governed_complete(
            provider=provider,
            system="sys",
            messages=[{"role": "user", "content": "x" * 500}],
            max_tokens=200,
            context=_ctx("user-cap"),
        )
    assert day_exc.value.code == AIErrorCode.AI_BUDGET_DAILY_EXCEEDED

    await reserve_counter("ai:budget:day", f"user-month:{day_id}", 100, ttl_until_end_of_day())
    await reserve_counter("ai:budget:month", f"user-month:{month_id}", 1_999_900, ttl_until_end_of_month())
    with pytest.raises(AIError) as month_exc:
        await governed_complete(
            provider=provider,
            system="sys",
            messages=[{"role": "user", "content": "x" * 500}],
            max_tokens=400,
            context=_ctx("user-month", action="manual_command_parse"),
        )
    assert month_exc.value.code == AIErrorCode.AI_BUDGET_MONTHLY_EXCEEDED


@pytest.mark.asyncio
async def test_ai_usage_log_records_actual_tokens(monkeypatch):
    from src.ai.governance import governed_complete

    usage_rows: list[dict] = []

    async def fake_usage(clerk_user_id, **kwargs):
        usage_rows.append({"clerk_user_id": clerk_user_id, **kwargs})

    async def fake_posthog(*args, **kwargs):
        return None

    monkeypatch.setattr("src.ai.governance.write_ai_usage_log", fake_usage)
    monkeypatch.setattr("src.ai.governance.capture_posthog", fake_posthog)

    provider = DummyProvider('{"trade_decisions":[{"asset":"BTC/USDT","action":"hold"}]}')
    await governed_complete(
        provider=provider,
        system="system prompt",
        messages=[{"role": "user", "content": "ctx"}],
        max_tokens=75,
        context=_ctx("user-log", action="council_vote"),
    )

    assert len(usage_rows) == 1
    row = usage_rows[0]
    assert row["clerk_user_id"] == "user-log"
    assert row["provider"] == "groq"
    assert row["action"] == "council_vote"
    assert row["prompt_tokens"] == 12
    assert row["completion_tokens"] == 18
    assert row["total_tokens"] == 30


@pytest.mark.asyncio
async def test_council_calls_count_separately_toward_budget(monkeypatch):
    from src.ai.governance import governed_complete
    from src.ai.limiter import current_budget_periods, read_counter

    async def fake_usage(*args, **kwargs):
        return None

    async def fake_posthog(*args, **kwargs):
        return None

    monkeypatch.setattr("src.ai.governance.write_ai_usage_log", fake_usage)
    monkeypatch.setattr("src.ai.governance.capture_posthog", fake_posthog)

    provider = DummyProvider('{"trade_decisions":[]}')
    for _ in range(3):
        await governed_complete(
            provider=provider,
            system="system prompt",
            messages=[{"role": "user", "content": "ctx"}],
            max_tokens=75,
            context=_ctx("council-user", action="council_vote"),
        )

    day_id, _ = current_budget_periods()
    reserved = await read_counter("ai:budget:day", f"council-user:{day_id}")
    assert reserved > 0


@pytest.mark.asyncio
async def test_governed_complete_prefers_async_provider(monkeypatch):
    from src.ai.governance import governed_complete

    async def fake_usage(*args, **kwargs):
        return None

    async def fake_posthog(*args, **kwargs):
        return None

    monkeypatch.setattr("src.ai.governance.write_ai_usage_log", fake_usage)
    monkeypatch.setattr("src.ai.governance.capture_posthog", fake_posthog)

    provider = AsyncOnlyDummyProvider('{"trade_decisions":[{"asset":"BTC/USDT","action":"hold"}]}')
    response = await governed_complete(
        provider=provider,
        system="sys",
        messages=[{"role": "user", "content": "ctx"}],
        max_tokens=50,
        context=_ctx("async-user"),
    )

    assert '"action":"hold"' in response.content


def test_counter_store_uses_postgres_fallback_when_database_url_present(monkeypatch):
    import src.ai.limiter as limiter

    limiter._STORE = None
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    monkeypatch.setenv("APP_ENV", "production")

    store = limiter.get_counter_store()

    assert isinstance(store, limiter.PostgresCounterStore)
