"""Notifier with pluggable backends."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol

from src.config_loader import CONFIG

EventKind = Literal[
    "agent_started",
    "agent_stopped",
    "trade_opened",
    "trade_closed",
    "stop_loss_hit",
    "take_profit_hit",
    "order_rejected",
    "risk_block",
    "risk_blocked",
    "kill_switch_triggered",
    "market_data_stale",
    "exchange_connection_lost",
    "ai_council_failed",
    "daily_loss_limit_reached",
    "confidence_gate_skipped",
    "telegram_alert_failed",
    "circuit_breaker_tripped",
    "decision_error",
    "info",
]


@dataclass
class TradingEvent:
    kind: EventKind
    venue: str
    symbol: str | None = None
    mode: str | None = None
    action: str | None = None
    price: float | None = None
    quantity: float | None = None
    pnl: float | None = None
    confidence: float | None = None
    risk_summary: str | None = None
    trace_id: str | None = None
    timestamp: str | None = None
    message: str = ""
    data: dict = field(default_factory=dict)

    def render_text(self) -> str:
        parts = [self.kind.replace("_", " ").title()]
        venue = self.venue or "unknown"
        header = f"Venue: {venue}"
        if self.symbol:
            header += f" | Symbol: {self.symbol}"
        if self.mode:
            header += f" | Mode: {self.mode}"
        parts.append(header)
        if self.action:
            parts.append(f"Action: {self.action}")
        if self.price is not None:
            parts.append(f"Price: {self.price}")
        if self.quantity is not None:
            parts.append(f"Quantity: {self.quantity}")
        if self.pnl is not None:
            parts.append(f"PnL: {self.pnl}")
        if self.confidence is not None:
            parts.append(f"Confidence: {round(float(self.confidence) * 100, 1)}%")
        if self.risk_summary:
            parts.append(f"Risk: {self.risk_summary}")
        if self.message:
            parts.append(self.message)
        parts.append(f"Trace ID: {self.trace_id or '-'}")
        parts.append(f"Timestamp: {self.timestamp or datetime.now(timezone.utc).isoformat()}")
        return "\n".join(parts)[:4096]


class Backend(Protocol):
    async def send(self, event: TradingEvent) -> None: ...


class ConsoleBackend:
    async def send(self, event: TradingEvent) -> None:
        logging.info("[%s][%s] %s", event.venue, event.kind, event.render_text())


class TelegramBackend:
    """H12: Fully async Telegram notifier — never blocks the event loop."""

    def __init__(self, token: str, chat_id: str):
        self.token   = token
        self.chat_id = chat_id
        self._url    = f"https://api.telegram.org/bot{self.token}/sendMessage"

    async def send(self, event: TradingEvent) -> None:
        text = event.render_text()
        try:
            import aiohttp as ah
            async with ah.ClientSession() as session:
                async with session.post(
                    self._url,
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                    timeout=ah.ClientTimeout(total=3),  # 3s max — never blocks trading
                ) as resp:
                    if resp.status not in (200, 400):  # 400 = bad chat_id, not transient
                        logging.warning("Telegram returned %d", resp.status)
        except asyncio.TimeoutError:
            logging.warning("Telegram send timed out — skipping")
        except Exception as e:
            logging.warning("Telegram send failed: %s", e)


class Notifier:
    def __init__(self, backends: list[Backend]):
        self.backends = backends

    async def emit(self, event: TradingEvent) -> None:
        await asyncio.gather(*(b.send(event) for b in self.backends), return_exceptions=True)


def build_notifier() -> Notifier:
    """Construct a Notifier from .env config. Always includes ConsoleBackend."""
    backends: list[Backend] = [ConsoleBackend()]
    token = CONFIG.get("telegram_bot_token")
    chat_id = CONFIG.get("telegram_chat_id")
    if token and chat_id:
        backends.append(TelegramBackend(token, chat_id))
    return Notifier(backends)
