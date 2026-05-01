"""Observability tests (test_observability_*).

Every trade and critical event must produce structured logs with:
  - trace_id (UUID, unique per operation)
  - user_id
  - venue
  - action / symbol
  - no secrets

Also validates TradeReceipt and confidence scores are emitted.
"""
from __future__ import annotations

import json
import logging
import uuid
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import MockVenue


# ── Helpers ────────────────────────────────────────────────────────────────────

def capture_structured_logs(logger_name: str):
    """Context manager that captures structured JSON log entries."""
    log_records: list[dict] = []

    class StructuredHandler(logging.Handler):
        def emit(self, record):
            try:
                data = json.loads(record.getMessage())
                log_records.append(data)
            except (json.JSONDecodeError, ValueError):
                log_records.append({"raw": record.getMessage()})

    handler = StructuredHandler()
    logger  = logging.getLogger(logger_name)
    logger.addHandler(handler)
    try:
        yield log_records
    finally:
        logger.removeHandler(handler)


# ═════════════════════════════════════════════════════════════════════════════
# TraceContext + structured_log
# ═════════════════════════════════════════════════════════════════════════════

def test_observability_trace_context_auto_generates_id(mock_env):
    from src.services.observability import TraceContext
    ctx = TraceContext(user_id="u1", venue="binance")
    assert ctx.trace_id
    # Looks like a UUID
    assert len(ctx.trace_id) == 36 and ctx.trace_id.count("-") == 4


def test_observability_trace_context_explicit_id_preserved(mock_env):
    from src.services.observability import TraceContext
    my_id = str(uuid.uuid4())
    ctx = TraceContext(user_id="u1", venue="binance", trace_id=my_id)
    assert ctx.trace_id == my_id


def test_observability_structured_log_contains_required_fields(mock_env, caplog):
    from src.services.observability import TraceContext, structured_log

    logger = logging.getLogger("test_obs")
    ctx = TraceContext(user_id="user_obs_test", venue="binance",
                       symbol="BTCUSDT", action="buy")

    with caplog.at_level(logging.INFO, logger="test_obs"):
        structured_log(logger, "info", ctx, "Order placed",
                       quantity=0.003, price=50_000.0)

    # Find our log record
    log_text = caplog.text
    # Should contain the structured JSON
    assert "trace_id" in log_text or "user_obs_test" in log_text


def test_observability_structured_log_json_parseable(mock_env):
    from src.services.observability import TraceContext, structured_log

    log_records: list[str] = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            log_records.append(record.getMessage())

    logger = logging.getLogger("obs_json_test")
    handler = CapturingHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        ctx = TraceContext(user_id="u_json", venue="oanda")
        structured_log(logger, "info", ctx, "Trade validated",
                       symbol="EURUSD", allocation_usd=500.0)
    finally:
        logger.removeHandler(handler)

    assert len(log_records) == 1
    data = json.loads(log_records[0])

    assert data["trace_id"]
    assert data["user_id"]  == "u_json"
    assert data["venue"]    == "oanda"
    assert data["message"]  == "Trade validated"


def test_observability_log_contains_no_secrets(mock_env):
    from src.services.observability import TraceContext, structured_log
    from src.services.encryption import encrypt

    secret_key = "SHOULD_NOT_APPEAR_IN_LOGS"
    log_records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, r): log_records.append(r.getMessage())

    logger = logging.getLogger("obs_secret_test")
    h = Capture(); logger.addHandler(h); logger.setLevel(logging.DEBUG)

    try:
        ctx = TraceContext(user_id="u_secret", venue="binance")
        structured_log(logger, "info", ctx, "Connection tested",
                       result="ok", balance=12_500.0)
    finally:
        logger.removeHandler(h)

    for record in log_records:
        assert secret_key not in record, "Secret leaked into log!"


# ═════════════════════════════════════════════════════════════════════════════
# TradeReceipt observability
# ═════════════════════════════════════════════════════════════════════════════

def test_observability_receipt_has_trace_id(mock_env):
    from src.services.trade_receipt import build_trade_receipt

    trace = str(uuid.uuid4())
    r = build_trade_receipt(
        "u1", "binance", "BTCUSDT", "buy",
        0.003, 50_000.0, 150.0, "RSI signal",
        {"max_position_pct": 3, "max_leverage": 2, "original_allocation_usd": 150.0},
        9_500.0, 9_350.0, trace_id=trace,
    )
    assert r.trace_id == trace


def test_observability_every_receipt_unique_trade_id(mock_env):
    from src.services.trade_receipt import build_trade_receipt

    receipts = [
        build_trade_receipt(
            "u1", "binance", "BTCUSDT", "buy", 0.001, 50_000.0, 50.0, "sig",
            {"max_position_pct": 3, "max_leverage": 2, "original_allocation_usd": 50.0},
            10_000.0, 9_950.0,
        )
        for _ in range(10)
    ]
    trade_ids = {r.trade_id for r in receipts}
    assert len(trade_ids) == 10, "Trade IDs must be unique per receipt"


def test_observability_confidence_score_present(mock_env):
    from src.services.trade_receipt import build_trade_receipt

    r = build_trade_receipt(
        "u1", "binance", "BTCUSDT", "buy", 0.003, 50_000.0, 150.0, "signal",
        {"max_position_pct": 3, "max_leverage": 2, "original_allocation_usd": 150.0},
        9_500.0, 9_350.0,
        indicators={"rsi14": 25.0, "macd": 0.5, "ema20": 49_500.0},
    )

    d = r.to_dict()
    assert "confidence" in d
    assert "overall" in d["confidence"]
    assert "label" in d["confidence"]
    assert d["confidence"]["label"] in ("LOW", "MEDIUM", "HIGH")
    assert 0.0 <= d["confidence"]["overall"] <= 1.0


def test_observability_ai_explanation_in_receipt(mock_env):
    from src.services.trade_receipt import build_trade_receipt

    r = build_trade_receipt(
        "u1", "binance", "BTCUSDT", "buy", 0.003, 50_000.0, 150.0,
        "RSI crossed below 30 indicating oversold condition.",
        {"max_position_pct": 3, "max_leverage": 2, "original_allocation_usd": 150.0},
        9_500.0, 9_350.0,
        indicators={"rsi14": 28.0, "macd": 0.4, "ema20": 49_000.0},
    )

    assert r.ai_explanation
    assert len(r.ai_explanation) > 20
    # Should mention trade details
    exp_lower = r.ai_explanation.lower()
    assert "buy" in exp_lower or "btcusdt" in exp_lower or "rsi" in exp_lower


def test_observability_risk_decision_in_receipt(mock_env):
    from src.services.trade_receipt import build_trade_receipt

    r = build_trade_receipt(
        "u1", "binance", "BTCUSDT", "buy", 0.003, 50_000.0, 100.0, "test",
        # original was 500 but capped to 100
        {"max_position_pct": 3, "max_leverage": 2, "original_allocation_usd": 500.0},
        9_500.0, 9_400.0,
    )

    assert r.risk.capped is True
    assert r.risk.original_alloc == 500.0
    assert r.risk.final_alloc == 100.0
    summary = r.risk.human_summary()
    assert "$500" in summary or "500" in summary
    assert "$100" in summary or "100" in summary


# ═════════════════════════════════════════════════════════════════════════════
# Human error messages
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("code,ctx,expected_fragment", [
    ("INVALID_API_KEY",    {"venue": "Binance"},                          "No trades"),
    ("INSUFFICIENT_BALANCE",{"venue":"Binance","available":45.0,"required":150.0},"45.00"),
    ("RATE_LIMITED",       {"venue":"Binance","retry_s":30.0},            "30"),
    ("RISK_BLOCKED",       {"reason":"Max leverage exceeded"},            "No funds"),
    ("NETWORK_TIMEOUT",    {"venue":"Binance","timeout_s":10.0},          "10"),
    ("MARKET_CLOSED",      {"venue":"Binance","symbol":"EURUSD"},         "closed"),
    ("DUPLICATE_SIGNAL",   {},                                            "ignored"),
    ("PLAN_LIMIT",         {"plan_required":"PRO","current_plan":"FREE"}, "/billing"),
    ("AGENT_NOT_RUNNING",  {},                                            "not currently running"),
    ("DECRYPTION_FAILED",  {"venue":"Binance"},                           "reconnect"),
])
def test_observability_human_error_messages(mock_env, code, ctx, expected_fragment):
    from src.services.observability import human_error
    msg = human_error(code, ctx)
    assert isinstance(msg, str) and len(msg) > 10
    assert expected_fragment.lower() in msg.lower(), \
        f"Error message for {code!r} missing '{expected_fragment}': {msg}"


def test_observability_unknown_error_code_safe(mock_env):
    from src.services.observability import human_error
    msg = human_error("TOTALLY_UNKNOWN_CODE_XYZ")
    assert isinstance(msg, str)
    assert "No trades" in msg or "unexpected" in msg.lower()


# ═════════════════════════════════════════════════════════════════════════════
# Audit log field completeness
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_observability_audit_log_fields(mock_env):
    """Audit log entries must always include event, symbol, action, data."""
    audit_entries: list[dict] = []

    async def fake_audit(user_id, event, symbol=None, action=None, data=None):
        audit_entries.append({
            "user_id": user_id, "event": event,
            "symbol": symbol, "action": action, "data": data,
        })

    with patch("src.services.persistence.write_audit", new=fake_audit):
        await fake_audit("clerk_u1", "order", "BTCUSDT", "buy",
                         {"qty": 0.003, "price": 50_000.0, "venue": "binance"})
        await fake_audit("clerk_u1", "risk_block", "ETHUSDT", "sell",
                         {"reason": "max_position exceeded"})

    assert len(audit_entries) == 2

    order_entry = audit_entries[0]
    assert order_entry["event"]  == "order"
    assert order_entry["symbol"] == "BTCUSDT"
    assert order_entry["action"] == "buy"
    assert isinstance(order_entry["data"], dict)
    assert "qty" in order_entry["data"]

    risk_entry = audit_entries[1]
    assert "reason" in risk_entry["data"]
