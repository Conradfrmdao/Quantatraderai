"""Read venue credentials + agent state from Supabase PostgreSQL.

Uses asyncpg so calls never block the FastAPI event loop.
Credentials are stored AES-256-GCM encrypted by Next.js; this module
decrypts them before returning.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("quantatraderai.db")

_DB_TIMEOUT = 10


async def _connect():
    import asyncpg
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL env var is not set")
    return await asyncpg.connect(db_url, timeout=_DB_TIMEOUT, statement_cache_size=0)


async def _resolve_db_user_id(conn, clerk_user_id: str) -> str | None:
    user_row = await conn.fetchrow(
        'SELECT id FROM "User" WHERE "clerkId" = $1',
        clerk_user_id,
    )
    if not user_row:
        logger.warning("No user found for clerkId=%s", clerk_user_id)
        return None
    return str(user_row["id"])


async def get_user_venues(
    clerk_user_id: str,
    only_active: bool = False,
) -> list[dict[str, Any]]:
    """Return decrypted venues for the given Clerk user ID.

    Args:
        clerk_user_id: Clerk user ID (e.g. user_2abc…)
        only_active: If True, only return venues with isActive=true.
                     Default False so the Test Connection button works on
                     newly-added venues that haven't been activated yet.
    """
    from src.services.encryption import decrypt

    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return []

        if only_active:
            rows = await conn.fetch(
                'SELECT * FROM "Venue" WHERE "userId" = $1 AND "isActive" = true',
                user_id,
            )
        else:
            rows = await conn.fetch(
                'SELECT * FROM "Venue" WHERE "userId" = $1',
                user_id,
            )
    finally:
        await conn.close()

    venues: list[dict[str, Any]] = []
    for row in rows:
        venue = dict(row)
        try:
            if venue.get("apiKey"):
                venue["apiKey"] = decrypt(venue["apiKey"])
            if venue.get("apiSecret"):
                venue["apiSecret"] = decrypt(venue["apiSecret"])
            if venue.get("apiPassphrase"):
                venue["apiPassphrase"] = decrypt(venue["apiPassphrase"])
            if venue.get("metaApiToken"):
                venue["metaApiToken"] = decrypt(venue["metaApiToken"])
        except Exception as e:
            logger.error("Decrypt failed for venue %s: %s — skipping", venue.get("id"), e)
            continue
        venues.append(venue)
    return venues


async def get_user_settings(clerk_user_id: str) -> dict[str, Any] | None:
    """Return UserSettings for the given Clerk user ID, or None."""
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return None
        row = await conn.fetchrow(
            'SELECT * FROM "UserSettings" WHERE "userId" = $1', user_id
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def upsert_agent_run(
    clerk_user_id: str,
    venue: str,
    symbols: list[str],
    timeframe: str,
    is_paper: bool,
    market: str,
    is_running: bool,
) -> None:
    """Persist agent state so it can be resumed on server restart."""
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            logger.warning("upsert_agent_run: unknown clerkId=%s", clerk_user_id)
            return

        import uuid
        await conn.execute(
            """
            INSERT INTO "AgentRun"
                ("id","userId","venue","symbols","timeframe","isPaper","market","isRunning","startedAt")
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW())
            ON CONFLICT ("userId") DO UPDATE SET
                "venue"=$3,"symbols"=$4,"timeframe"=$5,"isPaper"=$6,"market"=$7,
                "isRunning"=$8,
                "stoppedAt"=CASE WHEN $8=false THEN NOW() ELSE NULL END,
                "startedAt"=CASE WHEN $8=true  THEN NOW()
                                 ELSE "AgentRun"."startedAt" END
            """,
            str(uuid.uuid4()), user_id, venue, symbols, timeframe, is_paper, market, is_running,
        )
    except Exception as e:
        logger.warning("upsert_agent_run failed: %s", e)
    finally:
        await conn.close()


async def list_strategy_rules(
    clerk_user_id: str,
    *,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return []

        if active_only:
            rows = await conn.fetch(
                'SELECT * FROM "StrategyRule" WHERE "userId" = $1 AND "isActive" = true ORDER BY "createdAt" ASC',
                user_id,
            )
        else:
            rows = await conn.fetch(
                'SELECT * FROM "StrategyRule" WHERE "userId" = $1 ORDER BY "createdAt" ASC',
                user_id,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("list_strategy_rules failed: %s", e)
        return []
    finally:
        await conn.close()


async def create_strategy_rule(clerk_user_id: str, rule: Any) -> dict[str, Any] | None:
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return None

        row = await conn.fetchrow(
            """
            INSERT INTO "StrategyRule"
                ("id","userId","text","symbol","action","condition","indicator","operator","threshold","allocationPct","isActive","createdAt","updatedAt")
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW(),NOW())
            RETURNING *
            """,
            str(rule.id),
            user_id,
            str(rule.raw_text),
            rule.symbol,
            str(rule.action),
            str(rule.condition),
            str(rule.indicator),
            str(rule.operator),
            float(rule.threshold),
            float(rule.allocation_pct),
            bool(rule.active),
        )
        return dict(row) if row else None
    except Exception as e:
        logger.warning("create_strategy_rule failed: %s", e)
        return None
    finally:
        await conn.close()


async def delete_strategy_rule(clerk_user_id: str, rule_id: str) -> bool:
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return False

        status = await conn.execute(
            'DELETE FROM "StrategyRule" WHERE "id" = $1 AND "userId" = $2',
            rule_id,
            user_id,
        )
        return status.endswith("1")
    except Exception as e:
        logger.warning("delete_strategy_rule failed: %s", e)
        return False
    finally:
        await conn.close()


async def get_running_agents() -> list[dict[str, Any]]:
    """Return all AgentRun rows where isRunning=true (for boot-time resume)."""
    conn = await _connect()
    try:
        rows = await conn.fetch(
            """
            SELECT ar.*, u."clerkId"
            FROM "AgentRun" ar
            JOIN "User" u ON u.id = ar."userId"
            WHERE ar."isRunning" = true
            """
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("get_running_agents failed: %s", e)
        return []
    finally:
        await conn.close()
