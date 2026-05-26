"""Centralized trading lifecycle events for persistence, broadcast, and alerts."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from src.ai.telemetry import capture_posthog, capture_sentry_exception
from src.alerts.notifier import TradingEvent
from src.services.persistence import write_trade_receipt
from src.services.position_reconciliation import ReconciliationResult, list_positions, reconcile_positions
from src.services.trade_receipt import build_trade_receipt

logger = logging.getLogger("quantatraderai.trading_events")

AlertFn = Callable[[TradingEvent], Awaitable[None]]
BroadcastFn = Callable[[dict[str, Any], str | None], Awaitable[None]]
NotifyUserFn = Callable[[str, TradingEvent], Awaitable[bool | None]]
PersistAuditFn = Callable[[str | None, str, str | None, str | None, dict[str, Any] | None], Awaitable[None]]
PersistTradeFn = Callable[..., Awaitable[None]]
PersistEquityFn = Callable[[str, float, float, float, int], Awaitable[None]]

_TELEGRAM_FAILURES: dict[str, list[float]] = {}
_TELEGRAM_FAILURE_WINDOW_S = 600.0


def _runtime_value(runtime: Any, key: str, default: Any = None) -> Any:
    if isinstance(runtime, dict):
        return runtime.get(key, default)
    return getattr(runtime, key, default)


@dataclass
class TradingEventDeps:
    broadcast: BroadcastFn
    emit_notifier: AlertFn
    notify_user: NotifyUserFn
    persist_audit: PersistAuditFn
    persist_trade: PersistTradeFn
    persist_equity: PersistEquityFn | None = None


def _trim_failures(user_id: str) -> list[float]:
    now = time.time()
    recent = [ts for ts in _TELEGRAM_FAILURES.get(user_id, []) if now - ts <= _TELEGRAM_FAILURE_WINDOW_S]
    _TELEGRAM_FAILURES[user_id] = recent
    return recent


async def _safe_capture_posthog(event: str, properties: dict[str, Any]) -> None:
    try:
        await capture_posthog(event, properties)
    except Exception:
        logger.debug("posthog capture skipped for %s", event)


async def _send_alert(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    event: TradingEvent,
) -> None:
    try:
        await deps.emit_notifier(event)
    except Exception:
        logger.debug("console notifier skipped for %s", event.kind)

    if not clerk_user_id:
        return

    try:
        delivered = await deps.notify_user(clerk_user_id, event)
    except Exception as exc:
        delivered = False
        logger.warning("telegram user alert failed for %s: %s", clerk_user_id, exc)

    if delivered is False:
        recent = _trim_failures(clerk_user_id)
        recent.append(time.time())
        _TELEGRAM_FAILURES[clerk_user_id] = recent
        payload = {
            "type": "telegram_alert_failed",
            "trace_id": event.trace_id,
            "kind": event.kind,
            "symbol": event.symbol,
            "venue": event.venue,
            "mode": event.mode,
            "timestamp": event.timestamp,
            "message": "Telegram delivery failed. Trading continued safely.",
        }
        await deps.broadcast(payload, ws_user_id)
        await _safe_capture_posthog("telegram_alert_failed", {
            "user_id": clerk_user_id,
            "trace_id": event.trace_id,
            "kind": event.kind,
            "venue": event.venue,
            "symbol": event.symbol,
        })
        if len(recent) >= 3:
            capture_sentry_exception(
                RuntimeError("Repeated telegram delivery failure"),
                context={
                    "user_id": clerk_user_id,
                    "trace_id": event.trace_id,
                    "venue": event.venue,
                    "symbol": event.symbol,
                    "kind": event.kind,
                },
            )


async def _publish_position_changes(
    deps: TradingEventDeps,
    *,
    ws_user_id: str | None,
    trace_id: str,
    changes: list[dict[str, Any]],
) -> None:
    for change in changes:
        event_type = str(change.get("type") or "")
        payload = dict(change.get("position") or {})
        payload["trace_id"] = trace_id
        await deps.broadcast({"type": event_type, "data": payload, "trace_id": trace_id}, ws_user_id)


async def on_agent_started(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    venue: str,
    mode: str,
    symbols: list[str],
    timeframe: str,
    trace_id: str,
) -> None:
    await deps.broadcast(
        {
            "type": "agent_started",
            "trace_id": trace_id,
            "venue": venue,
            "mode": mode,
            "symbols": symbols,
            "timeframe": timeframe,
        },
        ws_user_id,
    )
    await deps.broadcast({"type": "status_update", "status": "running", "paper": mode == "paper", "trace_id": trace_id}, ws_user_id)
    await deps.persist_audit(clerk_user_id, "agent_start", None, None, {
        "venue": venue,
        "symbols": symbols,
        "timeframe": timeframe,
        "mode": mode,
        "trace_id": trace_id,
    })
    await _send_alert(
        deps,
        clerk_user_id=clerk_user_id,
        ws_user_id=ws_user_id,
        event=TradingEvent(
            kind="agent_started",
            venue=venue,
            mode=mode,
            trace_id=trace_id,
            message=f"Agent started for {', '.join(symbols)} on {timeframe}.",
        ),
    )


async def on_agent_stopped(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    venue: str,
    mode: str,
    trace_id: str,
    reason: str,
    open_positions_remaining: int,
) -> None:
    message = (
        "Agent stopped. Open positions are still active."
        if open_positions_remaining > 0
        else "Agent stopped. No open positions remain."
    )
    await deps.broadcast(
        {
            "type": "agent_stopped",
            "trace_id": trace_id,
            "venue": venue,
            "mode": mode,
            "reason": reason,
            "open_positions_remaining": open_positions_remaining,
            "message": message,
        },
        ws_user_id,
    )
    await deps.broadcast(
        {
            "type": "status_update",
            "status": "stopped",
            "reason": reason,
            "paper": mode == "paper",
            "trace_id": trace_id,
            "open_positions_remaining": open_positions_remaining,
            "message": message,
        },
        ws_user_id,
    )
    await deps.persist_audit(clerk_user_id, "agent_stop", None, None, {
        "venue": venue,
        "mode": mode,
        "reason": reason,
        "trace_id": trace_id,
        "open_positions_remaining": open_positions_remaining,
    })
    await _safe_capture_posthog("agent_stopped_with_open_positions" if open_positions_remaining else "agent_stopped", {
        "user_id": clerk_user_id,
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "open_positions_remaining": open_positions_remaining,
        "reason": reason,
    })
    await _send_alert(
        deps,
        clerk_user_id=clerk_user_id,
        ws_user_id=ws_user_id,
        event=TradingEvent(
            kind="agent_stopped",
            venue=venue,
            mode=mode,
            trace_id=trace_id,
            message=message,
        ),
    )


async def on_risk_blocked(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    venue: str,
    mode: str,
    symbol: str,
    action: str,
    trace_id: str,
    reason: str,
    confidence: float | None = None,
) -> None:
    payload = {
        "type": "risk_blocked",
        "trace_id": trace_id,
        "symbol": symbol,
        "action": action,
        "venue": venue,
        "mode": mode,
        "reason": reason,
        "confidence": confidence,
    }
    await deps.broadcast(payload, ws_user_id)
    await deps.persist_audit(clerk_user_id, "risk_block", symbol, action, {
        "venue": venue,
        "mode": mode,
        "reason": reason,
        "trace_id": trace_id,
        "confidence": confidence,
    })
    await _safe_capture_posthog("trade_blocked_by_risk", {
        "user_id": clerk_user_id,
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "symbol": symbol,
        "action": action,
        "reason": reason,
    })
    await _send_alert(
        deps,
        clerk_user_id=clerk_user_id,
        ws_user_id=ws_user_id,
        event=TradingEvent(
            kind="risk_blocked",
            venue=venue,
            symbol=symbol,
            mode=mode,
            action=action,
            confidence=confidence,
            risk_summary=reason,
            trace_id=trace_id,
            message=f"Trade blocked by risk rules: {reason}",
        ),
    )


async def on_order_rejected(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    venue: str,
    mode: str,
    symbol: str,
    action: str,
    trace_id: str,
    reason: str,
) -> None:
    payload = {
        "type": "order_rejected",
        "trace_id": trace_id,
        "symbol": symbol,
        "action": action,
        "venue": venue,
        "mode": mode,
        "reason": reason,
    }
    await deps.broadcast(payload, ws_user_id)
    await deps.persist_audit(clerk_user_id, "order_rejected", symbol, action, payload)
    await _safe_capture_posthog("order_rejected", {
        "user_id": clerk_user_id,
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "symbol": symbol,
        "action": action,
        "reason": reason,
    })
    await _send_alert(
        deps,
        clerk_user_id=clerk_user_id,
        ws_user_id=ws_user_id,
        event=TradingEvent(
            kind="order_rejected",
            venue=venue,
            symbol=symbol,
            mode=mode,
            action=action,
            risk_summary=reason,
            trace_id=trace_id,
            message=f"Order rejected: {reason}",
        ),
    )


async def on_market_data_stale(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    venue: str,
    mode: str,
    symbol: str,
    trace_id: str,
    reason: str,
) -> None:
    payload = {
        "type": "market_data_stale",
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "symbol": symbol,
        "reason": reason,
    }
    await deps.broadcast(payload, ws_user_id)
    await deps.persist_audit(clerk_user_id, "market_data_stale", symbol, None, payload)
    await _safe_capture_posthog("market_data_stale", {
        "user_id": clerk_user_id,
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "symbol": symbol,
    })
    await _send_alert(
        deps,
        clerk_user_id=clerk_user_id,
        ws_user_id=ws_user_id,
        event=TradingEvent(
            kind="market_data_stale",
            venue=venue,
            symbol=symbol,
            mode=mode,
            trace_id=trace_id,
            message=reason,
        ),
    )


async def on_confidence_gate_skipped(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    venue: str,
    mode: str,
    symbol: str,
    trace_id: str,
    confidence: float,
    threshold_pct: float,
) -> None:
    payload = {
        "type": "decision_completed",
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "symbol": symbol,
        "action": "hold",
        "reason": "confidence_gate_skipped",
        "confidence": confidence,
        "threshold_pct": threshold_pct,
    }
    await deps.broadcast(payload, ws_user_id)
    await deps.persist_audit(clerk_user_id, "confidence_gate_skipped", symbol, "hold", payload)
    await _safe_capture_posthog("confidence_gate_skipped", {
        "user_id": clerk_user_id,
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "symbol": symbol,
        "confidence": confidence,
        "threshold_pct": threshold_pct,
    })
    await _send_alert(
        deps,
        clerk_user_id=clerk_user_id,
        ws_user_id=ws_user_id,
        event=TradingEvent(
            kind="confidence_gate_skipped",
            venue=venue,
            symbol=symbol,
            mode=mode,
            confidence=confidence,
            trace_id=trace_id,
            message=f"Trade skipped because confidence {confidence * 100:.1f}% is below the {threshold_pct:.1f}% threshold.",
        ),
    )


async def on_daily_loss_limit_reached(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    venue: str,
    mode: str,
    trace_id: str,
    loss_pct: float,
    limit_pct: float,
) -> None:
    message = f"Daily loss limit reached at {loss_pct:.1f}% versus the configured {limit_pct:.1f}% limit."
    payload = {
        "type": "status_update",
        "status": "stopping",
        "reason": "daily_loss_limit_reached",
        "trace_id": trace_id,
        "paper": mode == "paper",
        "message": message,
    }
    await deps.broadcast(payload, ws_user_id)
    await deps.persist_audit(clerk_user_id, "daily_loss_limit_reached", None, None, {
        "venue": venue,
        "mode": mode,
        "trace_id": trace_id,
        "loss_pct": loss_pct,
        "limit_pct": limit_pct,
    })
    await _safe_capture_posthog("daily_loss_limit_reached", {
        "user_id": clerk_user_id,
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "loss_pct": loss_pct,
        "limit_pct": limit_pct,
    })
    await _send_alert(
        deps,
        clerk_user_id=clerk_user_id,
        ws_user_id=ws_user_id,
        event=TradingEvent(
            kind="daily_loss_limit_reached",
            venue=venue,
            mode=mode,
            trace_id=trace_id,
            risk_summary=f"Loss {loss_pct:.1f}% / Limit {limit_pct:.1f}%",
            message=message,
        ),
    )


async def on_kill_switch_started(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    venue: str,
    mode: str,
    trace_id: str,
) -> None:
    await deps.broadcast({"type": "kill_switch_started", "trace_id": trace_id, "venue": venue, "mode": mode}, ws_user_id)
    await deps.persist_audit(clerk_user_id, "kill_switch_started", None, None, {
        "venue": venue,
        "mode": mode,
        "trace_id": trace_id,
    })


async def on_kill_switch_completed(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    venue: str,
    mode: str,
    trace_id: str,
    closed: list[str],
    remaining_open: int,
    errors: list[str],
) -> None:
    payload = {
        "type": "kill_switch_completed",
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "closed": closed,
        "remaining_open": remaining_open,
        "errors": errors,
    }
    await deps.broadcast(payload, ws_user_id)
    await deps.broadcast({"type": "status_update", "status": "stopped", "reason": "kill_switch", "paper": mode == "paper", "trace_id": trace_id}, ws_user_id)
    await deps.persist_audit(clerk_user_id, "kill_switch", None, None, payload)
    await _safe_capture_posthog("kill_switch_closed_positions", {
        "user_id": clerk_user_id,
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "closed_count": len(closed),
        "remaining_open": remaining_open,
        "errors": len(errors),
    })
    await _send_alert(
        deps,
        clerk_user_id=clerk_user_id,
        ws_user_id=ws_user_id,
        event=TradingEvent(
            kind="kill_switch_triggered",
            venue=venue,
            mode=mode,
            trace_id=trace_id,
            message=f"Kill switch completed. Closed={len(closed)} Remaining open={remaining_open}.",
            risk_summary="; ".join(errors) if errors else None,
        ),
    )


async def on_order_filled(
    deps: TradingEventDeps,
    *,
    clerk_user_id: str | None,
    ws_user_id: str | None,
    venue_runtime: Any,
    symbol: str,
    action: str,
    quantity: float,
    price: float,
    allocation_usd: float,
    rationale: str,
    risk_summary: dict[str, Any],
    before_balance: float,
    after_balance: float,
    indicators: dict[str, Any] | None,
    trace_id: str,
    source: str,
    confidence: float | None = None,
    tp_price: float | None = None,
    sl_price: float | None = None,
    tick_count: int = 0,
    realized_pnl: float | None = None,
) -> ReconciliationResult:
    venue = str(_runtime_value(venue_runtime, "venue_name", "unknown") or "unknown")
    market = str(_runtime_value(venue_runtime, "market", "spot") or "spot")
    is_paper = bool(_runtime_value(venue_runtime, "is_paper", False))
    mode = "paper" if is_paper else "live"
    await deps.broadcast(
        {
            "type": "order_filled",
            "trace_id": trace_id,
            "symbol": symbol,
            "action": action,
            "venue": venue,
            "mode": mode,
            "price": price,
            "qty": quantity,
            "allocation_usd": allocation_usd,
            "source": source,
        },
        ws_user_id,
    )
    await deps.broadcast(
        {
            "type": "trade_executed",
            "data": {"symbol": symbol, "action": action, "price": price, "qty": quantity, "venue": venue, "paper": is_paper, "source": source},
            "trace_id": trace_id,
        },
        ws_user_id,
    )
    receipt = build_trade_receipt(
        user_id=clerk_user_id or "",
        venue=venue,
        symbol=symbol,
        action=action,
        quantity=quantity,
        price=price,
        allocation_usd=allocation_usd,
        rationale=rationale,
        risk_summary=risk_summary,
        before_balance=before_balance,
        after_balance=after_balance,
        indicators=indicators,
        tp_price=tp_price,
        sl_price=sl_price,
        is_paper=is_paper,
        trace_id=trace_id,
        realized_pnl=realized_pnl,
    )
    reconciliation = await reconcile_positions(clerk_user_id, venue_runtime, mode, "order_filled", trace_id)
    position_key = f"{venue}:{market}:{mode}:{symbol}"
    await write_trade_receipt(clerk_user_id, position_key=position_key, receipt=receipt.to_dict())
    await deps.persist_trade(
        clerk_user_id,
        symbol=symbol,
        action=action,
        quantity=quantity,
        price=price,
        allocation_usd=allocation_usd,
        pnl=float(realized_pnl) if realized_pnl is not None else 0.0,
        source=source,
        rationale=rationale,
        tp_price=tp_price,
        sl_price=sl_price,
    )
    await deps.persist_audit(clerk_user_id, "order_filled", symbol, action, {
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "source": source,
        "quantity": quantity,
        "price": price,
        "allocation_usd": allocation_usd,
        "market": market,
    })
    await _publish_position_changes(deps, ws_user_id=ws_user_id, trace_id=trace_id, changes=reconciliation.changes)
    if clerk_user_id and deps.persist_equity is not None:
        await deps.persist_equity(clerk_user_id, after_balance, after_balance, after_balance - before_balance, tick_count)
    await _safe_capture_posthog("trade_executed", {
        "user_id": clerk_user_id,
        "trace_id": trace_id,
        "venue": venue,
        "mode": mode,
        "symbol": symbol,
        "action": action,
        "source": source,
    })
    alert_kind = "trade_closed" if any(change["type"] == "position_closed" and change["position"].get("symbol") == symbol for change in reconciliation.changes) else "trade_opened"
    await _send_alert(
        deps,
        clerk_user_id=clerk_user_id,
        ws_user_id=ws_user_id,
        event=TradingEvent(
            kind=alert_kind,  # type: ignore[arg-type]
            venue=venue,
            symbol=symbol,
            mode=mode,
            action=action,
            price=price,
            quantity=quantity,
            pnl=(
                float(realized_pnl)
                if alert_kind == "trade_closed" and realized_pnl is not None
                else None
            ),
            confidence=confidence if confidence is not None else receipt.confidence.overall,
            risk_summary=receipt.risk.human_summary(),
            trace_id=trace_id,
            message=receipt.ai_explanation,
        ),
    )
    return reconciliation


async def current_open_position_count(
    clerk_user_id: str | None,
    *,
    venue: str | None = None,
    market: str | None = None,
    mode: str | None = None,
) -> int:
    rows = await list_positions(clerk_user_id, include_closed=False, venue=venue, market=market, mode=mode)
    return len(rows)
