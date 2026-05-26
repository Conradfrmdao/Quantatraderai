"""Durable position reconciliation against venue or paper source-of-truth."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("quantatraderai.positions")

_DB_TIMEOUT = 8


@dataclass
class ReconciliationResult:
    positions: list[dict[str, Any]]
    source: str
    reconciled_at: str
    warnings: list[str] = field(default_factory=list)
    changes: list[dict[str, Any]] = field(default_factory=list)
    is_paper: bool = False


def _runtime_value(runtime: Any, key: str, default: Any = None) -> Any:
    if isinstance(runtime, dict):
        return runtime.get(key, default)
    return getattr(runtime, key, default)


def _runtime_symbols(runtime: Any) -> list[str]:
    symbols = _runtime_value(runtime, "symbols", []) or []
    if isinstance(symbols, str):
        return [symbols]
    return list(symbols)


def _infer_asset_class(venue_name: str, market: str) -> str:
    venue = str(venue_name or "").lower()
    mode = str(market or "").lower()
    if venue in {"oanda", "metatrader"}:
        return "forex"
    if venue in {"alpaca", "ibkr"}:
        return "stocks"
    if venue == "polymarket":
        return "prediction"
    if mode in {"spot", "cash"}:
        return "crypto_spot"
    return "crypto_perp"


def _symbol_cache_key(symbol: str) -> str:
    return str(symbol or "").replace("/", "").replace("_", "").split(":")[0].upper()


def _signed_quantity(side: str, quantity: float) -> float:
    qty = abs(float(quantity or 0.0))
    return qty if side == "long" else -qty


def _serialize_position_row(row: Any) -> dict[str, Any]:
    side = str(row["side"] or "long")
    qty = _signed_quantity(side, float(row["quantity"] or 0.0))
    return {
        "symbol": str(row["symbol"] or ""),
        "quantity": qty,
        "side": side,
        "entry_price": float(row["entryPrice"] or 0.0),
        "current_price": float(row["currentPrice"] or 0.0),
        "unrealized_pnl": float(row["unrealizedPnl"] or 0.0),
        "realized_pnl": float(row["realizedPnl"] or 0.0),
        "leverage": float(row["leverage"]) if row["leverage"] is not None else None,
        "liquidation_price": float(row["liquidationPrice"]) if row["liquidationPrice"] is not None else None,
        "status": str(row["status"] or "open"),
        "source": str(row["source"] or ""),
        "trace_id": str(row["traceId"] or ""),
        "mode": str(row["mode"] or ""),
        "market": str(row["market"] or ""),
        "asset_class": str(row["assetClass"] or ""),
        "reconciled_at": row["lastSyncedAt"].isoformat() if row["lastSyncedAt"] else None,
        "closed_at": row["closedAt"].isoformat() if row["closedAt"] else None,
    }


async def _connect():
    import asyncpg

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL env var is not set")
    return await asyncpg.connect(db_url, timeout=_DB_TIMEOUT, statement_cache_size=0)


async def _resolve_db_user_id(conn: Any, clerk_user_id: str) -> str | None:
    row = await conn.fetchrow('SELECT id FROM "User" WHERE "clerkId" = $1', clerk_user_id)
    return str(row["id"]) if row else None


def _merge_positions(
    items: list[dict[str, Any]],
    *,
    warnings: list[str],
) -> list[dict[str, Any]]:
    by_symbol: dict[str, dict[str, Any]] = {}
    for item in items:
        symbol = str(item["symbol"] or "")
        side = str(item["side"] or "long")
        signed_qty = _signed_quantity(side, float(item["quantity"] or 0.0))
        if not symbol or signed_qty == 0:
            continue
        existing = by_symbol.get(symbol)
        if existing is None:
            by_symbol[symbol] = dict(item, signed_qty=signed_qty)
            continue

        warnings.append(f"Duplicate position snapshot merged for {symbol}.")
        merged_qty = float(existing["signed_qty"]) + signed_qty
        if merged_qty == 0:
            by_symbol.pop(symbol, None)
            continue

        weight_existing = abs(float(existing["signed_qty"]))
        weight_new = abs(signed_qty)
        total_weight = weight_existing + weight_new
        existing["entry_price"] = (
            (float(existing["entry_price"]) * weight_existing)
            + (float(item["entry_price"]) * weight_new)
        ) / total_weight
        existing["current_price"] = float(item.get("current_price") or existing.get("current_price") or 0.0)
        existing["unrealized_pnl"] = float(existing.get("unrealized_pnl") or 0.0) + float(item.get("unrealized_pnl") or 0.0)
        existing["signed_qty"] = merged_qty
        existing["side"] = "long" if merged_qty > 0 else "short"
        existing["quantity"] = abs(merged_qty)
        if item.get("liquidation_price") is not None:
            existing["liquidation_price"] = item.get("liquidation_price")
        if item.get("leverage") is not None:
            existing["leverage"] = item.get("leverage")

    merged: list[dict[str, Any]] = []
    for item in by_symbol.values():
        item.pop("signed_qty", None)
        merged.append(item)
    return merged


def _normalize_paper_positions(
    runtime: Any,
    warnings: list[str],
) -> list[dict[str, Any]]:
    positions = _runtime_value(runtime, "paper_positions", []) or []
    price_cache = _runtime_value(runtime, "price_cache", {}) or {}
    normalized: list[dict[str, Any]] = []
    for pos in positions:
        symbol = str(pos.get("symbol") or "")
        qty = float(pos.get("quantity") or 0.0)
        entry_price = float(pos.get("entry_price") or 0.0)
        current_price = float(pos.get("current_price") or 0.0) or float(price_cache.get(_symbol_cache_key(symbol)) or entry_price)
        normalized.append(
            {
                "symbol": symbol,
                "side": "long" if qty >= 0 else "short",
                "quantity": abs(qty),
                "entry_price": entry_price,
                "current_price": current_price,
                "unrealized_pnl": float(pos.get("unrealized_pnl") or 0.0),
                "realized_pnl": float(pos.get("realized_pnl") or 0.0),
                "leverage": pos.get("leverage"),
                "liquidation_price": pos.get("liquidation_price"),
                "source": "paper_ledger",
                "external_position_id": None,
            }
        )
    return _merge_positions(normalized, warnings=warnings)


def _normalize_live_positions(
    runtime: Any,
    raw_positions: list[Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    price_cache = _runtime_value(runtime, "price_cache", {}) or {}
    normalized: list[dict[str, Any]] = []
    for pos in raw_positions or []:
        symbol = str(getattr(pos, "symbol", "") or "")
        quantity = float(getattr(pos, "quantity", 0.0) or 0.0)
        if quantity == 0:
            continue
        entry_price = float(getattr(pos, "entry_price", 0.0) or 0.0)
        current_price = float(getattr(pos, "current_price", 0.0) or 0.0) or float(price_cache.get(_symbol_cache_key(symbol)) or entry_price)
        normalized.append(
            {
                "symbol": symbol,
                "side": "long" if quantity > 0 else "short",
                "quantity": abs(quantity),
                "entry_price": entry_price,
                "current_price": current_price,
                "unrealized_pnl": float(getattr(pos, "unrealized_pnl", 0.0) or 0.0),
                "realized_pnl": 0.0,
                "leverage": getattr(pos, "leverage", None),
                "liquidation_price": getattr(pos, "liquidation_price", None),
                "source": str(_runtime_value(runtime, "venue_name", "venue") or "venue"),
                "external_position_id": symbol,
            }
        )
    return _merge_positions(normalized, warnings=warnings)


async def list_positions(
    clerk_user_id: str | None,
    *,
    include_closed: bool = False,
    venue: str | None = None,
    market: str | None = None,
    mode: str | None = None,
) -> list[dict[str, Any]]:
    if not clerk_user_id:
        return []
    conn = await _connect()
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return []
        clauses = ['"userId" = $1']
        params: list[Any] = [user_id]
        if not include_closed:
            clauses.append('"status" = \'open\'')
        if venue:
            params.append(venue)
            clauses.append(f'"venue" = ${len(params)}')
        if market:
            params.append(market)
            clauses.append(f'"market" = ${len(params)}')
        if mode:
            params.append(mode)
            clauses.append(f'"mode" = ${len(params)}')
        rows = await conn.fetch(
            f'''
            SELECT *
            FROM "Position"
            WHERE {' AND '.join(clauses)}
            ORDER BY "status" ASC, "updatedAt" DESC, "symbol" ASC
            ''',
            *params,
        )
        return [_serialize_position_row(row) for row in rows]
    finally:
        await conn.close()


async def reconcile_positions(
    clerk_user_id: str | None,
    venue_runtime: Any,
    mode: str,
    reason: str,
    trace_id: str,
) -> ReconciliationResult:
    venue_name = str(_runtime_value(venue_runtime, "venue_name", "unknown") or "unknown")
    market = str(_runtime_value(venue_runtime, "market", "spot") or "spot")
    is_paper = bool(_runtime_value(venue_runtime, "is_paper", False))
    asset_class = str(_runtime_value(venue_runtime, "asset_class", "") or _infer_asset_class(venue_name, market))
    reconciled_at = datetime.now(timezone.utc).isoformat()
    warnings: list[str] = []

    if not clerk_user_id:
        return ReconciliationResult(
            positions=[],
            source="paper_ledger" if is_paper else venue_name,
            reconciled_at=reconciled_at,
            warnings=["Cannot reconcile positions without a user context."],
            is_paper=is_paper,
        )

    try:
        if is_paper:
            normalized = _normalize_paper_positions(venue_runtime, warnings)
            source = "paper_ledger"
        else:
            venue = _runtime_value(venue_runtime, "venue")
            if venue is None:
                raise RuntimeError("Venue runtime is not initialised.")
            raw_positions = await venue.get_positions()
            normalized = _normalize_live_positions(venue_runtime, raw_positions, warnings)
            source = venue_name
    except Exception as exc:
        logger.warning("Position reconciliation source fetch failed for %s: %s", clerk_user_id, exc)
        cached = await list_positions(clerk_user_id, include_closed=False, venue=venue_name, market=market, mode=mode)
        return ReconciliationResult(
            positions=cached,
            source="paper_ledger" if is_paper else venue_name,
            reconciled_at=reconciled_at,
            warnings=[f"Position reconciliation skipped: {exc}"],
            is_paper=is_paper,
        )

    conn = await _connect()
    changes: list[dict[str, Any]] = []
    try:
        user_id = await _resolve_db_user_id(conn, clerk_user_id)
        if not user_id:
            return ReconciliationResult(
                positions=[],
                source=source,
                reconciled_at=reconciled_at,
                warnings=["No database user record exists for this session."],
                is_paper=is_paper,
            )

        existing_rows = await conn.fetch(
            '''
            SELECT *
            FROM "Position"
            WHERE "userId" = $1 AND "venue" = $2 AND "market" = $3 AND "mode" = $4
            ''',
            user_id,
            venue_name,
            market,
            mode,
        )
        existing_by_symbol = {str(row["symbol"]): row for row in existing_rows}
        active_symbols = [item["symbol"] for item in normalized]

        async with conn.transaction():
            for item in normalized:
                prior = existing_by_symbol.get(item["symbol"])
                row = await conn.fetchrow(
                    '''
                    INSERT INTO "Position"
                        ("id","userId","venue","assetClass","market","mode","symbol","side",
                         "quantity","entryPrice","currentPrice","realizedPnl","unrealizedPnl",
                         "leverage","liquidationPrice","source","externalPositionId","traceId",
                         "status","openedAt","closedAt","lastSyncedAt","createdAt","updatedAt")
                    VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,
                        $9,$10,$11,$12,$13,
                        $14,$15,$16,$17,$18,
                        'open',$19,NULL,$20,$20,$20
                    )
                    ON CONFLICT ("userId","venue","symbol","market","mode")
                    DO UPDATE SET
                        "assetClass" = EXCLUDED."assetClass",
                        "side" = EXCLUDED."side",
                        "quantity" = EXCLUDED."quantity",
                        "entryPrice" = EXCLUDED."entryPrice",
                        "currentPrice" = EXCLUDED."currentPrice",
                        "realizedPnl" = CASE
                            WHEN "Position"."status" <> 'open' THEN 0
                            ELSE COALESCE("Position"."realizedPnl", 0)
                        END,
                        "unrealizedPnl" = EXCLUDED."unrealizedPnl",
                        "leverage" = EXCLUDED."leverage",
                        "liquidationPrice" = EXCLUDED."liquidationPrice",
                        "source" = EXCLUDED."source",
                        "externalPositionId" = EXCLUDED."externalPositionId",
                        "traceId" = EXCLUDED."traceId",
                        "status" = 'open',
                        "openedAt" = CASE
                            WHEN "Position"."status" <> 'open' OR "Position"."openedAt" IS NULL
                                THEN COALESCE(EXCLUDED."openedAt", NOW())
                            ELSE "Position"."openedAt"
                        END,
                        "closedAt" = NULL,
                        "lastSyncedAt" = EXCLUDED."lastSyncedAt",
                        "updatedAt" = EXCLUDED."updatedAt"
                    RETURNING *
                    ''',
                    str(uuid.uuid4()),
                    user_id,
                    venue_name,
                    asset_class,
                    market,
                    mode,
                    item["symbol"],
                    item["side"],
                    float(item["quantity"] or 0.0),
                    float(item["entry_price"] or 0.0),
                    float(item["current_price"] or 0.0),
                    float(item.get("realized_pnl") or 0.0),
                    float(item.get("unrealized_pnl") or 0.0),
                    float(item["leverage"]) if item.get("leverage") is not None else None,
                    float(item["liquidation_price"]) if item.get("liquidation_price") is not None else None,
                    source,
                    item.get("external_position_id"),
                    trace_id,
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                )
                if prior is None or str(prior["status"] or "") != "open":
                    changes.append({"type": "position_opened", "position": _serialize_position_row(row)})
                else:
                    if (
                        float(prior["quantity"] or 0.0) != float(row["quantity"] or 0.0)
                        or float(prior["currentPrice"] or 0.0) != float(row["currentPrice"] or 0.0)
                        or float(prior["unrealizedPnl"] or 0.0) != float(row["unrealizedPnl"] or 0.0)
                        or str(prior["side"] or "") != str(row["side"] or "")
                    ):
                        changes.append({"type": "position_updated", "position": _serialize_position_row(row)})

            if active_symbols:
                closed_rows = await conn.fetch(
                    '''
                    UPDATE "Position"
                    SET "status" = 'closed',
                        "closedAt" = COALESCE("closedAt", NOW()),
                        "traceId" = $5,
                        "source" = $6,
                        "realizedPnl" = CASE
                            WHEN "status" = 'open' THEN COALESCE("realizedPnl", 0) + COALESCE("unrealizedPnl", 0)
                            ELSE COALESCE("realizedPnl", 0)
                        END,
                        "unrealizedPnl" = 0,
                        "lastSyncedAt" = NOW(),
                        "updatedAt" = NOW()
                    WHERE "userId" = $1
                      AND "venue" = $2
                      AND "market" = $3
                      AND "mode" = $4
                      AND "status" = 'open'
                      AND NOT ("symbol" = ANY($7::text[]))
                    RETURNING *
                    ''',
                    user_id,
                    venue_name,
                    market,
                    mode,
                    trace_id,
                    source,
                    active_symbols,
                )
            else:
                closed_rows = await conn.fetch(
                    '''
                    UPDATE "Position"
                    SET "status" = 'closed',
                        "closedAt" = COALESCE("closedAt", NOW()),
                        "traceId" = $5,
                        "source" = $6,
                        "realizedPnl" = CASE
                            WHEN "status" = 'open' THEN COALESCE("realizedPnl", 0) + COALESCE("unrealizedPnl", 0)
                            ELSE COALESCE("realizedPnl", 0)
                        END,
                        "unrealizedPnl" = 0,
                        "lastSyncedAt" = NOW(),
                        "updatedAt" = NOW()
                    WHERE "userId" = $1
                      AND "venue" = $2
                      AND "market" = $3
                      AND "mode" = $4
                      AND "status" = 'open'
                    RETURNING *
                    ''',
                    user_id,
                    venue_name,
                    market,
                    mode,
                    trace_id,
                    source,
                )
            for row in closed_rows:
                changes.append({"type": "position_closed", "position": _serialize_position_row(row)})

        rows = await conn.fetch(
            '''
            SELECT *
            FROM "Position"
            WHERE "userId" = $1
              AND "venue" = $2
              AND "market" = $3
              AND "mode" = $4
              AND "status" = 'open'
            ORDER BY "updatedAt" DESC, "symbol" ASC
            ''',
            user_id,
            venue_name,
            market,
            mode,
        )
        positions = [_serialize_position_row(row) for row in rows]
        return ReconciliationResult(
            positions=positions,
            source=source,
            reconciled_at=reconciled_at,
            warnings=warnings,
            changes=changes,
            is_paper=is_paper,
        )
    finally:
        await conn.close()
