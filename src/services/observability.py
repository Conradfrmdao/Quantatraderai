"""Structured observability helpers — trace_id, structured log context.

Every trade operation should call with_trace(trace_id) to propagate the ID
through all log entries and the final TradeReceipt.

Usage:
    from src.services.observability import TraceContext, structured_log

    ctx = TraceContext(user_id="u123", venue="binance", trace_id=str(uuid4()))
    structured_log(logger, "info", ctx, "Trade placed", symbol="BTCUSDT", action="buy")
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class TraceContext:
    user_id:  str
    venue:    str
    trace_id: str = ""
    symbol:   str = ""
    action:   str = ""

    def __post_init__(self):
        if not self.trace_id:
            self.trace_id = str(uuid.uuid4())

    def to_dict(self) -> dict[str, str]:
        return {k: v for k, v in asdict(self).items() if v}


def structured_log(
    logger: logging.Logger,
    level: str,
    ctx: TraceContext,
    message: str,
    **extra: Any,
) -> None:
    """Emit a structured log entry guaranteed to contain trace_id, user_id, venue."""
    payload = {
        "trace_id": ctx.trace_id,
        "user_id":  ctx.user_id,
        "venue":    ctx.venue,
        "message":  message,
    }
    if ctx.symbol: payload["symbol"] = ctx.symbol
    if ctx.action: payload["action"] = ctx.action
    payload.update(extra)
    log_fn = getattr(logger, level, logger.info)
    log_fn(json.dumps(payload))


def human_error(code: str, context: dict[str, Any] | None = None) -> str:
    """Return a human-readable, non-technical error message for the UI.

    Follows the "Failure Transparency" principle: never say "Error occurred",
    always say exactly what happened and whether any funds were touched.
    """
    ctx = context or {}
    messages: dict[str, str] = {
        "INVALID_API_KEY": (
            "Your {venue} API key is invalid or has been revoked. "
            "No trades were attempted. Go to Settings → Venues to update your credentials."
        ),
        "INSUFFICIENT_BALANCE": (
            "Your {venue} account has insufficient balance (${available:.2f} available, "
            "${required:.2f} required). No funds were used."
        ),
        "SYMBOL_NOT_FOUND": (
            "The symbol {symbol} is not available on {venue}. "
            "No order was placed. Check the symbol format in Settings."
        ),
        "RATE_LIMITED": (
            "{venue} is temporarily rate-limiting requests. "
            "No trades were affected. The agent will retry automatically in {retry_s:.0f}s."
        ),
        "NETWORK_TIMEOUT": (
            "Connection to {venue} timed out after {timeout_s:.0f}s. "
            "No order was placed. The position is unchanged."
        ),
        "RISK_BLOCKED": (
            "This trade was blocked by your risk rules: {reason}. "
            "No funds were used. Adjust risk settings if needed."
        ),
        "MARKET_CLOSED": (
            "{venue} market for {symbol} is currently closed. "
            "No order was placed. The agent will retry at market open."
        ),
        "DUPLICATE_SIGNAL": (
            "A duplicate TradingView signal was received and ignored. "
            "Only one trade per signal is executed."
        ),
        "KILL_SWITCH_CONFIRM": (
            "Emergency stop requires confirmation within 5 seconds. "
            "No positions were closed yet."
        ),
        "PLAN_LIMIT": (
            "This feature requires the {plan_required} plan. "
            "Your current plan is {current_plan}. Upgrade at /billing."
        ),
        "AGENT_NOT_RUNNING": (
            "The trading agent is not currently running. "
            "Start it from the dashboard before sending signals."
        ),
        "DECRYPTION_FAILED": (
            "Your stored credentials could not be decrypted. "
            "This may happen if the encryption key was rotated. "
            "Please reconnect your {venue} account in Settings."
        ),
    }
    template = messages.get(code, "An unexpected error occurred. No trades were affected.")
    try:
        return template.format(**ctx)
    except KeyError:
        return template  # return unformatted if context keys are missing
