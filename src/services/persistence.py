"""Persistent writes to Supabase from the Python backend.

Every decision, order, equity tick, and lifecycle event is written here
so the dashboard /audit, /journal, equity curve, and compliance reports
have real data. All calls are fire-and-forget (no exception propagates
to the trading loop).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger("quantatraderai.persistence")

_DB_TIMEOUT = 6


async def _connect():
    import asyncpg
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    return await asyncpg.connect(db_url, timeout=_DB_TIMEOUT)


async def _user_id_for_clerk(conn, clerk_user_id: str) -> str | None:
    row = await conn.fetchrow('SELECT id FROM "User" WHERE "clerkId" = $1', clerk_user_id)
    return row["id"] if row else None


async def write_audit(
    clerk_user_id: str | None,
    event: str,
    symbol: str | None = None,
    action: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Append to immutable AuditLog. Never raises."""
    if not clerk_user_id:
        return
    try:
        conn = await _connect()
        if conn is None:
            return
        try:
            user_id = await _user_id_for_clerk(conn, clerk_user_id)
            if not user_id:
                return
            await conn.execute(
                """
                INSERT INTO "AuditLog" ("id","userId","event","symbol","action","data","createdAt")
                VALUES ($1,$2,$3,$4,$5,$6,NOW())
                """,
                str(uuid.uuid4()), user_id, event, symbol, action,
                json.dumps(data or {}, default=str),
            )
        finally:
            await conn.close()
    except Exception as e:
        logger.debug("write_audit skipped: %s", e)


async def write_equity_point(
    clerk_user_id: str | None,
    equity: float,
    balance: float,
    pnl: float = 0.0,
    tick_count: int = 0,
) -> None:
    """Persist one equity curve sample."""
    if not clerk_user_id:
        return
    try:
        conn = await _connect()
        if conn is None:
            return
        try:
            user_id = await _user_id_for_clerk(conn, clerk_user_id)
            if not user_id:
                return
            await conn.execute(
                """
                INSERT INTO "EquityPoint" ("id","userId","equity","balance","pnl","tickCount","createdAt")
                VALUES ($1,$2,$3,$4,$5,$6,NOW())
                """,
                str(uuid.uuid4()), user_id, float(equity), float(balance),
                float(pnl), int(tick_count),
            )
        finally:
            await conn.close()
    except Exception as e:
        logger.debug("write_equity_point skipped: %s", e)


async def write_trade_log(
    clerk_user_id: str | None,
    symbol: str,
    action: str,
    quantity: float,
    price: float,
    allocation_usd: float = 0.0,
    pnl: float = 0.0,
    source: str = "agent",
    rationale: str | None = None,
    tp_price: float | None = None,
    sl_price: float | None = None,
) -> None:
    """Persist a filled order to the trade journal."""
    if not clerk_user_id:
        return
    try:
        conn = await _connect()
        if conn is None:
            return
        try:
            user_id = await _user_id_for_clerk(conn, clerk_user_id)
            if not user_id:
                return
            await conn.execute(
                """
                INSERT INTO "TradeLog"
                    ("id","userId","symbol","action","quantity","price",
                     "allocationUsd","pnl","source","rationale","tpPrice","slPrice","createdAt")
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,NOW())
                """,
                str(uuid.uuid4()), user_id, symbol, action,
                float(quantity), float(price),
                float(allocation_usd), float(pnl),
                source, rationale, tp_price, sl_price,
            )
        finally:
            await conn.close()
    except Exception as e:
        logger.debug("write_trade_log skipped: %s", e)


async def write_ai_usage_log(
    clerk_user_id: str | None,
    *,
    agent_run_id: str | None,
    provider: str,
    model: str,
    action: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float,
    trace_id: str,
    mode: str,
    venue: str | None,
) -> None:
    if not clerk_user_id:
        return
    try:
        conn = await _connect()
        if conn is None:
            return
        try:
            user_id = await _user_id_for_clerk(conn, clerk_user_id)
            if not user_id:
                return
            await conn.execute(
                """
                INSERT INTO "AIUsageLog"
                    ("id","userId","agentRunId","provider","model","action",
                     "promptTokens","completionTokens","totalTokens","estimatedCostUsd",
                     "traceId","mode","venue","createdAt")
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NOW())
                """,
                str(uuid.uuid4()),
                user_id,
                agent_run_id,
                provider,
                model,
                action,
                int(prompt_tokens),
                int(completion_tokens),
                int(total_tokens),
                float(estimated_cost_usd),
                trace_id,
                mode,
                venue,
            )
        finally:
            await conn.close()
    except Exception as e:
        logger.debug("write_ai_usage_log skipped: %s", e)


async def write_ai_decision(
    clerk_user_id: str | None,
    *,
    agent_run_id: str | None,
    venue_id: str | None,
    trace_id: str,
    mode: str,
    persona: str | None,
    symbol: str,
    provider: str,
    model: str,
    final_action: str,
    confidence: float,
    reasoning_summary: str,
    risk_decision: str,
    is_council: bool,
) -> str | None:
    if not clerk_user_id:
        return None
    try:
        conn = await _connect()
        if conn is None:
            return None
        try:
            user_id = await _user_id_for_clerk(conn, clerk_user_id)
            if not user_id:
                return None
            row_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO "AIDecision"
                    ("id","userId","agentRunId","venueId","traceId","mode","persona",
                     "symbol","provider","model","finalAction","confidence",
                     "reasoningSummary","riskDecision","isCouncil","createdAt")
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,NOW())
                """,
                row_id,
                user_id,
                agent_run_id,
                venue_id,
                trace_id,
                mode,
                persona,
                symbol,
                provider,
                model,
                final_action,
                float(confidence),
                reasoning_summary,
                risk_decision,
                bool(is_council),
            )
            return row_id
        finally:
            await conn.close()
    except Exception as e:
        logger.debug("write_ai_decision skipped: %s", e)
        return None


async def write_ai_council_vote(
    clerk_user_id: str | None,
    *,
    decision_id: str,
    provider: str,
    model: str,
    role: str,
    vote_action: str,
    confidence: float,
    reasoning_summary: str,
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float,
    trace_id: str,
) -> str | None:
    if not clerk_user_id:
        return None
    try:
        conn = await _connect()
        if conn is None:
            return None
        try:
            user_id = await _user_id_for_clerk(conn, clerk_user_id)
            if not user_id:
                return None
            row_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO "AICouncilVote"
                    ("id","decisionId","userId","provider","model","role","voteAction",
                     "confidence","reasoningSummary","latencyMs","promptTokens",
                     "completionTokens","totalTokens","estimatedCostUsd","traceId","createdAt")
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,NOW())
                """,
                row_id,
                decision_id,
                user_id,
                provider,
                model,
                role,
                vote_action,
                float(confidence),
                reasoning_summary,
                int(latency_ms),
                int(prompt_tokens),
                int(completion_tokens),
                int(total_tokens),
                float(estimated_cost_usd),
                trace_id,
            )
            return row_id
        finally:
            await conn.close()
    except Exception as e:
        logger.debug("write_ai_council_vote skipped: %s", e)
        return None
