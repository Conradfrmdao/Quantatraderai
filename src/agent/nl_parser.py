"""Natural language strategy command parser.

Converts plain English trading rules into structured StrategyRule objects that
the agent evaluates every tick.

Examples:
  "buy BTC when RSI drops below 30"
  "sell ETH if MACD crosses below signal"
  "close SOL when price drops 5% from entry"
  "buy BTC with 3% of portfolio when EMA20 crosses above EMA50"

Uses the configured LLM provider to parse — no hardcoded grammar.
Falls back to simple keyword rules if LLM unavailable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.ai.errors import AIError
from src.ai.governance import AIRequestContext, governed_complete, new_trace_id

logger = logging.getLogger("quantatraderai.agent.nl_parser")


@dataclass
class StrategyRule:
    """A parsed strategy rule that can be evaluated each tick."""
    id:          str
    raw_text:    str
    symbol:      str | None       # None = applies to all
    action:      str              # buy | sell | close
    condition:   str              # human-readable condition description
    indicator:   str              # rsi | macd | ema | price | bbands
    operator:    str              # lt | gt | cross_above | cross_below | pct_drop | pct_rise
    threshold:   float
    allocation_pct: float = 3.0  # % of portfolio
    active:      bool = True
    metadata:    dict  = field(default_factory=dict)


_SYSTEM_PROMPT = """You parse natural language trading rules into JSON.
Return ONLY valid JSON with this structure:
{
  "symbol": "<symbol or null>",
  "action": "buy|sell|close",
  "condition": "<human readable>",
  "indicator": "rsi|macd|ema|price|bbands|volume",
  "operator": "lt|gt|cross_above|cross_below|pct_drop|pct_rise",
  "threshold": <number>,
  "allocation_pct": <number, default 3>
}
"""


async def parse_nl_rule(
    text: str,
    rule_id: str | None = None,
    ai_context: AIRequestContext | None = None,
    stream_handler=None,
) -> StrategyRule | None:
    """Parse a natural language rule string into a StrategyRule."""
    import uuid
    rid = rule_id or str(uuid.uuid4())[:8]

    # Try LLM parsing first
    try:
        from src.agent.providers.factory import get_provider
        provider = get_provider()
        messages = [{"role": "user", "content": f"Parse this trading rule: {text}"}]
        call_ctx = ai_context or AIRequestContext(
            user_id="",
            trace_id=new_trace_id(),
            plan="FREE",
            action="manual_command_parse",
            provider=provider.name,
            model=provider.model,
            mode="paper",
            venue="strategy_rules",
            endpoint="/api/strategies",
            stream=stream_handler is not None,
        )
        resp = await governed_complete(
            provider=provider,
            system=_SYSTEM_PROMPT,
            messages=messages,
            max_tokens=256,
            context=call_ctx,
            stream_handler=stream_handler,
        )
        raw  = resp.content if hasattr(resp, "content") else str(resp)
        start = raw.find("{"); end = raw.rfind("}") + 1
        if start != -1 and end > 0:
            parsed = json.loads(raw[start:end])
            return StrategyRule(
                id=rid, raw_text=text,
                symbol=parsed.get("symbol"),
                action=parsed.get("action", "buy"),
                condition=parsed.get("condition", text),
                indicator=parsed.get("indicator", "rsi"),
                operator=parsed.get("operator", "lt"),
                threshold=float(parsed.get("threshold", 30)),
                allocation_pct=float(parsed.get("allocation_pct", 3)),
            )
    except AIError:
        raise
    except Exception as e:
        logger.warning("LLM parse failed: %s — trying keyword fallback", e)

    # Simple keyword fallback
    return _keyword_parse(text, rid)


def _keyword_parse(text: str, rid: str) -> StrategyRule | None:
    """Very simple keyword-based parser as fallback."""
    low = text.lower()
    action = "buy" if "buy" in low else "sell" if "sell" in low else "close"
    indicator = "rsi"
    for kw in ("macd", "ema", "price", "bbands"):
        if kw in low: indicator = kw; break
    threshold = 30.0
    for token in low.split():
        try:
            v = float(token)
            threshold = v
            break
        except ValueError:
            pass
    operator = "lt" if "below" in low or "drops" in low or "under" in low else "gt"
    return StrategyRule(
        id=rid, raw_text=text, symbol=None,
        action=action, condition=text,
        indicator=indicator, operator=operator, threshold=threshold,
    )


def evaluate_rule(rule: StrategyRule, indicators: dict[str, Any], price: float) -> bool:
    """Return True if the rule's condition is currently met."""
    if not rule.active:
        return False
    from src.indicators.local_indicators import latest

    val: float | None = None
    if rule.indicator == "rsi":
        val = latest(indicators.get("rsi14", []))
    elif rule.indicator == "macd":
        val = latest(indicators.get("macd", []))
    elif rule.indicator == "ema":
        val = latest(indicators.get("ema20", []))
    elif rule.indicator == "price":
        val = price
    elif rule.indicator == "bbands":
        if rule.operator == "lt":
            val = latest(indicators.get("bbands_lower", []))
            return price < (val or float("inf"))
        else:
            val = latest(indicators.get("bbands_upper", []))
            return price > (val or 0)

    if val is None:
        return False

    if rule.operator == "lt":    return val < rule.threshold
    if rule.operator == "gt":    return val > rule.threshold
    if rule.operator == "cross_above":
        prev = indicators.get(f"{rule.indicator}_prev")
        return prev is not None and prev < rule.threshold <= val
    if rule.operator == "cross_below":
        prev = indicators.get(f"{rule.indicator}_prev")
        return prev is not None and prev > rule.threshold >= val

    return False
