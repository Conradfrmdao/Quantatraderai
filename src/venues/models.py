"""Shared dataclasses used across all venue adapters.

Adapters convert venue-specific payloads into these types so the agent,
risk manager, and backtester can stay venue-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

AssetClass = Literal["crypto_perp", "crypto_spot", "forex", "prediction"]
OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "stop", "take_profit"]


@dataclass
class Candle:
    ts: int  # epoch seconds
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Ticker:
    symbol: str
    last: float
    bid: float | None = None
    ask: float | None = None


@dataclass
class Balance:
    currency: str
    total: float
    available: float


@dataclass
class Position:
    symbol: str
    quantity: float  # signed: +long, -short
    entry_price: float
    unrealized_pnl: float = 0.0
    leverage: float | None = None
    liquidation_price: float | None = None


@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    status: str = "open"
    filled_quantity: float = 0.0
    avg_fill_price: float | None = None


@dataclass
class SymbolMeta:
    """Metadata every adapter must expose for a symbol.

    The risk manager and agent consult this before sizing any order;
    crypto perps, crypto spot, and forex all have materially different
    constraints.
    """
    symbol: str
    asset_class: AssetClass
    tick_size: float
    lot_size: float
    min_notional: float
    max_leverage: float
    # Forex-specific
    pip_value: float | None = None
    # Perp-specific
    funding_rate: float | None = None
    # Extra venue-native payload if the agent needs it
    extra: dict = field(default_factory=dict)
