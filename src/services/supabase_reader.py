"""Read venue credentials + agent state from Supabase PostgreSQL.

Uses asyncpg so calls never block the FastAPI event loop.
Credentials are stored AES-256-GCM encrypted by Next.js; this module
decrypts them before returning.
"""
from __future__ import annotations

import json
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


async def get_user_plan(clerk_user_id: str) -> str:
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return "FREE"
        row = await conn.fetchrow('SELECT plan FROM "User" WHERE id = $1', user_id)
        return str(row["plan"]) if row else "FREE"
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
) -> str | None:
    """Persist agent state so it can be resumed on server restart."""
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            logger.warning("upsert_agent_run: unknown clerkId=%s", clerk_user_id)
            return

        import uuid
        row = await conn.fetchrow(
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
            RETURNING "id"
            """,
            str(uuid.uuid4()), user_id, venue, symbols, timeframe, is_paper, market, is_running,
        )
        return str(row["id"]) if row else None
    except Exception as e:
        logger.warning("upsert_agent_run failed: %s", e)
        return None
    finally:
        await conn.close()


async def load_agent_warm_state(clerk_user_id: str) -> dict[str, Any] | None:
    """Return the most recent warm startup snapshot stored on AgentRun."""
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return None
        row = await conn.fetchrow(
            'SELECT "warmState", "warmStateUpdatedAt" FROM "AgentRun" WHERE "userId" = $1',
            user_id,
        )
        if not row or not row["warmState"]:
            return None
        payload = json.loads(str(row["warmState"]))
        if row["warmStateUpdatedAt"]:
            payload.setdefault("persisted_at", row["warmStateUpdatedAt"].isoformat())
        return payload
    except Exception as e:
        logger.warning("load_agent_warm_state failed: %s", e)
        return None
    finally:
        await conn.close()


async def save_agent_warm_state(clerk_user_id: str, warm_state: dict[str, Any]) -> bool:
    """Persist the latest warm startup snapshot on AgentRun."""
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return False
        status = await conn.execute(
            """
            UPDATE "AgentRun"
            SET "warmState" = $2,
                "warmStateUpdatedAt" = NOW()
            WHERE "userId" = $1
            """,
            user_id,
            json.dumps(warm_state),
        )
        return status.endswith("1")
    except Exception as e:
        logger.warning("save_agent_warm_state failed: %s", e)
        return False
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


async def find_venue_id(clerk_user_id: str, venue_name: str) -> str | None:
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return None
        rows = await conn.fetch('SELECT id, type FROM "Venue" WHERE "userId" = $1', user_id)
        for row in rows:
            normalized = str(row["type"]).lower()
            if normalized == venue_name.lower() or normalized == venue_name.split(":")[0].upper().lower():
                return str(row["id"])
        return None
    except Exception as e:
        logger.warning("find_venue_id failed: %s", e)
        return None
    finally:
        await conn.close()


async def list_ai_decisions(clerk_user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return []

        decision_rows = await conn.fetch(
            """
            SELECT *
            FROM "AIDecision"
            WHERE "userId" = $1
            ORDER BY "createdAt" DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
        decision_ids = [str(row["id"]) for row in decision_rows]
        votes_by_decision: dict[str, list[dict[str, Any]]] = {}
        if decision_ids:
            vote_rows = await conn.fetch(
                """
                SELECT *
                FROM "AICouncilVote"
                WHERE "decisionId" = ANY($1::text[])
                ORDER BY "createdAt" ASC
                """,
                decision_ids,
            )
            for row in vote_rows:
                votes_by_decision.setdefault(str(row["decisionId"]), []).append(dict(row))

        results: list[dict[str, Any]] = []
        for row in decision_rows:
            payload = dict(row)
            votes = votes_by_decision.get(str(row["id"]), [])
            results.append({
                "ts": payload["createdAt"].isoformat(),
                "trace_id": payload["traceId"],
                "reasoning_summary": payload["reasoningSummary"],
                "trade_decisions": [{
                    "asset": payload["symbol"],
                    "action": payload["finalAction"],
                    "rationale": payload["reasoningSummary"],
                    "allocation_usd": 0.0,
                    "confidence": payload["confidence"],
                    "deadlock": payload["riskDecision"] == "deadlock",
                    "council": [
                        {
                            "role": vote.get("role"),
                            "provider": vote.get("provider"),
                            "action": vote.get("voteAction"),
                            "confidence": vote.get("confidence"),
                            "rationale": vote.get("reasoningSummary"),
                            "veto": vote.get("voteAction") == "hold" and vote.get("role") == "risk_officer",
                        }
                        for vote in votes
                    ] if votes else None,
                }],
                "council": [{
                    "asset": payload["symbol"],
                    "vote": payload["finalAction"],
                    "confidence": payload["confidence"],
                    "deadlock": payload["riskDecision"] == "deadlock",
                    "opinions": [
                        {
                            "role": vote.get("role"),
                            "provider": vote.get("provider"),
                            "action": vote.get("voteAction"),
                            "confidence": vote.get("confidence"),
                            "rationale": vote.get("reasoningSummary"),
                            "veto": vote.get("voteAction") == "hold" and vote.get("role") == "risk_officer",
                        }
                        for vote in votes
                    ],
                }] if votes else None,
            })
        return results
    except Exception as e:
        logger.warning("list_ai_decisions failed: %s", e)
        return []
    finally:
        await conn.close()
