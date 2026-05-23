"""Market-data persistence primitives.

PostgreSQL is the primary store in production; an in-memory fallback keeps
tests lightweight and lets the app degrade gracefully if the DB is missing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("quantatraderai.market.store")


def utc_dt(value: int | float | datetime | None) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    ts = float(value or 0)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def utc_ts(value: datetime | int | float | None) -> int:
    if value is None:
        return 0
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())
    return int(value)


@dataclass(frozen=True)
class MarketCandleRow:
    venue: str
    asset_class: str
    symbol: str
    timeframe: str
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "venue": self.venue,
            "asset_class": self.asset_class,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "time": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source,
        }


class MarketDataStore:
    async def upsert_candles(self, candles: list[MarketCandleRow]) -> int:
        raise NotImplementedError

    async def get_candles(
        self,
        *,
        venue: str,
        symbol: str,
        timeframe: str,
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_latest_candle(self, *, venue: str, symbol: str, timeframe: str) -> dict[str, Any] | None:
        rows = await self.get_candles(venue=venue, symbol=symbol, timeframe=timeframe, limit=1)
        return rows[-1] if rows else None

    async def upsert_indicator_snapshot(
        self,
        *,
        venue: str,
        asset_class: str,
        symbol: str,
        timeframe: str,
        timestamp: int,
        indicators: dict[str, Any],
    ) -> bool:
        raise NotImplementedError

    async def get_indicator_snapshot(
        self,
        *,
        venue: str,
        symbol: str,
        timeframe: str,
        timestamp: int | None = None,
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    async def upsert_backfill_job(
        self,
        *,
        venue: str,
        asset_class: str,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
        status: str,
        last_fetched_ts: int | None = None,
        error_message: str | None = None,
        source: str | None = None,
        live_sync: bool = False,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def get_backfill_job(self, *, venue: str, symbol: str, timeframe: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def list_active_backfill_jobs(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class InMemoryMarketDataStore(MarketDataStore):
    def __init__(self) -> None:
        self._candles: dict[tuple[str, str, str], dict[int, dict[str, Any]]] = {}
        self._indicators: dict[tuple[str, str, str, int], dict[str, Any]] = {}
        self._jobs: dict[tuple[str, str, str], dict[str, Any]] = {}

    async def upsert_candles(self, candles: list[MarketCandleRow]) -> int:
        for candle in candles:
            key = (candle.venue, candle.symbol, candle.timeframe)
            bucket = self._candles.setdefault(key, {})
            bucket[candle.timestamp] = candle.as_dict()
        return len(candles)

    async def get_candles(
        self,
        *,
        venue: str,
        symbol: str,
        timeframe: str,
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        items = list(self._candles.get((venue, symbol, timeframe), {}).values())
        items.sort(key=lambda item: int(item.get("time") or 0))
        if start_ts is not None:
            items = [item for item in items if int(item.get("time") or 0) >= start_ts]
        if end_ts is not None:
            items = [item for item in items if int(item.get("time") or 0) <= end_ts]
        if limit is not None and limit > 0:
            items = items[-limit:]
        return [dict(item) for item in items]

    async def upsert_indicator_snapshot(
        self,
        *,
        venue: str,
        asset_class: str,
        symbol: str,
        timeframe: str,
        timestamp: int,
        indicators: dict[str, Any],
    ) -> bool:
        self._indicators[(venue, symbol, timeframe, timestamp)] = {
            "venue": venue,
            "asset_class": asset_class,
            "symbol": symbol,
            "timeframe": timeframe,
            "time": timestamp,
            "indicators": json.loads(json.dumps(indicators)),
        }
        return True

    async def get_indicator_snapshot(
        self,
        *,
        venue: str,
        symbol: str,
        timeframe: str,
        timestamp: int | None = None,
    ) -> dict[str, Any] | None:
        candidates = [
            value for (v, s, tf, ts), value in self._indicators.items()
            if v == venue and s == symbol and tf == timeframe and (timestamp is None or ts == timestamp)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: int(item.get("time") or 0))
        return dict(candidates[-1])

    async def upsert_backfill_job(
        self,
        *,
        venue: str,
        asset_class: str,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
        status: str,
        last_fetched_ts: int | None = None,
        error_message: str | None = None,
        source: str | None = None,
        live_sync: bool = False,
    ) -> dict[str, Any]:
        key = (venue, symbol, timeframe)
        existing = self._jobs.get(key) or {"id": str(uuid.uuid4())}
        existing.update({
            "venue": venue,
            "asset_class": asset_class,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "status": status,
            "last_fetched_ts": last_fetched_ts,
            "error_message": error_message,
            "source": source,
            "live_sync": live_sync,
            "updated_at": int(datetime.now(timezone.utc).timestamp()),
        })
        self._jobs[key] = existing
        return dict(existing)

    async def get_backfill_job(self, *, venue: str, symbol: str, timeframe: str) -> dict[str, Any] | None:
        row = self._jobs.get((venue, symbol, timeframe))
        return dict(row) if row else None

    async def list_active_backfill_jobs(self) -> list[dict[str, Any]]:
        rows = [dict(row) for row in self._jobs.values() if row.get("status") in {"pending", "running", "live"}]
        rows.sort(key=lambda row: int(row.get("updated_at") or 0), reverse=True)
        return rows


class PostgresMarketDataStore(MarketDataStore):
    def __init__(self) -> None:
        self._db_url = os.getenv("DATABASE_URL", "")
        if not self._db_url:
            raise RuntimeError("DATABASE_URL env var is not set")
        self._pool = None
        self._lock = asyncio.Lock()

    async def _get_pool(self):
        if self._pool is not None:
            return self._pool
        async with self._lock:
            if self._pool is not None:
                return self._pool
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self._db_url,
                min_size=1,
                max_size=6,
                command_timeout=15,
                statement_cache_size=0,
                max_inactive_connection_lifetime=300,
            )
            return self._pool

    async def upsert_candles(self, candles: list[MarketCandleRow]) -> int:
        if not candles:
            return 0
        pool = await self._get_pool()
        query = """
            INSERT INTO "MarketCandle"
                ("id","venue","assetClass","symbol","timeframe","timestamp","open","high","low","close","volume","source","createdAt","updatedAt")
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,NOW(),NOW())
            ON CONFLICT ("venue","symbol","timeframe","timestamp") DO UPDATE SET
                "assetClass" = EXCLUDED."assetClass",
                "open" = EXCLUDED."open",
                "high" = EXCLUDED."high",
                "low" = EXCLUDED."low",
                "close" = EXCLUDED."close",
                "volume" = EXCLUDED."volume",
                "source" = EXCLUDED."source",
                "updatedAt" = NOW()
        """
        rows = [
            (
                str(uuid.uuid4()),
                candle.venue,
                candle.asset_class,
                candle.symbol,
                candle.timeframe,
                utc_dt(candle.timestamp),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.source,
            )
            for candle in candles
        ]
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(query, rows)
        return len(rows)

    async def get_candles(
        self,
        *,
        venue: str,
        symbol: str,
        timeframe: str,
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        clauses = ['"venue" = $1', '"symbol" = $2', '"timeframe" = $3']
        params: list[Any] = [venue, symbol, timeframe]
        if start_ts is not None:
            params.append(utc_dt(start_ts))
            clauses.append(f'"timestamp" >= ${len(params)}')
        if end_ts is not None:
            params.append(utc_dt(end_ts))
            clauses.append(f'"timestamp" <= ${len(params)}')
        sql = (
            'SELECT "venue","assetClass","symbol","timeframe","timestamp","open","high","low","close","volume","source" '
            'FROM "MarketCandle" '
            f'WHERE {" AND ".join(clauses)} '
            'ORDER BY "timestamp" ASC'
        )
        if limit is not None and limit > 0:
            params.append(limit)
            sql += f' LIMIT ${len(params)}'
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [
            {
                "venue": row["venue"],
                "asset_class": row["assetClass"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "time": utc_ts(row["timestamp"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "source": row["source"],
            }
            for row in rows
        ]

    async def upsert_indicator_snapshot(
        self,
        *,
        venue: str,
        asset_class: str,
        symbol: str,
        timeframe: str,
        timestamp: int,
        indicators: dict[str, Any],
    ) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO "MarketIndicatorSnapshot"
                    ("id","venue","assetClass","symbol","timeframe","timestamp","indicatorsJson","createdAt")
                VALUES ($1,$2,$3,$4,$5,$6,$7,NOW())
                ON CONFLICT ("venue","symbol","timeframe","timestamp") DO UPDATE SET
                    "assetClass" = EXCLUDED."assetClass",
                    "indicatorsJson" = EXCLUDED."indicatorsJson"
                """,
                str(uuid.uuid4()),
                venue,
                asset_class,
                symbol,
                timeframe,
                utc_dt(timestamp),
                json.dumps(indicators),
            )
        return True

    async def get_indicator_snapshot(
        self,
        *,
        venue: str,
        symbol: str,
        timeframe: str,
        timestamp: int | None = None,
    ) -> dict[str, Any] | None:
        pool = await self._get_pool()
        if timestamp is None:
            sql = (
                'SELECT "venue","assetClass","symbol","timeframe","timestamp","indicatorsJson" '
                'FROM "MarketIndicatorSnapshot" '
                'WHERE "venue" = $1 AND "symbol" = $2 AND "timeframe" = $3 '
                'ORDER BY "timestamp" DESC LIMIT 1'
            )
            params = (venue, symbol, timeframe)
        else:
            sql = (
                'SELECT "venue","assetClass","symbol","timeframe","timestamp","indicatorsJson" '
                'FROM "MarketIndicatorSnapshot" '
                'WHERE "venue" = $1 AND "symbol" = $2 AND "timeframe" = $3 AND "timestamp" = $4 '
                'LIMIT 1'
            )
            params = (venue, symbol, timeframe, utc_dt(timestamp))
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
        if not row:
            return None
        return {
            "venue": row["venue"],
            "asset_class": row["assetClass"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "time": utc_ts(row["timestamp"]),
            "indicators": json.loads(str(row["indicatorsJson"])),
        }

    async def upsert_backfill_job(
        self,
        *,
        venue: str,
        asset_class: str,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
        status: str,
        last_fetched_ts: int | None = None,
        error_message: str | None = None,
        source: str | None = None,
        live_sync: bool = False,
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO "MarketDataBackfillJob"
                    ("id","venue","assetClass","symbol","timeframe","startDate","endDate","status","lastFetchedAt","errorMessage","source","isLiveSync","createdAt","updatedAt")
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,NOW(),NOW())
                ON CONFLICT ("venue","symbol","timeframe") DO UPDATE SET
                    "assetClass" = EXCLUDED."assetClass",
                    "startDate" = EXCLUDED."startDate",
                    "endDate" = EXCLUDED."endDate",
                    "status" = EXCLUDED."status",
                    "lastFetchedAt" = EXCLUDED."lastFetchedAt",
                    "errorMessage" = EXCLUDED."errorMessage",
                    "source" = EXCLUDED."source",
                    "isLiveSync" = EXCLUDED."isLiveSync",
                    "updatedAt" = NOW()
                RETURNING "id","venue","assetClass","symbol","timeframe","startDate","endDate","status","lastFetchedAt","errorMessage","source","isLiveSync","updatedAt"
                """,
                str(uuid.uuid4()),
                venue,
                asset_class,
                symbol,
                timeframe,
                utc_dt(start_ts),
                utc_dt(end_ts),
                status,
                utc_dt(last_fetched_ts) if last_fetched_ts else None,
                error_message,
                source,
                live_sync,
            )
        return {
            "id": row["id"],
            "venue": row["venue"],
            "asset_class": row["assetClass"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "start_ts": utc_ts(row["startDate"]),
            "end_ts": utc_ts(row["endDate"]),
            "status": row["status"],
            "last_fetched_ts": utc_ts(row["lastFetchedAt"]) if row["lastFetchedAt"] else None,
            "error_message": row["errorMessage"],
            "source": row["source"],
            "live_sync": bool(row["isLiveSync"]),
            "updated_at": utc_ts(row["updatedAt"]),
        }

    async def get_backfill_job(self, *, venue: str, symbol: str, timeframe: str) -> dict[str, Any] | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT "id","venue","assetClass","symbol","timeframe","startDate","endDate","status","lastFetchedAt","errorMessage","source","isLiveSync","updatedAt"
                FROM "MarketDataBackfillJob"
                WHERE "venue" = $1 AND "symbol" = $2 AND "timeframe" = $3
                LIMIT 1
                """,
                venue,
                symbol,
                timeframe,
            )
        if not row:
            return None
        return {
            "id": row["id"],
            "venue": row["venue"],
            "asset_class": row["assetClass"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "start_ts": utc_ts(row["startDate"]),
            "end_ts": utc_ts(row["endDate"]),
            "status": row["status"],
            "last_fetched_ts": utc_ts(row["lastFetchedAt"]) if row["lastFetchedAt"] else None,
            "error_message": row["errorMessage"],
            "source": row["source"],
            "live_sync": bool(row["isLiveSync"]),
            "updated_at": utc_ts(row["updatedAt"]),
        }

    async def list_active_backfill_jobs(self) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT "id","venue","assetClass","symbol","timeframe","startDate","endDate","status","lastFetchedAt","errorMessage","source","isLiveSync","updatedAt"
                FROM "MarketDataBackfillJob"
                WHERE "status" IN ('pending','running','live')
                ORDER BY "updatedAt" DESC
                """
            )
        return [
            {
                "id": row["id"],
                "venue": row["venue"],
                "asset_class": row["assetClass"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "start_ts": utc_ts(row["startDate"]),
                "end_ts": utc_ts(row["endDate"]),
                "status": row["status"],
                "last_fetched_ts": utc_ts(row["lastFetchedAt"]) if row["lastFetchedAt"] else None,
                "error_message": row["errorMessage"],
                "source": row["source"],
                "live_sync": bool(row["isLiveSync"]),
                "updated_at": utc_ts(row["updatedAt"]),
            }
            for row in rows
        ]


_store_lock = asyncio.Lock()
_store: MarketDataStore | None = None


async def get_market_data_store() -> MarketDataStore:
    global _store
    if _store is not None:
        return _store
    async with _store_lock:
        if _store is not None:
            return _store
        try:
            if os.getenv("DATABASE_URL"):
                _store = PostgresMarketDataStore()
            else:
                _store = InMemoryMarketDataStore()
        except Exception as exc:
            logger.warning("Falling back to in-memory market store: %s", exc)
            _store = InMemoryMarketDataStore()
        return _store


def set_market_data_store(store: MarketDataStore | None) -> None:
    global _store
    _store = store
