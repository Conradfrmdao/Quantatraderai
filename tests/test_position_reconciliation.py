from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.position_reconciliation import (
    _normalize_live_positions,
    _normalize_paper_positions,
    reconcile_positions,
)
from src.venues.models import Position


def test_normalize_paper_positions_merges_duplicate_symbols():
    runtime = {
        "paper_positions": [
            {"symbol": "BTC/USDT", "quantity": 0.10, "entry_price": 60000.0, "current_price": 61000.0, "unrealized_pnl": 100.0},
            {"symbol": "BTC/USDT", "quantity": 0.05, "entry_price": 62000.0, "current_price": 61000.0, "unrealized_pnl": -50.0},
        ],
        "price_cache": {"BTCUSDT": 61000.0},
    }
    warnings: list[str] = []

    normalized = _normalize_paper_positions(runtime, warnings)

    assert len(normalized) == 1
    assert normalized[0]["symbol"] == "BTC/USDT"
    assert normalized[0]["quantity"] == pytest.approx(0.15)
    assert normalized[0]["current_price"] == pytest.approx(61000.0)
    assert warnings == ["Duplicate position snapshot merged for BTC/USDT."]


def test_normalize_live_positions_merges_duplicate_snapshots():
    runtime = {"venue_name": "binance", "price_cache": {"BTCUSDT": 62500.0}}
    warnings: list[str] = []
    raw_positions = [
        Position(symbol="BTC/USDT", quantity=0.08, entry_price=60000.0, unrealized_pnl=120.0, current_price=62500.0),
        Position(symbol="BTC/USDT", quantity=0.02, entry_price=61000.0, unrealized_pnl=30.0, current_price=62500.0),
    ]

    normalized = _normalize_live_positions(runtime, raw_positions, warnings)

    assert len(normalized) == 1
    assert normalized[0]["quantity"] == pytest.approx(0.10)
    assert normalized[0]["source"] == "binance"
    assert warnings == ["Duplicate position snapshot merged for BTC/USDT."]


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self):
        self.positions: list[dict] = []

    async def close(self):
        return None

    def transaction(self):
        return _FakeTransaction()

    async def fetchrow(self, query: str, *params):
        if 'SELECT id FROM "User"' in query:
            return {"id": "db_user"} if params[0] == "clerk_user" else None

        if 'INSERT INTO "Position"' in query:
            (
                row_id,
                user_id,
                venue,
                asset_class,
                market,
                mode,
                symbol,
                side,
                quantity,
                entry_price,
                current_price,
                realized_pnl,
                unrealized_pnl,
                leverage,
                liquidation_price,
                source,
                external_position_id,
                trace_id,
                opened_at,
                synced_at,
            ) = params
            key = (user_id, venue, symbol, market, mode)
            existing = next(
                (row for row in self.positions if (row["userId"], row["venue"], row["symbol"], row["market"], row["mode"]) == key),
                None,
            )
            if existing is None:
                row = {
                    "id": row_id,
                    "userId": user_id,
                    "venue": venue,
                    "assetClass": asset_class,
                    "market": market,
                    "mode": mode,
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "entryPrice": entry_price,
                    "currentPrice": current_price,
                    "realizedPnl": realized_pnl,
                    "unrealizedPnl": unrealized_pnl,
                    "leverage": leverage,
                    "liquidationPrice": liquidation_price,
                    "source": source,
                    "externalPositionId": external_position_id,
                    "traceId": trace_id,
                    "status": "open",
                    "openedAt": opened_at,
                    "closedAt": None,
                    "lastSyncedAt": synced_at,
                    "createdAt": synced_at,
                    "updatedAt": synced_at,
                }
                self.positions.append(row)
                return deepcopy(row)

            existing.update({
                "assetClass": asset_class,
                "side": side,
                "quantity": quantity,
                "entryPrice": entry_price,
                "currentPrice": current_price,
                "unrealizedPnl": unrealized_pnl,
                "leverage": leverage,
                "liquidationPrice": liquidation_price,
                "source": source,
                "externalPositionId": external_position_id,
                "traceId": trace_id,
                "status": "open",
                "closedAt": None,
                "lastSyncedAt": synced_at,
                "updatedAt": synced_at,
            })
            if existing.get("openedAt") is None:
                existing["openedAt"] = opened_at
            return deepcopy(existing)

        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def fetch(self, query: str, *params):
        if (
            'FROM "Position"' in query
            and 'WHERE "userId" = $1' in query
            and 'AND "venue" = $2' in query
            and 'AND "market" = $3' in query
            and 'AND "mode" = $4' in query
        ):
            user_id, venue, market, mode = params[:4]
            rows = [row for row in self.positions if row["userId"] == user_id and row["venue"] == venue and row["market"] == market and row["mode"] == mode]
            if 'AND "status" = \'open\'' in query:
                rows = [row for row in rows if row["status"] == "open"]
            return [deepcopy(row) for row in rows]

        if 'UPDATE "Position"' in query and 'SET "status" = \'closed\'' in query:
            user_id, venue, market, mode, trace_id, source = params[:6]
            active_symbols = list(params[6]) if len(params) > 6 else None
            closed = []
            now = datetime.now(timezone.utc)
            for row in self.positions:
                if row["userId"] != user_id or row["venue"] != venue or row["market"] != market or row["mode"] != mode:
                    continue
                if row["status"] != "open":
                    continue
                if active_symbols is not None and row["symbol"] in active_symbols:
                    continue
                row["status"] = "closed"
                row["closedAt"] = row["closedAt"] or now
                row["traceId"] = trace_id
                row["source"] = source
                row["realizedPnl"] = float(row.get("realizedPnl") or 0.0) + float(row.get("unrealizedPnl") or 0.0)
                row["unrealizedPnl"] = 0.0
                row["lastSyncedAt"] = now
                row["updatedAt"] = now
                closed.append(deepcopy(row))
            return closed

        raise AssertionError(f"Unexpected fetch query: {query}")


@pytest.mark.asyncio
async def test_reconcile_positions_upserts_updates_and_closes_rows():
    conn = _FakeConn()

    class StubVenue:
        def __init__(self):
            self.positions = [Position(symbol="BTC/USDT", quantity=0.10, entry_price=60000.0, unrealized_pnl=200.0, current_price=62000.0)]

        async def get_positions(self):
            return list(self.positions)

    venue = StubVenue()
    runtime = {"venue_name": "binance", "market": "spot", "is_paper": False, "venue": venue}

    with patch("src.services.position_reconciliation._connect", AsyncMock(return_value=conn)):
        opened = await reconcile_positions("clerk_user", runtime, "live", "test_open", "trace-open")
        venue.positions = [Position(symbol="BTC/USDT", quantity=0.10, entry_price=60000.0, unrealized_pnl=350.0, current_price=63500.0)]
        updated = await reconcile_positions("clerk_user", runtime, "live", "test_update", "trace-update")
        venue.positions = []
        closed = await reconcile_positions("clerk_user", runtime, "live", "test_close", "trace-close")

    assert [change["type"] for change in opened.changes] == ["position_opened"]
    assert any(change["type"] == "position_updated" for change in updated.changes)
    assert any(change["type"] == "position_closed" for change in closed.changes)
    assert closed.positions == []
    assert conn.positions[0]["status"] == "closed"


@pytest.mark.asyncio
async def test_reconcile_positions_falls_back_to_cached_rows_when_source_fetch_fails():
    class FailingVenue:
        async def get_positions(self):
            raise RuntimeError("venue offline")

    runtime = {"venue_name": "binance", "market": "spot", "is_paper": False, "venue": FailingVenue()}
    cached = [{"symbol": "BTC/USDT", "quantity": 0.1}]

    with patch("src.services.position_reconciliation.list_positions", AsyncMock(return_value=cached)):
        result = await reconcile_positions("clerk_user", runtime, "live", "fallback", "trace-fallback")

    assert result.positions == cached
    assert result.warnings
    assert "skipped" in result.warnings[0].lower()
