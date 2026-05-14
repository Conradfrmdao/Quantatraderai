"""Distributed-friendly AI rate limiting and reservation counters."""

from __future__ import annotations

import asyncio
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiohttp

from src.ai.budgets import current_budget_periods


def _is_local_env() -> bool:
    return os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower() in {"local", "development", "dev", "test"}


@dataclass(frozen=True)
class LimitResult:
    allowed: bool
    current: int
    limit: int
    retry_after_seconds: int


class CounterStore:
    async def incr(self, key: str, amount: int, ttl_s: int) -> int:
        raise NotImplementedError

    async def get(self, key: str) -> int:
        raise NotImplementedError


class InMemoryCounterStore(CounterStore):
    def __init__(self) -> None:
        self._values: dict[str, tuple[int, float]] = {}

    async def incr(self, key: str, amount: int, ttl_s: int) -> int:
        now = time.time()
        current, expires_at = self._values.get(key, (0, now + ttl_s))
        if expires_at <= now:
            current, expires_at = 0, now + ttl_s
        current = max(0, current + amount)
        self._values[key] = (current, expires_at)
        return current

    async def get(self, key: str) -> int:
        now = time.time()
        current, expires_at = self._values.get(key, (0, now))
        if expires_at <= now:
            self._values.pop(key, None)
            return 0
        return current


class UpstashCounterStore(CounterStore):
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    async def _pipeline(self, commands: list[list[str]]) -> list[object]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/pipeline",
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                json=commands,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                resp.raise_for_status()
                payload = await resp.json()
        results: list[object] = []
        for item in payload:
            if isinstance(item, dict) and "result" in item:
                results.append(item["result"])
            else:
                results.append(item)
        return results

    async def incr(self, key: str, amount: int, ttl_s: int) -> int:
        ttl = max(1, int(ttl_s))
        results = await self._pipeline([
            ["INCRBY", key, str(amount)],
            ["EXPIRE", key, str(ttl)],
        ])
        return int(results[0] or 0)

    async def get(self, key: str) -> int:
        results = await self._pipeline([["GET", key]])
        value = results[0]
        return int(value or 0)


class RedisUrlCounterStore(CounterStore):
    def __init__(self, url: str) -> None:
        self.url = url
        self._client = None

    async def _client_or_init(self):
        if self._client is None:
            import redis.asyncio as redis

            self._client = redis.from_url(self.url, decode_responses=True)
        return self._client

    async def incr(self, key: str, amount: int, ttl_s: int) -> int:
        client = await self._client_or_init()
        async with client.pipeline(transaction=True) as pipe:
            pipe.incrby(key, amount)
            pipe.expire(key, max(1, int(ttl_s)))
            result = await pipe.execute()
        return int(result[0] or 0)

    async def get(self, key: str) -> int:
        client = await self._client_or_init()
        value = await client.get(key)
        return int(value or 0)


class PostgresCounterStore(CounterStore):
    def __init__(self, url: str) -> None:
        self.url = url
        self._pool = None

    async def _pool_or_init(self):
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(self.url, min_size=1, max_size=5, timeout=5)
        return self._pool

    async def incr(self, key: str, amount: int, ttl_s: int) -> int:
        pool = await self._pool_or_init()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(1, int(ttl_s)))
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO "RuntimeCounter" ("id","value","expiresAt","updatedAt")
                VALUES ($1,$2,$3,NOW())
                ON CONFLICT ("id") DO UPDATE SET
                    "value" = CASE
                        WHEN "RuntimeCounter"."expiresAt" <= NOW()
                            THEN GREATEST(0, EXCLUDED."value")
                        ELSE GREATEST(0, "RuntimeCounter"."value" + EXCLUDED."value")
                    END,
                    "expiresAt" = CASE
                        WHEN "RuntimeCounter"."expiresAt" <= NOW()
                            THEN EXCLUDED."expiresAt"
                        ELSE GREATEST("RuntimeCounter"."expiresAt", EXCLUDED."expiresAt")
                    END,
                    "updatedAt" = NOW()
                RETURNING "value"
                """,
                key,
                int(amount),
                expires_at,
            )
        return int(row["value"] if row else 0)

    async def get(self, key: str) -> int:
        pool = await self._pool_or_init()
        async with pool.acquire() as conn:
            await conn.execute('DELETE FROM "RuntimeCounter" WHERE "id" = $1 AND "expiresAt" <= NOW()', key)
            row = await conn.fetchrow('SELECT "value" FROM "RuntimeCounter" WHERE "id" = $1', key)
        return int(row["value"] if row else 0)


_STORE: CounterStore | None = None


def get_counter_store() -> CounterStore | None:
    global _STORE
    if _STORE is not None:
        return _STORE

    upstash_url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
    upstash_token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
    if upstash_url and upstash_token:
        _STORE = UpstashCounterStore(upstash_url, upstash_token)
        return _STORE

    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            _STORE = RedisUrlCounterStore(redis_url)
            return _STORE
        except Exception:
            _STORE = None

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        try:
            _STORE = PostgresCounterStore(database_url)
            return _STORE
        except Exception:
            _STORE = None

    if _is_local_env():
        _STORE = InMemoryCounterStore()
        return _STORE

    return None


def counter_store_available() -> bool:
    return get_counter_store() is not None


def fixed_window_key(prefix: str, identity: str, window_s: int, now: float | None = None) -> tuple[str, int]:
    ts = now or time.time()
    bucket = int(ts // window_s)
    retry_after = max(1, int(((bucket + 1) * window_s) - ts))
    return f"{prefix}:{identity}:{bucket}", retry_after


async def consume_limit(prefix: str, identity: str, limit: int, window_s: int) -> LimitResult:
    store = get_counter_store()
    if store is None:
        raise RuntimeError("counter_store_unavailable")
    key, retry_after = fixed_window_key(prefix, identity, window_s)
    current = await store.incr(key, 1, retry_after)
    return LimitResult(
        allowed=current <= limit,
        current=current,
        limit=limit,
        retry_after_seconds=retry_after,
    )


async def reserve_counter(prefix: str, identity: str, amount: int, ttl_s: int) -> int:
    store = get_counter_store()
    if store is None:
        raise RuntimeError("counter_store_unavailable")
    return await store.incr(f"{prefix}:{identity}", amount, ttl_s)


async def read_counter(prefix: str, identity: str) -> int:
    store = get_counter_store()
    if store is None:
        raise RuntimeError("counter_store_unavailable")
    return await store.get(f"{prefix}:{identity}")


def ttl_until_end_of_day() -> int:
    now = time.time()
    return max(60, int(math.ceil(((int(now // 86400) + 1) * 86400) - now)))


def ttl_until_end_of_month() -> int:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    first_of_next_month = (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1)
    return max(60, int((first_of_next_month - now).total_seconds()))
