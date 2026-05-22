"""Central AI governance boundary for all model calls."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from src.agent.providers.base import LLMProvider, LLMResponse
from src.ai.budgets import (
    clamp_max_output_tokens,
    current_budget_periods,
    estimate_cost_usd,
    estimate_prompt_tokens,
    estimate_total_request_tokens,
    get_budget_policy,
)
from src.ai.errors import AIError, AIErrorCode
from src.ai.limiter import (
    consume_limit,
    counter_store_available,
    read_counter,
    reserve_counter,
    ttl_until_end_of_day,
    ttl_until_end_of_month,
)
from src.ai.redaction import redact_text
from src.ai.telemetry import ai_structured_log, capture_posthog, capture_sentry_exception
from src.services.persistence import write_ai_usage_log

AIAction = Literal[
    "agent_decision",
    "council_vote",
    "manual_command_parse",
    "trade_explanation",
    "backtest_commentary",
    "sanitize_output",
]

StreamHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


@dataclass
class AIRequestContext:
    user_id: str
    trace_id: str
    plan: str
    action: AIAction
    provider: str
    model: str
    mode: str
    venue: str
    symbol: str = ""
    persona: str = ""
    agent_run_id: str | None = None
    endpoint: str = ""
    stream: bool = False


@dataclass
class AIPermit:
    trace_id: str
    reservation_id: str
    estimated_tokens: int
    max_allowed_tokens: int


@dataclass
class UsageReservation:
    permit: AIPermit
    estimated_prompt_tokens: int
    requested_max_tokens: int


ACTION_LIMITS: dict[AIAction, dict[str, int]] = {
    "agent_decision": {"window_s": 60, "user": 12, "provider": 12, "endpoint": 12},
    "council_vote": {"window_s": 60, "user": 24, "provider": 24, "endpoint": 24},
    "manual_command_parse": {"window_s": 60, "user": 8, "provider": 8, "endpoint": 8},
    "trade_explanation": {"window_s": 3600, "user": 20, "provider": 20, "endpoint": 20},
    "backtest_commentary": {"window_s": 3600, "user": 6, "provider": 6, "endpoint": 6},
    "sanitize_output": {"window_s": 60, "user": 20, "provider": 20, "endpoint": 20},
}


def new_trace_id() -> str:
    return str(uuid.uuid4())


def _production_like() -> bool:
    return not __import__("os").getenv("APP_ENV", __import__("os").getenv("ENVIRONMENT", "development")).lower() in {"local", "development", "dev", "test"}


def _stream_event_base(ctx: AIRequestContext) -> dict[str, Any]:
    return {
        "trace_id": ctx.trace_id,
        "provider": ctx.provider,
        "model": ctx.model,
        "action": ctx.action,
        "mode": ctx.mode,
        "venue": ctx.venue,
        "symbol": ctx.symbol,
        "persona": ctx.persona or None,
    }


async def _emit_stream_event(handler: StreamHandler | None, payload: dict[str, Any]) -> None:
    if not handler:
        return
    result = handler(payload)
    if asyncio.iscoroutine(result):
        await result


def _chunk_text(text: str, chunk_size: int = 180) -> list[str]:
    value = redact_text(text)
    if not value:
        return []
    return [value[i:i + chunk_size] for i in range(0, len(value), chunk_size)]


async def _enforce_rate_limits(ctx: AIRequestContext) -> None:
    config = ACTION_LIMITS[ctx.action]
    checks = [
        ("user", f"{ctx.user_id}:{ctx.action}", config["user"]),
        ("provider", f"{ctx.user_id}:{ctx.provider}:{ctx.action}", config["provider"]),
        ("endpoint", f"{ctx.user_id}:{ctx.endpoint or ctx.action}:{ctx.action}", config["endpoint"]),
    ]
    for scope, identity, limit in checks:
        result = await consume_limit(f"ai:rl:{scope}", identity, limit, config["window_s"])
        if not result.allowed:
            await capture_posthog("ai_rate_limited", {
                "user_id": ctx.user_id,
                "plan": ctx.plan,
                "mode": ctx.mode,
                "venue": ctx.venue,
                "persona": ctx.persona,
                "provider": ctx.provider,
                "trace_id": ctx.trace_id,
                "success": False,
                "reason_code": "ai_rate_limited",
                "action": ctx.action,
            })
            ai_structured_log(
                "warning",
                "AI request rate limited",
                trace_id=ctx.trace_id,
                user_id=ctx.user_id,
                venue=ctx.venue,
                mode=ctx.mode,
                action=ctx.action,
                provider=ctx.provider,
                model=ctx.model,
                result="failure",
                reason_code="ai_rate_limited",
                retry_after_seconds=result.retry_after_seconds,
            )
            raise AIError(
                AIErrorCode.AI_RATE_LIMITED,
                trace_id=ctx.trace_id,
                retry_after_seconds=result.retry_after_seconds,
                metadata={"reason_code": "ai_rate_limited"},
            )


async def _reserve_budget(ctx: AIRequestContext, system: str, messages: list[dict[str, Any]], max_tokens: int, tools: list[dict[str, Any]] | None) -> UsageReservation:
    policy = get_budget_policy(ctx.plan)
    prompt_est = estimate_prompt_tokens(system, messages, tools=tools)
    total_est = estimate_total_request_tokens(system, messages, max_tokens, tools=tools)
    reservation_id = str(uuid.uuid4())
    day_id, month_id = current_budget_periods()
    ttl_day = ttl_until_end_of_day()
    ttl_month = ttl_until_end_of_month()

    current_day = await read_counter("ai:budget:day", f"{ctx.user_id}:{day_id}")
    if current_day + total_est > policy.daily_tokens:
        await capture_posthog("token_budget_exceeded", {
            "user_id": ctx.user_id,
            "plan": ctx.plan,
            "mode": ctx.mode,
            "venue": ctx.venue,
            "persona": ctx.persona,
            "provider": ctx.provider,
            "trace_id": ctx.trace_id,
            "success": False,
            "reason_code": "daily_budget_exceeded",
            "action": ctx.action,
        })
        raise AIError(AIErrorCode.AI_BUDGET_DAILY_EXCEEDED, trace_id=ctx.trace_id, metadata={"reason_code": "daily_budget_exceeded"})

    current_month = await read_counter("ai:budget:month", f"{ctx.user_id}:{month_id}")
    if current_month + total_est > policy.monthly_tokens:
        await capture_posthog("token_budget_exceeded", {
            "user_id": ctx.user_id,
            "plan": ctx.plan,
            "mode": ctx.mode,
            "venue": ctx.venue,
            "persona": ctx.persona,
            "provider": ctx.provider,
            "trace_id": ctx.trace_id,
            "success": False,
            "reason_code": "monthly_budget_exceeded",
            "action": ctx.action,
        })
        raise AIError(AIErrorCode.AI_BUDGET_MONTHLY_EXCEEDED, trace_id=ctx.trace_id, metadata={"reason_code": "monthly_budget_exceeded"})

    if ctx.agent_run_id:
        current_run = await read_counter("ai:budget:run", ctx.agent_run_id)
        if current_run + total_est > policy.per_agent_run_tokens:
            await capture_posthog("token_budget_exceeded", {
                "user_id": ctx.user_id,
                "plan": ctx.plan,
                "mode": ctx.mode,
                "venue": ctx.venue,
                "persona": ctx.persona,
                "provider": ctx.provider,
                "trace_id": ctx.trace_id,
                "success": False,
                "reason_code": "agent_run_budget_exceeded",
                "action": ctx.action,
            })
            raise AIError(AIErrorCode.AI_AGENT_RUN_BUDGET_EXCEEDED, trace_id=ctx.trace_id, metadata={"reason_code": "agent_run_budget_exceeded"})

    await reserve_counter("ai:budget:day", f"{ctx.user_id}:{day_id}", total_est, ttl_day)
    await reserve_counter("ai:budget:month", f"{ctx.user_id}:{month_id}", total_est, ttl_month)
    if ctx.agent_run_id:
        await reserve_counter("ai:budget:run", ctx.agent_run_id, total_est, ttl_month)

    return UsageReservation(
        permit=AIPermit(
            trace_id=ctx.trace_id,
            reservation_id=reservation_id,
            estimated_tokens=total_est,
            max_allowed_tokens=policy.per_request_max_output_tokens,
        ),
        estimated_prompt_tokens=prompt_est,
        requested_max_tokens=max_tokens,
    )


async def _reconcile_budget(ctx: AIRequestContext, reserved_tokens: int, actual_total_tokens: int) -> None:
    delta = int(actual_total_tokens) - int(reserved_tokens)
    if delta == 0:
        return
    day_id, month_id = current_budget_periods()
    ttl_day = ttl_until_end_of_day()
    ttl_month = ttl_until_end_of_month()
    await reserve_counter("ai:budget:day", f"{ctx.user_id}:{day_id}", delta, ttl_day)
    await reserve_counter("ai:budget:month", f"{ctx.user_id}:{month_id}", delta, ttl_month)
    if ctx.agent_run_id:
        await reserve_counter("ai:budget:run", ctx.agent_run_id, delta, ttl_month)


async def record_ai_success(
    *,
    ctx: AIRequestContext,
    usage: UsageReservation,
    response: LLMResponse,
    latency_ms: int,
) -> None:
    prompt_tokens = int(response.input_tokens or usage.estimated_prompt_tokens)
    completion_tokens = int(response.output_tokens or max(1, len(redact_text(response.content)) // 4))
    total_tokens = max(prompt_tokens + completion_tokens, 1)
    await _reconcile_budget(ctx, usage.permit.estimated_tokens, total_tokens)
    await write_ai_usage_log(
        ctx.user_id,
        agent_run_id=ctx.agent_run_id,
        provider=ctx.provider,
        model=ctx.model,
        action=ctx.action,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimate_cost_usd(ctx.provider, prompt_tokens, completion_tokens),
        trace_id=ctx.trace_id,
        mode=ctx.mode,
        venue=ctx.venue,
    )
    ai_structured_log(
        "info",
        "AI request completed",
        trace_id=ctx.trace_id,
        user_id=ctx.user_id,
        venue=ctx.venue,
        mode=ctx.mode,
        action=ctx.action,
        provider=ctx.provider,
        model=ctx.model,
        latency_ms=latency_ms,
        result="success",
        reason_code="ai_completed",
        total_tokens=total_tokens,
    )
    await capture_posthog("ai_decision_completed" if ctx.action == "agent_decision" else "ai_council_vote_completed" if ctx.action == "council_vote" else "ai_request_completed", {
        "user_id": ctx.user_id,
        "plan": ctx.plan,
        "mode": ctx.mode,
        "venue": ctx.venue,
        "persona": ctx.persona,
        "provider": ctx.provider,
        "trace_id": ctx.trace_id,
        "success": True,
        "reason_code": "ai_completed",
        "action": ctx.action,
    })


async def record_ai_failure(
    *,
    ctx: AIRequestContext,
    usage: UsageReservation | None,
    exc: Exception,
    latency_ms: int,
    reason_code: str,
) -> None:
    prompt_tokens = usage.estimated_prompt_tokens if usage else 0
    completion_tokens = 0
    total_tokens = prompt_tokens + completion_tokens
    if usage:
        await _reconcile_budget(ctx, usage.permit.estimated_tokens, total_tokens)
        await write_ai_usage_log(
            ctx.user_id,
            agent_run_id=ctx.agent_run_id,
            provider=ctx.provider,
            model=ctx.model,
            action=ctx.action,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimate_cost_usd(ctx.provider, prompt_tokens, completion_tokens),
            trace_id=ctx.trace_id,
            mode=ctx.mode,
            venue=ctx.venue,
        )
    capture_sentry_exception(exc if isinstance(exc, Exception) else Exception(str(exc)), context={
        "user_id": ctx.user_id,
        "trace_id": ctx.trace_id,
        "venue": ctx.venue,
        "provider": ctx.provider,
        "model": ctx.model,
        "action": ctx.action,
        "mode": ctx.mode,
        "plan": ctx.plan,
        "reason_code": reason_code,
    })
    ai_structured_log(
        "error",
        "AI request failed",
        trace_id=ctx.trace_id,
        user_id=ctx.user_id,
        venue=ctx.venue,
        mode=ctx.mode,
        action=ctx.action,
        provider=ctx.provider,
        model=ctx.model,
        latency_ms=latency_ms,
        result="failure",
        reason_code=reason_code,
    )


def _ensure_ai_request_allowed(ctx: AIRequestContext) -> None:
    if ctx.user_id:
        return
    if _production_like():
        raise AIError(AIErrorCode.AI_GOVERNANCE_UNAVAILABLE, trace_id=ctx.trace_id, metadata={"reason_code": "missing_user_id"})


async def governed_complete(
    *,
    provider: LLMProvider,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    context: AIRequestContext,
    tools: list[dict[str, Any]] | None = None,
    stream_handler: StreamHandler | None = None,
) -> LLMResponse:
    _ensure_ai_request_allowed(context)
    if _production_like() and not counter_store_available():
        raise AIError(AIErrorCode.AI_GOVERNANCE_UNAVAILABLE, trace_id=context.trace_id, metadata={"reason_code": "counter_store_unavailable"})

    context.provider = provider.name
    context.model = provider.model
    bounded_max_tokens = clamp_max_output_tokens(context.plan, max_tokens)
    governance_started_at = time.perf_counter()
    try:
        await _enforce_rate_limits(context)
        usage = await _reserve_budget(context, system, messages, bounded_max_tokens, tools)
    except AIError:
        raise
    except Exception as exc:
        latency_ms = int((time.perf_counter() - governance_started_at) * 1000)
        await record_ai_failure(
            ctx=context,
            usage=None,
            exc=exc,
            latency_ms=latency_ms,
            reason_code="ai_governance_unavailable",
        )
        raise AIError(
            AIErrorCode.AI_GOVERNANCE_UNAVAILABLE,
            trace_id=context.trace_id,
            metadata={"reason_code": "ai_governance_unavailable"},
            cause=exc,
        ) from exc
    started_at = time.perf_counter()

    await capture_posthog("ai_decision_started" if context.action == "agent_decision" else "ai_request_started", {
        "user_id": context.user_id,
        "plan": context.plan,
        "mode": context.mode,
        "venue": context.venue,
        "persona": context.persona,
        "provider": context.provider,
        "trace_id": context.trace_id,
        "success": True,
        "reason_code": "started",
        "action": context.action,
    })
    await _emit_stream_event(stream_handler, {
        "type": "ai_decision_started" if context.action == "agent_decision" else "ai_council_vote_started" if context.action == "council_vote" else "ai_stream_started",
        **_stream_event_base(context),
        "partial": "",
        "final": False,
    })

    try:
        async_complete = getattr(provider, "acomplete", None)
        if callable(async_complete):
            try:
                response = await async_complete(
                    system=system,
                    messages=messages,
                    max_tokens=bounded_max_tokens,
                    tools=tools,
                )
            except NotImplementedError:
                # Fallback for legacy providers that have not grown a native async
                # transport yet. The governed boundary still protects rate limits,
                # budgets, and persistence; only the transport remains sync.
                response = provider.complete(
                    system=system,
                    messages=messages,
                    max_tokens=bounded_max_tokens,
                    tools=tools,
                )
        else:
            response = provider.complete(
                system=system,
                messages=messages,
                max_tokens=bounded_max_tokens,
                tools=tools,
            )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        for chunk in _chunk_text(response.content):
            await _emit_stream_event(stream_handler, {
                "type": "ai_decision_delta" if context.action == "agent_decision" else "ai_council_vote_delta" if context.action == "council_vote" else "ai_stream_delta",
                **_stream_event_base(context),
                "partial": chunk,
                "final": False,
            })
        await record_ai_success(ctx=context, usage=usage, response=response, latency_ms=latency_ms)
        await _emit_stream_event(stream_handler, {
            "type": "ai_decision_completed" if context.action == "agent_decision" else "ai_council_vote_completed" if context.action == "council_vote" else "ai_stream_completed",
            **_stream_event_base(context),
            "partial": "",
            "final": True,
            "content": redact_text(response.content),
            "stop_reason": response.stop_reason,
        })
        return response
    except AIError:
        raise
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        await record_ai_failure(ctx=context, usage=usage, exc=exc, latency_ms=latency_ms, reason_code="ai_provider_failed")
        await _emit_stream_event(stream_handler, {
            "type": "ai_decision_failed" if context.action == "agent_decision" else "ai_stream_failed",
            **_stream_event_base(context),
            "partial": "",
            "final": True,
            "reason_code": "ai_provider_failed",
            "message": "The AI request failed safely. No trade was executed.",
        })
        raise AIError(AIErrorCode.AI_PROVIDER_FAILED, trace_id=context.trace_id, metadata={"reason_code": "ai_provider_failed"}, cause=exc) from exc


async def governed_stream(
    *,
    provider: LLMProvider,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    context: AIRequestContext,
    tools: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async def collect(payload: dict[str, Any]) -> None:
        events.append(payload)

    try:
        response = await governed_complete(
            provider=provider,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            context=context,
            tools=tools,
            stream_handler=collect,
        )
        events.append({
            "type": "ai_final_response",
            **_stream_event_base(context),
            "final": True,
            "content": redact_text(response.content),
        })
    except AIError as exc:
        events.append({
            "type": "ai_stream_failed",
            **_stream_event_base(context),
            "final": True,
            "error": exc.code.value,
            "message": exc.definition.user_message,
            "trace_id": exc.trace_id,
        })
    return events
