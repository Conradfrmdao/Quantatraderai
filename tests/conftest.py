"""Shared fixtures for QuntaTradeAI test suite.

Provides:
  - base_candles       — 20 synthetic OHLCV candles
  - account_state_factory — minimal account dict for RiskManager tests
  - MockVenue          — in-memory Venue that records all calls
  - mock_env           — sets ENCRYPTION_KEY + DATABASE_URL for tests
  - encrypted_key_pair — (plaintext, ciphertext) round-trip fixture
"""
from __future__ import annotations

import asyncio
import base64
import os
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Test encryption key (32 bytes, deterministic for all tests) ───────────────
_TEST_ENC_KEY = base64.urlsafe_b64encode(b"QuntaTest2025_SecureKey_32bytes!").decode()


# ── Environment fixture ────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Always set minimal required env vars so nothing crashes on import."""
    monkeypatch.setenv("ENCRYPTION_KEY", _TEST_ENC_KEY)
    monkeypatch.setenv("DATABASE_URL", "postgresql://mock:mock@localhost/mock")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-used")
    monkeypatch.setenv("WS_AUTH_REQUIRED", "false")


# ── Candle fixture ─────────────────────────────────────────────────────────────
@pytest.fixture
def base_candles():
    """20 synthetic OHLCV candles for indicator smoke tests."""
    prices = [
        100, 102, 101, 105, 103, 107, 106, 110, 108, 112,
        109, 111, 113, 110, 108, 106, 104, 107, 109, 111,
    ]
    candles = []
    for i, close in enumerate(prices):
        candles.append({
            "time":   1_700_000_000 + i * 3600,
            "open":   close - 1,
            "high":   close + 2,
            "low":    close - 2,
            "close":  float(close),
            "volume": 1000.0 + i * 10,
        })
    return candles


# ── Account state factory ──────────────────────────────────────────────────────
@pytest.fixture
def account_state_factory():
    """Build a minimal account_state dict for RiskManager tests."""
    def _make(total_value=10_000.0, balance=8_000.0, positions=None):
        return {
            "total_value": total_value,
            "balance": balance,
            "positions": positions or [],
            "min_order_usd": 1.0,
        }
    return _make


# ── Encryption round-trip fixture ──────────────────────────────────────────────
@pytest.fixture
def encrypted_key_pair():
    """Returns (plaintext, ciphertext) for Binance-format API key."""
    from src.services.encryption import encrypt, decrypt
    plaintext = "test-binance-api-key-abc123"
    ciphertext = encrypt(plaintext)
    return {"plaintext": plaintext, "ciphertext": ciphertext}


# ── MockVenue — full in-memory implementation ──────────────────────────────────
class MockVenue:
    """Deterministic in-memory venue for testing.

    Records every call so tests can assert on what was placed/cancelled.
    Raises RuntimeError on demand to test error handling.
    """
    name = "mock"
    asset_class = "crypto_spot"

    def __init__(self, starting_balance: float = 10_000.0, fail_on: str | None = None):
        from src.venues.models import Balance, Candle, Order, Position, SymbolMeta, Ticker
        self.Balance    = Balance
        self.Candle     = Candle
        self.Order      = Order
        self.Position   = Position
        self.SymbolMeta = SymbolMeta
        self.Ticker     = Ticker

        self._balance    = starting_balance
        self._positions: list[Any] = []
        self._orders:    list[Any] = []
        self._fail_on    = fail_on   # e.g. "get_balances", "place_order"
        self._price      = 50_000.0  # default price for all symbols
        self.calls: dict[str, int] = {}

    def _record(self, name: str):
        self.calls[name] = self.calls.get(name, 0) + 1
        if self._fail_on == name:
            raise RuntimeError(f"MockVenue: simulated failure on {name}")

    async def get_balances(self):
        self._record("get_balances")
        return [self.Balance(currency="USDT", total=self._balance, available=self._balance)]

    async def get_positions(self):
        self._record("get_positions")
        return list(self._positions)

    async def get_ticker(self, symbol: str):
        self._record("get_ticker")
        return self.Ticker(symbol=symbol, last=self._price,
                           bid=self._price - 1, ask=self._price + 1)

    async def get_candles(self, symbol: str, timeframe: str, lookback: int):
        self._record("get_candles")
        now = int(time.time())
        interval = 3600
        candles = []
        for i in range(lookback, 0, -1):
            p = self._price + (i % 7 - 3) * 100
            candles.append(self.Candle(
                ts=now - i * interval,
                open=p - 50, high=p + 100, low=p - 100, close=p, volume=100.0,
            ))
        return candles

    async def get_symbol_info(self, symbol: str):
        self._record("get_symbol_info")
        return self.SymbolMeta(
            symbol=symbol, asset_class="crypto_spot",
            tick_size=0.01, lot_size=0.001,
            min_notional=10.0, max_leverage=10.0,
        )

    async def place_order(self, symbol, side, quantity, order_type="market",
                          price=None, stop_loss=None, take_profit=None, leverage=None):
        self._record("place_order")
        order = self.Order(
            order_id=str(uuid.uuid4()), symbol=symbol, side=side,
            order_type=order_type, quantity=quantity, price=price or self._price,
            stop_loss=stop_loss, take_profit=take_profit,
            status="filled", filled_quantity=quantity, avg_fill_price=price or self._price,
        )
        self._orders.append(order)
        # Update balance and add position
        cost = quantity * (price or self._price)
        if side == "buy":
            self._balance -= cost
            from src.venues.models import Position
            self._positions.append(Position(
                symbol=symbol, quantity=quantity, entry_price=price or self._price,
                unrealized_pnl=0.0,
            ))
        else:
            self._balance += cost
            self._positions = [p for p in self._positions if p.symbol != symbol]
        return order

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        self._record("cancel_order")
        return True

    async def close_position(self, symbol: str, quantity: float | None = None):
        self._record("close_position")
        pos = next((p for p in self._positions if p.symbol == symbol), None)
        if not pos:
            return None
        qty = quantity or abs(pos.quantity)
        self._positions = [p for p in self._positions if p.symbol != symbol]
        self._balance += qty * self._price
        return self.Order(
            order_id=str(uuid.uuid4()), symbol=symbol, side="sell",
            order_type="market", quantity=qty, price=self._price,
            status="filled", filled_quantity=qty, avg_fill_price=self._price,
        )

    def set_price(self, price: float):
        self._price = price

    def inject_position(self, symbol: str, qty: float, entry: float):
        from src.venues.models import Position
        self._positions.append(Position(symbol=symbol, quantity=qty, entry_price=entry))


@pytest.fixture
def mock_venue():
    return MockVenue(starting_balance=10_000.0)


@pytest.fixture
def mock_venue_factory():
    def _make(balance=10_000.0, fail_on=None):
        return MockVenue(starting_balance=balance, fail_on=fail_on)
    return _make
