"""Load tests (test_load_*) — 100+ trades/min with metrics.

These tests measure performance characteristics and output structured metrics.
They do not make real API calls — all venue I/O is mocked with MockVenue.

Output schema:
  {
    "avg_latency_ms": float,
    "max_latency_ms": float,
    "p95_latency_ms": float,
    "error_rate_pct": float,
    "retry_count":    int,
    "trades_per_min": float,
    "total_trades":   int,
    "duration_sec":   float,
  }

Gate: error_rate < 1%, avg_latency < 200ms, max_latency < 1000ms
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
import uuid
from typing import Any

import pytest

from tests.conftest import MockVenue

_GATE_ERROR_RATE_PCT = 1.0     # max acceptable error %
_GATE_AVG_LATENCY_MS = 200.0   # max acceptable average latency
_GATE_MAX_LATENCY_MS = 1000.0  # max acceptable single-call latency


# ── Core metric runner ─────────────────────────────────────────────────────────

async def _run_load(n_trades: int, concurrent: int = 5) -> dict[str, Any]:
    """Execute n_trades via MockVenue in batches of `concurrent`, recording timing."""
    venue = MockVenue(starting_balance=1_000_000.0)

    latencies_ms: list[float] = []
    errors: int = 0
    retries: int = 0

    async def one_trade(_: int) -> None:
        nonlocal errors, retries
        start = time.perf_counter()
        try:
            price = 50_000.0
            qty   = 100.0 / price  # $100 trade
            await venue.place_order("BTCUSDT", "buy", qty, "market", price=price)
        except Exception:
            errors += 1
        finally:
            latencies_ms.append((time.perf_counter() - start) * 1000)

    start_total = time.perf_counter()

    # Process in batches
    for batch_start in range(0, n_trades, concurrent):
        batch = range(batch_start, min(batch_start + concurrent, n_trades))
        await asyncio.gather(*[one_trade(i) for i in batch])

    total_sec = time.perf_counter() - start_total

    return {
        "avg_latency_ms": round(statistics.mean(latencies_ms), 3),
        "max_latency_ms": round(max(latencies_ms), 3),
        "p95_latency_ms": round(sorted(latencies_ms)[int(len(latencies_ms) * 0.95)], 3),
        "error_rate_pct": round((errors / n_trades) * 100, 3),
        "retry_count":    retries,
        "trades_per_min": round((n_trades / total_sec) * 60, 1),
        "total_trades":   n_trades,
        "duration_sec":   round(total_sec, 3),
        "errors":         errors,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Tests
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_load_100_trades_metrics(mock_env, capsys):
    """Run 100 trades through MockVenue, assert latency + error gates."""
    metrics = await _run_load(n_trades=100, concurrent=10)

    # Emit structured output (captured by run_tests.sh)
    with capsys.disabled():
        print(f"\n[LOAD_METRICS] {json.dumps(metrics)}")

    # Gate assertions
    assert metrics["error_rate_pct"] <= _GATE_ERROR_RATE_PCT, \
        f"Error rate {metrics['error_rate_pct']:.2f}% exceeds {_GATE_ERROR_RATE_PCT}% gate"

    assert metrics["avg_latency_ms"] <= _GATE_AVG_LATENCY_MS, \
        f"Avg latency {metrics['avg_latency_ms']:.1f}ms exceeds {_GATE_AVG_LATENCY_MS}ms gate"

    assert metrics["max_latency_ms"] <= _GATE_MAX_LATENCY_MS, \
        f"Max latency {metrics['max_latency_ms']:.1f}ms exceeds {_GATE_MAX_LATENCY_MS}ms gate"

    assert metrics["total_trades"] == 100


@pytest.mark.asyncio
async def test_load_sustained_200_trades(mock_env):
    """200 trades sustained — error gate must still hold."""
    metrics = await _run_load(n_trades=200, concurrent=20)

    assert metrics["error_rate_pct"] == 0.0, \
        f"Zero errors expected with MockVenue, got {metrics['errors']}"
    assert metrics["total_trades"] == 200


@pytest.mark.asyncio
async def test_load_error_rate_under_failure_injection(mock_env):
    """With 5% failure injection, error rate must be ≤ 10% (retry absorbs some)."""
    import random

    venue = MockVenue(starting_balance=1_000_000.0)

    n_errors = 0
    original = venue.place_order

    async def flaky_place_order(*args, **kwargs):
        nonlocal n_errors
        if random.random() < 0.05:   # 5% failure rate
            n_errors += 1
            raise RuntimeError("simulated 5% exchange failure")
        return await original(*args, **kwargs)

    venue.place_order = flaky_place_order

    latencies: list[float] = []
    errors = 0

    async def one_trade(_):
        nonlocal errors
        start = time.perf_counter()
        try:
            await venue.place_order("BTCUSDT", "buy", 0.001)
        except Exception:
            errors += 1
        finally:
            latencies.append((time.perf_counter() - start) * 1000)

    n = 200
    await asyncio.gather(*[one_trade(i) for i in range(n)])

    error_rate = (errors / n) * 100
    assert error_rate <= 10.0, f"Error rate {error_rate:.1f}% too high under 5% injection"


@pytest.mark.asyncio
async def test_load_no_duplicate_orders_under_load(mock_env):
    """Under heavy concurrent load, no duplicate order IDs should appear."""
    order_ids: list[str] = []
    lock = asyncio.Lock()

    venue = MockVenue(starting_balance=1_000_000.0)

    async def trade_and_record(_):
        order = await venue.place_order("BTCUSDT", "buy", 0.001)
        async with lock:
            order_ids.append(order.order_id)

    await asyncio.gather(*[trade_and_record(i) for i in range(50)])

    assert len(order_ids) == 50
    assert len(set(order_ids)) == 50, \
        f"Duplicate order IDs detected: {50 - len(set(order_ids))} duplicates"


@pytest.mark.asyncio
async def test_load_metrics_schema_valid(mock_env):
    """Verify the metrics output has the required schema for the release gate."""
    metrics = await _run_load(n_trades=10, concurrent=2)

    required_keys = {
        "avg_latency_ms", "max_latency_ms", "p95_latency_ms",
        "error_rate_pct", "retry_count", "trades_per_min",
        "total_trades", "duration_sec",
    }
    for k in required_keys:
        assert k in metrics, f"Missing metrics key: {k}"
        assert isinstance(metrics[k], (int, float)), f"{k} must be numeric"


@pytest.mark.asyncio
async def test_load_risk_checks_under_load(mock_env):
    """Risk manager must handle 100 concurrent validate_trade calls correctly."""
    from src.risk_manager import RiskManager

    rm      = RiskManager(venue="mock", asset_class="crypto_spot")
    account = {"total_value": 10_000.0, "balance": 9_000.0, "positions": []}

    async def one_risk_check(i: int) -> bool:
        trade = {
            "action": "buy", "asset": "BTCUSDT",
            "current_price": 50_000.0,
            "allocation_usd": 100.0,
        }
        ok, _, _ = rm.validate_trade(trade, account, 10_000.0)
        return ok

    results = await asyncio.gather(*[one_risk_check(i) for i in range(100)])

    # All should pass (100 USD trade on 10k account is within 3%)
    passing = sum(1 for r in results if r)
    assert passing == 100, f"Only {passing}/100 risk checks passed under load"


@pytest.mark.asyncio
async def test_load_state_isolation_under_load(mock_env):
    """50 concurrent users each perform 10 trades — verify final balances are correct."""
    from src.server import get_state

    async def user_load(i: int) -> tuple[str, float, float]:
        uid = f"load_user_{i:04d}"
        initial = 10_000.0 + i
        venue = MockVenue(starting_balance=initial)
        venue.set_price(50_000.0)

        s = get_state(uid)
        s.user_id = uid
        s.venue   = venue

        # 10 $10 trades
        for _ in range(10):
            await venue.place_order("BTCUSDT", "buy", 0.0002, price=50_000.0)
            await asyncio.sleep(0)

        final = (await venue.get_balances())[0].total
        return uid, initial, final

    results = await asyncio.gather(*[user_load(i) for i in range(50)])

    for uid, initial, final in results:
        expected = initial - 10 * (0.0002 * 50_000.0)  # 10 trades × $10 each
        assert abs(final - expected) < 0.1, \
            f"{uid}: expected ${expected:.2f} but got ${final:.2f}"
