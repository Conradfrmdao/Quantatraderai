"""Per-plan AI token budgets and token estimation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.ai.redaction import redact_text


@dataclass(frozen=True)
class TokenBudgetPolicy:
    daily_tokens: int
    monthly_tokens: int
    per_request_max_output_tokens: int
    per_agent_run_tokens: int


PLAN_TOKEN_BUDGETS: dict[str, TokenBudgetPolicy] = {
    "FREE": TokenBudgetPolicy(25_000, 400_000, 800, 40_000),
    "STARTER": TokenBudgetPolicy(100_000, 2_000_000, 1_200, 120_000),
    "PRO": TokenBudgetPolicy(300_000, 8_000_000, 2_000, 400_000),
    "ENTERPRISE": TokenBudgetPolicy(1_000_000, 25_000_000, 4_000, 1_500_000),
}


PROVIDER_COSTS_PER_1K: dict[str, tuple[float, float]] = {
    "anthropic": (0.0008, 0.004),
    "groq": (0.0, 0.0),
    "gemini": (0.0, 0.0),
    "openrouter": (0.0006, 0.002),
    "ollama": (0.0, 0.0),
}


def get_budget_policy(plan: str | None) -> TokenBudgetPolicy:
    return PLAN_TOKEN_BUDGETS.get(str(plan or "FREE").upper(), PLAN_TOKEN_BUDGETS["FREE"])


def _estimate_tokens_from_text(text: str | None) -> int:
    value = redact_text(text or "")
    if not value:
        return 0
    return max(1, int(len(value) / 4))


def estimate_prompt_tokens(system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> int:
    total = _estimate_tokens_from_text(system)
    for message in messages:
        total += _estimate_tokens_from_text(str(message.get("role", "")))
        content = message.get("content")
        if isinstance(content, list):
            for item in content:
                total += _estimate_tokens_from_text(str(item))
        else:
            total += _estimate_tokens_from_text(str(content))
    if tools:
        total += _estimate_tokens_from_text(str(tools))
    return total


def clamp_max_output_tokens(plan: str | None, requested_max_tokens: int) -> int:
    policy = get_budget_policy(plan)
    return max(1, min(int(requested_max_tokens or policy.per_request_max_output_tokens), policy.per_request_max_output_tokens))


def estimate_total_request_tokens(system: str, messages: list[dict[str, Any]], requested_max_tokens: int, tools: list[dict[str, Any]] | None = None) -> int:
    return estimate_prompt_tokens(system, messages, tools=tools) + max(1, int(requested_max_tokens or 0))


def estimate_cost_usd(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_rate, output_rate = PROVIDER_COSTS_PER_1K.get(provider.lower(), (0.0, 0.0))
    return round(((prompt_tokens / 1000.0) * input_rate) + ((completion_tokens / 1000.0) * output_rate), 8)


def current_budget_periods(now: datetime | None = None) -> tuple[str, str]:
    ts = now or datetime.now(timezone.utc)
    return ts.strftime("%Y%m%d"), ts.strftime("%Y%m")
