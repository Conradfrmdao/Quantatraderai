"""Per-plan AI provider and council policy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AIPlanPolicy:
    primary_providers: tuple[str, ...]
    fallback_providers: tuple[str, ...]
    sanitize_providers: tuple[str, ...]
    council_enabled: bool
    council_providers: tuple[str, ...]
    council_active_models: int
    dormant_providers: tuple[str, ...] = ()


PLAN_AI_POLICY: dict[str, AIPlanPolicy] = {
    "FREE": AIPlanPolicy(
        primary_providers=("groq",),
        fallback_providers=(),
        sanitize_providers=("groq",),
        council_enabled=False,
        council_providers=(),
        council_active_models=1,
    ),
    "STARTER": AIPlanPolicy(
        primary_providers=("groq",),
        fallback_providers=("gemini",),
        sanitize_providers=("gemini", "groq"),
        council_enabled=False,
        council_providers=(),
        council_active_models=1,
    ),
    "PRO": AIPlanPolicy(
        primary_providers=("groq",),
        fallback_providers=("gemini",),
        sanitize_providers=("gemini", "groq"),
        council_enabled=True,
        council_providers=("groq", "gemini"),
        council_active_models=2,
    ),
    "ENTERPRISE": AIPlanPolicy(
        primary_providers=("groq",),
        fallback_providers=("gemini",),
        sanitize_providers=("gemini", "groq"),
        council_enabled=True,
        council_providers=("groq", "gemini"),
        council_active_models=2,
        dormant_providers=("bedrock",),
    ),
}


def get_ai_plan_policy(plan: str | None) -> AIPlanPolicy:
    return PLAN_AI_POLICY.get(str(plan or "FREE").upper(), PLAN_AI_POLICY["FREE"])
