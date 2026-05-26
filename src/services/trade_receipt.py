"""Trade Receipt — produces Stripe-style receipts for every trade action.

Every trade that passes risk validation gets a TradeReceipt with:
  - Unique trade_id (UUID)
  - Timestamp
  - Venue + symbol + action
  - Risk decision (why it passed or was capped)
  - Confidence score (0-1) based on indicator alignment
  - Before + after balance snapshot
  - Human-readable explanation: "Why this trade?"
  - AES-256 signed: receipt_hash

Usage (in server.py after place_order succeeds):
    receipt = build_trade_receipt(
        user_id, venue, symbol, action, qty, price, alloc_usd,
        rationale, risk_summary, before_balance, after_balance,
        indicators, tp_price, sl_price,
    )
    # receipt.to_dict() is stored in TradeLog.data and returned to dashboard
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


@dataclass
class RiskDecision:
    passed:       bool
    capped:       bool          # True if allocation was reduced
    original_alloc: float
    final_alloc:    float
    reason:       str           # "" if passed cleanly
    limits_applied: dict[str, Any] = field(default_factory=dict)

    def human_summary(self) -> str:
        if not self.passed:
            return f"Trade blocked: {self.reason}"
        if self.capped:
            diff = self.original_alloc - self.final_alloc
            return (
                f"Allocation capped from ${self.original_alloc:.2f} to "
                f"${self.final_alloc:.2f} (reduced by ${diff:.2f} to comply with "
                f"max_position_pct={self.limits_applied.get('max_position_pct', '?')}%)"
            )
        return f"Risk check passed. Allocation ${self.final_alloc:.2f} within all limits."


@dataclass
class ConfidenceBreakdown:
    """Breakdown of each signal contributing to confidence."""
    rsi_signal:    float = 0.0   # 0-1: how aligned RSI is with direction
    macd_signal:   float = 0.0
    ema_signal:    float = 0.0
    overall:       float = 0.0   # weighted mean

    def label(self) -> str:
        if self.overall >= 0.75: return "HIGH"
        if self.overall >= 0.45: return "MEDIUM"
        return "LOW"

    def to_dict(self) -> dict:
        return {
            "rsi":     round(self.rsi_signal, 3),
            "macd":    round(self.macd_signal, 3),
            "ema":     round(self.ema_signal, 3),
            "overall": round(self.overall, 3),
            "label":   self.label(),
        }


@dataclass
class TradeReceipt:
    trade_id:        str
    trace_id:        str          # shared with audit log entry
    timestamp:       str          # ISO-8601 UTC
    user_id:         str
    venue:           str
    symbol:          str
    action:          str          # buy | sell | close
    quantity:        float
    price:           float
    allocation_usd:  float
    tp_price:        float | None
    sl_price:        float | None
    before_balance:  float
    after_balance:   float
    pnl_unrealized:  float
    risk:            RiskDecision
    confidence:      ConfidenceBreakdown
    rationale:       str          # LLM rationale text
    ai_explanation:  str          # "Why this trade?" human sentence
    mode:            str          # paper | live
    receipt_hash:    str = ""     # HMAC-SHA256 of canonical fields

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confidence"] = self.confidence.to_dict()
        d["risk"] = asdict(self.risk)
        d["risk"]["human_summary"] = self.risk.human_summary()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _confidence_from_indicators(action: str, indicators: dict[str, Any]) -> ConfidenceBreakdown:
    """Derive a confidence breakdown from live indicator values."""
    rsi   = float(indicators.get("rsi14") or 50.0)
    macd  = float(indicators.get("macd")  or 0.0)
    ema20 = float(indicators.get("ema20") or 0.0)
    price = float(indicators.get("current_price") or 0.0)

    is_buy = action == "buy"

    # RSI: oversold (<30) → strong buy signal, overbought (>70) → strong sell
    if is_buy:
        rsi_sig = max(0.0, (50.0 - rsi) / 50.0)   # higher for lower RSI
    else:
        rsi_sig = max(0.0, (rsi - 50.0) / 50.0)   # higher for higher RSI
    rsi_sig = min(1.0, rsi_sig)

    # MACD: positive for buy, negative for sell
    macd_sig = min(1.0, abs(macd) / 10.0) if (is_buy and macd > 0) or (not is_buy and macd < 0) else 0.2

    # EMA: price above EMA20 favours buy
    if price > 0 and ema20 > 0:
        ratio = price / ema20
        ema_sig = min(1.0, (ratio - 1.0) * 10.0) if is_buy else min(1.0, (1.0 - ratio) * 10.0)
        ema_sig = max(0.0, ema_sig)
    else:
        ema_sig = 0.5

    overall = 0.4 * rsi_sig + 0.35 * macd_sig + 0.25 * ema_sig
    return ConfidenceBreakdown(rsi_signal=rsi_sig, macd_signal=macd_sig,
                               ema_signal=ema_sig, overall=overall)


def _ai_explanation(
    action: str, symbol: str, rationale: str,
    indicators: dict[str, Any],
    confidence: ConfidenceBreakdown,
    risk: RiskDecision,
) -> str:
    """Produce a one-sentence human explanation: 'Why this trade?'"""
    rsi    = indicators.get("rsi14")
    macd   = indicators.get("macd")
    conf_l = confidence.label()

    signal_parts = []
    if rsi is not None:
        if action == "buy"  and float(rsi) < 35: signal_parts.append(f"RSI at {rsi:.0f} (oversold)")
        elif action == "sell" and float(rsi) > 65: signal_parts.append(f"RSI at {rsi:.0f} (overbought)")
        else: signal_parts.append(f"RSI at {rsi:.0f}")
    if macd is not None:
        direction = "positive" if float(macd) > 0 else "negative"
        signal_parts.append(f"MACD {direction} ({float(macd):.4f})")

    alloc_line = f"${risk.final_alloc:.2f} allocated"
    if risk.capped:
        alloc_line += " (capped by risk limits)"

    signal_str = " and ".join(signal_parts) if signal_parts else "indicator alignment"

    short_rationale = (rationale[:120] + "…") if len(rationale) > 120 else rationale

    return (
        f"The AI placed a {action.upper()} on {symbol} with {conf_l} confidence "
        f"({confidence.overall:.0%}). Signals: {signal_str}. "
        f"{alloc_line}. Reasoning: {short_rationale}"
    )


def _receipt_hash(r: TradeReceipt) -> str:
    """Tamper-evident hash of canonical fields using ENCRYPTION_KEY as HMAC key."""
    import hmac, os
    canonical = f"{r.trade_id}|{r.user_id}|{r.venue}|{r.symbol}|{r.action}|{r.quantity}|{r.price}|{r.allocation_usd}|{r.timestamp}"
    raw_key = os.getenv("ENCRYPTION_KEY")
    if not raw_key:
        raise RuntimeError("ENCRYPTION_KEY is not set — cannot produce tamper-evident receipt hash")
    key = raw_key.encode()
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()[:24]


def build_trade_receipt(
    user_id:        str,
    venue:          str,
    symbol:         str,
    action:         str,
    quantity:       float,
    price:          float,
    allocation_usd: float,
    rationale:      str,
    risk_summary:   dict[str, Any],
    before_balance: float,
    after_balance:  float,
    indicators:     dict[str, Any] | None = None,
    tp_price:       float | None = None,
    sl_price:       float | None = None,
    is_paper:       bool = True,
    trace_id:       str | None = None,
    realized_pnl:   float | None = None,
) -> TradeReceipt:
    """Construct a complete TradeReceipt — call after order fills."""
    trade_id   = str(uuid.uuid4())
    trace_id   = trace_id or str(uuid.uuid4())
    ts         = datetime.now(timezone.utc).isoformat()
    inds       = indicators or {}

    original_alloc = risk_summary.get("original_allocation_usd", allocation_usd)
    capped         = abs(original_alloc - allocation_usd) > 0.01

    risk = RiskDecision(
        passed=True, capped=capped,
        original_alloc=original_alloc, final_alloc=allocation_usd,
        reason="",
        limits_applied={
            "max_position_pct": risk_summary.get("max_position_pct", "?"),
            "max_leverage":     risk_summary.get("max_leverage", "?"),
        },
    )

    confidence = _confidence_from_indicators(action, {**inds, "current_price": price})
    explanation = _ai_explanation(action, symbol, rationale, inds, confidence, risk)

    pnl = float(realized_pnl) if realized_pnl is not None else (after_balance - before_balance)

    receipt = TradeReceipt(
        trade_id=trade_id, trace_id=trace_id,
        timestamp=ts, user_id=user_id,
        venue=venue, symbol=symbol, action=action,
        quantity=quantity, price=price,
        allocation_usd=allocation_usd,
        tp_price=tp_price, sl_price=sl_price,
        before_balance=before_balance, after_balance=after_balance,
        pnl_unrealized=pnl,
        risk=risk, confidence=confidence,
        rationale=rationale, ai_explanation=explanation,
        mode="paper" if is_paper else "live",
    )
    receipt.receipt_hash = _receipt_hash(receipt)
    return receipt
