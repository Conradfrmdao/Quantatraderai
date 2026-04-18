"""Notifier with pluggable backends.

Backends:
  - ConsoleBackend (always on, zero-config)
  - TelegramBackend (enabled when TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set)

Events are tagged with venue so multi-venue runs stay legible.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal, Protocol

from src.config_loader import CONFIG

EventKind = Literal[
    "trade_opened",
    "trade_closed",
    "stop_loss_hit",
    "circuit_breaker_tripped",
    "decision_error",
    "info",
]


@dataclass
class TradingEvent:
    kind: EventKind
    venue: str
    symbol: str | None = None
    message: str = ""
    data: dict = field(default_factory=dict)


class Backend(Protocol):
    async def send(self, event: TradingEvent) -> None: ...


class ConsoleBackend:
    async def send(self, event: TradingEvent) -> None:
        logging.info("[%s][%s] %s %s", event.venue, event.kind, event.symbol or "-", event.message)


class TelegramBackend:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    async def send(self, event: TradingEvent) -> None:
        import requests
        text = f"[{event.venue}][{event.kind}] {event.symbol or ''} {event.message}".strip()
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        def _do():
            try:
                requests.post(url, json={"chat_id": self.chat_id, "text": text}, timeout=10)
            except Exception as e:
                logging.warning("Telegram send failed: %s", e)

        await asyncio.to_thread(_do)


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
