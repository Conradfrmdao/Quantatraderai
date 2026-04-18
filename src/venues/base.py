"""Abstract `Venue` interface — the contract every exchange/broker implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.venues.models import (
    AssetClass,
    Balance,
    Candle,
    Order,
    OrderSide,
    OrderType,
    Position,
    SymbolMeta,
    Ticker,
)


class Venue(ABC):
    """Minimum surface the agent, risk manager, and backtester require."""

    name: str
    asset_class: AssetClass

    @abstractmethod
    async def get_balances(self) -> list[Balance]:
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        ...

    @abstractmethod
    async def get_candles(
        self, symbol: str, timeframe: str, lookback: int
    ) -> list[Candle]:
        ...

    @abstractmethod
    async def get_symbol_info(self, symbol: str) -> SymbolMeta:
        ...

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = "market",
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        leverage: float | None = None,
    ) -> Order:
        ...

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        ...

    @abstractmethod
    async def close_position(self, symbol: str, quantity: float | None = None) -> Order | None:
        ...
