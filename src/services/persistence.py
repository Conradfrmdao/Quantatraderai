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
