from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.position_reconciliation import ReconciliationResult
from src.services.trading_events import (
    TradingEventDeps,
    _TELEGRAM_FAILURES,
    on_agent_stopped,
    on_order_filled,
    on_order_rejected,
    on_risk_blocked,
)


def _deps(*, notify_result: bool | None = True):
    broadcasts: list[tuple[dict, str | None]] = []
    notifier_events = []

    async def _broadcast(payload: dict, ws_user_id: str | None):
        broadcasts.append((payload, ws_user_id))

    async def _emit_notifier(event):
        notifier_events.append(event)

    deps = TradingEventDeps(
        broadcast=_broadcast,
        emit_notifier=_emit_notifier,
        notify_user=AsyncMock(return_value=notify_result),
        persist_audit=AsyncMock(),
        persist_trade=AsyncMock(),
        persist_equity=AsyncMock(),
    )
    return deps, broadcasts, notifier_events


@pytest.mark.asyncio
async def test_on_order_filled_broadcasts_receipt_reconciliation_and_trade_alert():
    deps, broadcasts, notifier_events = _deps()
    reconciliation = ReconciliationResult(
        positions=[{"symbol": "BTC/USDT", "quantity": 0.1, "entry_price": 62000.0, "current_price": 62000.0, "unrealized_pnl": 0.0}],
        source="paper_ledger",
        reconciled_at="2026-05-26T10:00:00+00:00",
        changes=[{"type": "position_opened", "position": {"symbol": "BTC/USDT", "quantity": 0.1}}],
        is_paper=True,
    )
    runtime = {"venue_name": "binance", "market": "spot", "is_paper": True}

    with patch("src.services.trading_events.reconcile_positions", AsyncMock(return_value=reconciliation)):
        with patch("src.services.trading_events.write_trade_receipt", AsyncMock(return_value="trade_1")) as write_receipt:
            with patch("src.services.trading_events._safe_capture_posthog", AsyncMock()):
                result = await on_order_filled(
                    deps,
                    clerk_user_id="clerk_trade_user",
                    ws_user_id="clerk_trade_user",
                    venue_runtime=runtime,
                    symbol="BTC/USDT",
                    action="buy",
                    quantity=0.1,
                    price=62000.0,
                    allocation_usd=6200.0,
                    rationale="Momentum continuation",
                    risk_summary={"max_position_pct": 3, "original_allocation_usd": 6200.0},
                    before_balance=10000.0,
                    after_balance=3800.0,
                    indicators={"rsi14": 40, "macd": 1.2, "ema20": 61000},
                    trace_id="trace-fill-1",
                    source="agent",
                    confidence=0.77,
                    realized_pnl=0.0,
                )

    assert result is reconciliation
    assert [payload["type"] for payload, _ in broadcasts[:3]] == ["order_filled", "trade_executed", "position_opened"]
    assert all(user_id == "clerk_trade_user" for _, user_id in broadcasts)
    assert notifier_events[-1].kind == "trade_opened"
    deps.persist_trade.assert_awaited_once()
    assert deps.persist_trade.await_args.kwargs["pnl"] == 0.0
    write_receipt.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_risk_blocked_is_user_scoped_and_sends_alert():
    deps, broadcasts, notifier_events = _deps()

    with patch("src.services.trading_events._safe_capture_posthog", AsyncMock()):
        await on_risk_blocked(
            deps,
            clerk_user_id="clerk_risk_user",
            ws_user_id="clerk_risk_user",
            venue="binance",
            mode="live",
            symbol="BTC/USDT",
            action="buy",
            trace_id="trace-risk-1",
            reason="Position size exceeds configured max exposure",
            confidence=0.42,
        )

    assert broadcasts == [(
        {
            "type": "risk_blocked",
            "trace_id": "trace-risk-1",
            "symbol": "BTC/USDT",
            "action": "buy",
            "venue": "binance",
            "mode": "live",
            "reason": "Position size exceeds configured max exposure",
            "confidence": 0.42,
        },
        "clerk_risk_user",
    )]
    assert notifier_events[-1].kind == "risk_blocked"
    deps.persist_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_agent_stopped_includes_open_position_message():
    deps, broadcasts, notifier_events = _deps()

    with patch("src.services.trading_events._safe_capture_posthog", AsyncMock()):
        await on_agent_stopped(
            deps,
            clerk_user_id="clerk_stop_user",
            ws_user_id="clerk_stop_user",
            venue="binance",
            mode="live",
            trace_id="trace-stop-1",
            reason="user_stop",
            open_positions_remaining=2,
        )

    assert broadcasts[0][0]["type"] == "agent_stopped"
    assert broadcasts[0][0]["open_positions_remaining"] == 2
    assert "still active" in broadcasts[0][0]["message"]
    assert broadcasts[1][0]["type"] == "status_update"
    assert notifier_events[-1].kind == "agent_stopped"


@pytest.mark.asyncio
async def test_telegram_failures_do_not_break_execution_and_escalate_after_three_attempts():
    deps, broadcasts, notifier_events = _deps(notify_result=False)
    _TELEGRAM_FAILURES.clear()

    with patch("src.services.trading_events._safe_capture_posthog", AsyncMock()):
        with patch("src.services.trading_events.capture_sentry_exception", MagicMock()) as sentry_mock:
            for idx in range(3):
                await on_order_rejected(
                    deps,
                    clerk_user_id="clerk_alert_user",
                    ws_user_id="clerk_alert_user",
                    venue="binance",
                    mode="live",
                    symbol="BTC/USDT",
                    action="buy",
                    trace_id=f"trace-reject-{idx}",
                    reason="Exchange temporarily unavailable",
                )

    assert notifier_events[-1].kind == "order_rejected"
    failed_events = [payload for payload, _ in broadcasts if payload["type"] == "telegram_alert_failed"]
    assert len(failed_events) == 3
    assert all(payload["message"] == "Telegram delivery failed. Trading continued safely." for payload in failed_events)
    sentry_mock.assert_called_once()
