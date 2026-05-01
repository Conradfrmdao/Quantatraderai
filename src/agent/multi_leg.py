"""G25: Multi-leg strategy composition.

Allows users to define multi-asset, conditional strategies that the agent
evaluates each tick. Example rule:
    "if RSI(BTC) > 70 then short BTC AND long ETH with 2% each"

Rules are stored in StrategyRule table (text field parsed by nl_parser).
This module evaluates them against live indicator data each tick.

Usage:
    from src.agent.multi_leg import evaluate_multi_leg_rules
    orders = await evaluate_multi_leg_rules(user_id, indicators_by_symbol)
    # orders: list of {"symbol", "action", "allocation_usd", "rationale"}
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("qunta.multi_leg")


def _parse_condition(text: str, indicators: dict[str, Any]) -> bool:
    """Evaluate a simple condition string against indicator values.

    Supported patterns:
        RSI(BTC) > 70
        RSI(BTC) < 30
        MACD(ETH) > 0
        price(XAUUSD) > 2000
    Returns True if condition is met.
    """
    pattern = re.compile(
        r"(rsi|macd|ema|sma|price)\((\w+)\)\s*([<>]=?)\s*([\d.]+)",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if not m:
        return False

    func, sym, op, val_str = m.group(1).lower(), m.group(2).upper(), m.group(3), float(m.group(4))
    ind_key = f"{sym.lower()}:{func}"
    value   = indicators.get(ind_key)

    if value is None:
        return False

    if isinstance(value, list):
        value = value[-1] if value else None
    if value is None:
        return False

    value = float(value)
    if op == ">":  return value > val_str
    if op == "<":  return value < val_str
    if op == ">=": return value >= val_str
    if op == "<=": return value <= val_str
    return False


def _parse_action(text: str) -> list[dict]:
    """Parse action clauses like 'short BTC AND long ETH with 2%'.

    Returns list of {symbol, action, alloc_pct}
    """
    actions = []
    # Split on AND/THEN
    parts = re.split(r"\band\b|\bthen\b", text, flags=re.IGNORECASE)
    for part in parts:
        # Match: (buy|sell|long|short|close) SYMBOL [with N%]
        m = re.search(
            r"\b(buy|sell|long|short|close)\b\s+([A-Z]{2,10}(?:USDT|USD)?)\b(?:.*?with\s+([\d.]+)%)?",
            part, re.IGNORECASE,
        )
        if not m:
            continue
        raw_action = m.group(1).lower()
        symbol     = m.group(2).upper()
        alloc_pct  = float(m.group(3)) if m.group(3) else 2.0

        action = "sell" if raw_action in ("sell", "short") else (
                 "buy"  if raw_action in ("buy",  "long")  else "close"
        )
        actions.append({"symbol": symbol, "action": action, "alloc_pct": alloc_pct})
    return actions


async def evaluate_multi_leg_rules(
    user_id: str | None,
    indicators_by_symbol: dict[str, dict],
    account_equity: float = 10_000.0,
    raw_rules: list[dict] | None = None,
) -> list[dict]:
    """Evaluate all active multi-leg rules for a user.

    indicators_by_symbol: {symbol: {rsi: [...], macd: [...], ...}}
    Returns list of order dicts ready to pass to risk_manager.validate_trade.
    """
    if not user_id and not raw_rules:
        return []

    # Flatten indicators to {symbol:indicator → value} for easy lookup
    flat_indicators: dict[str, Any] = {}
    for sym, inds in indicators_by_symbol.items():
        for k, v in inds.items():
            flat_indicators[f"{sym.lower()}:{k}"] = v

    rules = raw_rules or []
    if not rules and user_id:
        try:
            import os, asyncpg
            db_url = os.getenv("DATABASE_URL", "")
            if db_url:
                conn = await asyncpg.connect(db_url, timeout=5)
                try:
                    rows = await conn.fetch(
                        'SELECT id, text FROM "StrategyRule" WHERE "userId"=$1 AND "isActive"=true',
                        user_id,
                    )
                    rules = [dict(r) for r in rows]
                finally:
                    await conn.close()
        except Exception as e:
            logger.warning("Failed to load multi-leg rules: %s", e)
            return []

    orders = []
    for rule in rules:
        text = rule.get("text", "")
        # Split on IF/WHEN
        if_match = re.split(r"\bif\b|\bwhen\b", text, flags=re.IGNORECASE, maxsplit=1)
        if len(if_match) < 2:
            continue

        condition_text = if_match[1]
        # Split condition from actions on THEN
        then_parts = re.split(r"\bthen\b", condition_text, flags=re.IGNORECASE, maxsplit=1)
        if len(then_parts) < 2:
            continue

        cond_str   = then_parts[0].strip()
        action_str = then_parts[1].strip()

        try:
            if not _parse_condition(cond_str, flat_indicators):
                continue
        except Exception:
            continue

        leg_orders = _parse_action(action_str)
        for leg in leg_orders:
            alloc_usd = account_equity * (leg["alloc_pct"] / 100)
            orders.append({
                "symbol":         leg["symbol"],
                "action":         leg["action"],
                "allocation_usd": round(alloc_usd, 2),
                "current_price":  0,  # filled by caller from price_cache
                "rationale":      f"Multi-leg rule: {text[:80]}",
                "source":         "multi_leg",
                "rule_id":        rule.get("id"),
            })
            logger.info("Multi-leg rule fired: %s → %s %s $%.0f",
                        text[:40], leg["action"], leg["symbol"], alloc_usd)

    return orders
