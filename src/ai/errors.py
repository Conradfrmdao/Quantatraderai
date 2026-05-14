"""Safe AI and trading error taxonomy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AIErrorCode(str, Enum):
    AI_RATE_LIMITED = "AI_RATE_LIMITED"
    AI_PROVIDER_UNAVAILABLE = "AI_PROVIDER_UNAVAILABLE"
    AI_PROVIDER_FAILED = "AI_PROVIDER_FAILED"
    AI_BUDGET_DAILY_EXCEEDED = "AI_BUDGET_DAILY_EXCEEDED"
    AI_BUDGET_MONTHLY_EXCEEDED = "AI_BUDGET_MONTHLY_EXCEEDED"
    AI_AGENT_RUN_BUDGET_EXCEEDED = "AI_AGENT_RUN_BUDGET_EXCEEDED"
    AI_COUNCIL_DISAGREEMENT = "AI_COUNCIL_DISAGREEMENT"
    AI_OUTPUT_INVALID = "AI_OUTPUT_INVALID"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    EXCHANGE_INSUFFICIENT_BALANCE = "EXCHANGE_INSUFFICIENT_BALANCE"
    EXCHANGE_ORDER_REJECTED = "EXCHANGE_ORDER_REJECTED"
    WS_AUTH_REQUIRED = "WS_AUTH_REQUIRED"
    AI_GOVERNANCE_UNAVAILABLE = "AI_GOVERNANCE_UNAVAILABLE"


@dataclass(frozen=True)
class ErrorDefinition:
    code: AIErrorCode
    http_status: int
    severity: str
    user_message: str
    internal_message: str


ERRORS: dict[AIErrorCode, ErrorDefinition] = {
    AIErrorCode.AI_RATE_LIMITED: ErrorDefinition(
        code=AIErrorCode.AI_RATE_LIMITED,
        http_status=429,
        severity="warning",
        user_message="AI usage is temporarily rate limited. No trade was executed.",
        internal_message="AI request rate limited",
    ),
    AIErrorCode.AI_PROVIDER_UNAVAILABLE: ErrorDefinition(
        code=AIErrorCode.AI_PROVIDER_UNAVAILABLE,
        http_status=503,
        severity="error",
        user_message="The selected AI provider is unavailable right now. No trade was executed.",
        internal_message="AI provider unavailable",
    ),
    AIErrorCode.AI_PROVIDER_FAILED: ErrorDefinition(
        code=AIErrorCode.AI_PROVIDER_FAILED,
        http_status=502,
        severity="error",
        user_message="The AI decision failed at the provider layer. No trade was executed.",
        internal_message="AI provider request failed",
    ),
    AIErrorCode.AI_BUDGET_DAILY_EXCEEDED: ErrorDefinition(
        code=AIErrorCode.AI_BUDGET_DAILY_EXCEEDED,
        http_status=403,
        severity="warning",
        user_message="Your daily AI token limit has been reached. No trade was executed.",
        internal_message="Daily AI token budget exceeded",
    ),
    AIErrorCode.AI_BUDGET_MONTHLY_EXCEEDED: ErrorDefinition(
        code=AIErrorCode.AI_BUDGET_MONTHLY_EXCEEDED,
        http_status=403,
        severity="warning",
        user_message="Your monthly AI token limit has been reached. Upgrade or wait for reset.",
        internal_message="Monthly AI token budget exceeded",
    ),
    AIErrorCode.AI_AGENT_RUN_BUDGET_EXCEEDED: ErrorDefinition(
        code=AIErrorCode.AI_AGENT_RUN_BUDGET_EXCEEDED,
        http_status=409,
        severity="warning",
        user_message="This agent run has exhausted its AI budget, so trading paused safely.",
        internal_message="Per-agent-run AI token budget exceeded",
    ),
    AIErrorCode.AI_COUNCIL_DISAGREEMENT: ErrorDefinition(
        code=AIErrorCode.AI_COUNCIL_DISAGREEMENT,
        http_status=409,
        severity="info",
        user_message="The AI council could not reach agreement, so no trade was executed.",
        internal_message="AI council disagreement",
    ),
    AIErrorCode.AI_OUTPUT_INVALID: ErrorDefinition(
        code=AIErrorCode.AI_OUTPUT_INVALID,
        http_status=502,
        severity="warning",
        user_message="The AI response could not be validated safely, so no trade was executed.",
        internal_message="AI output validation failed",
    ),
    AIErrorCode.MARKET_DATA_STALE: ErrorDefinition(
        code=AIErrorCode.MARKET_DATA_STALE,
        http_status=409,
        severity="warning",
        user_message="Market data is stale. The agent paused trading for safety.",
        internal_message="Market data stale",
    ),
    AIErrorCode.EXCHANGE_INSUFFICIENT_BALANCE: ErrorDefinition(
        code=AIErrorCode.EXCHANGE_INSUFFICIENT_BALANCE,
        http_status=409,
        severity="warning",
        user_message="The exchange rejected this order due to insufficient balance. No funds were used.",
        internal_message="Exchange insufficient balance",
    ),
    AIErrorCode.EXCHANGE_ORDER_REJECTED: ErrorDefinition(
        code=AIErrorCode.EXCHANGE_ORDER_REJECTED,
        http_status=409,
        severity="warning",
        user_message="The exchange rejected this order. No funds were used.",
        internal_message="Exchange order rejected",
    ),
    AIErrorCode.WS_AUTH_REQUIRED: ErrorDefinition(
        code=AIErrorCode.WS_AUTH_REQUIRED,
        http_status=401,
        severity="warning",
        user_message="WebSocket authentication is required before live AI updates can be streamed.",
        internal_message="WebSocket authentication required",
    ),
    AIErrorCode.AI_GOVERNANCE_UNAVAILABLE: ErrorDefinition(
        code=AIErrorCode.AI_GOVERNANCE_UNAVAILABLE,
        http_status=503,
        severity="error",
        user_message="AI safeguards are unavailable right now, so AI actions are paused for safety.",
        internal_message="AI governance store unavailable",
    ),
}


@dataclass
class AIError(Exception):
    code: AIErrorCode
    trace_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    retry_after_seconds: int | None = None
    cause: Exception | None = None

    def __str__(self) -> str:
        return f"{self.code.value} trace={self.trace_id}"

    @property
    def definition(self) -> ErrorDefinition:
        return ERRORS[self.code]

    @property
    def http_status(self) -> int:
        return self.definition.http_status


def safe_error_payload(error: AIError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": error.code.value,
            "message": error.definition.user_message,
            "trace_id": error.trace_id,
        }
    }
    if error.retry_after_seconds is not None:
        payload["error"]["retry_after_seconds"] = int(error.retry_after_seconds)
    if error.metadata.get("reason_code"):
        payload["error"]["reason_code"] = error.metadata["reason_code"]
    return payload


def ai_error_response(error: AIError) -> tuple[dict[str, Any], int]:
    return safe_error_payload(error), error.http_status
