"""In-memory `Venue` implementation for backtesting.

Tracks positions and PnL by replaying orders against a configurable
"current bar." The engine calls `set_bar()` before each iteration so
`place_order` fills at that bar's close.
"""

from __future__ import annotations

from src.venues.base import Venue
from src.venues.models import (
    Balance,
    Candle,
    Order,
    OrderSide,
    OrderType,
    Position,
    SymbolMeta,
    Ticker,
)


class MockVenue(Venue):
    name = "mock"

    def __init__(
        self,
        starting_balance: float = 10_000.0,
        currency: str = "USDC",
        asset_class: str = "crypto_perp",
        taker_fee_bps: float = 5.0,  # 0.05%
    ):
        self.balance = starting_balance
        self.currency = currency
        self.asset_class = asset_class
        self._taker_fee = taker_fee_bps / 10_000.0

        self._current_bar: Candle | None = None
        self._symbol: str | None = None
        self._positions: dict[str, Position] = {}
        self._order_counter = 0
        self.fills: list[dict] = []
        self.equity_curve: list[tuple[int, float]] = []

    # ---- backtest helpers ----------------------------------------------------

    def set_bar(self, symbol: str, bar: Candle) -> None:
        self._symbol = symbol
        self._current_bar = bar
        # Mark-to-market unrealized PnL
        pos = self._positions.get(symbol)
        if pos:
            pos.unrealized_pnl = (bar.close - pos.entry_price) * pos.quantity
        self.equity_curve.append((bar.ts, self.equity()))

    def equity(self) -> float:
        return self.balance + sum(p.unrealized_pnl for p in self._positions.values())

    # ---- Venue interface -----------------------------------------------------

    async def get_balances(self) -> list[Balance]:
        return [Balance(currency=self.currency, total=self.equity(), available=self.balance)]

    async def get_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.quantity != 0]

    async def get_ticker(self, symbol: str) -> Ticker:
        price = self._current_bar.close if self._current_bar else 0.0
        return Ticker(symbol=symbol, last=price)

    async def get_candles(self, symbol: str, timeframe: str, lookback: int) -> list[Candle]:
        # The engine supplies bars directly; this is only useful for a
        # primed history window if needed.
        return []

    async def get_symbol_info(self, symbol: str) -> SymbolMeta:
        return SymbolMeta(
            symbol=symbol,
            asset_class=self.asset_class,  # type: ignore[arg-type]
            tick_size=0.01,
            lot_size=0.0001,
            min_notional=1.0,
            max_leverage=10.0,
        )

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
        if self._current_bar is None:
            raise RuntimeError("MockVenue.set_bar must be called before place_order")

        fill_price = price if order_type == "limit" and price is not None else self._current_bar.close
        signed_qty = quantity if side == "buy" else -quantity
        fee = abs(signed_qty) * fill_price * self._taker_fee
        self.balance -= fee

        pos = self._positions.get(symbol)
        if pos is None:
            pos = Position(symbol=symbol, quantity=0.0, entry_price=0.0)
            self._positions[symbol] = pos

        new_qty = pos.quantity + signed_qty
        if pos.quantity == 0 or (pos.quantity > 0) == (signed_qty > 0):
            # Opening or adding — weighted-avg entry
            total_notional = pos.quantity * pos.entry_price + signed_qty * fill_price
            pos.entry_price = total_notional / new_qty if new_qty else 0.0
        else:
            # Reducing or flipping — realize PnL on the closed portion
            closed = min(abs(pos.quantity), abs(signed_qty)) * (1 if pos.quantity > 0 else -1)
            self.balance += (fill_price - pos.entry_price) * closed
            if abs(signed_qty) > abs(pos.quantity):
                # Flipping side: remaining units open a new position at fill price
                pos.entry_price = fill_price
        pos.quantity = new_qty

        self._order_counter += 1
        order_id = f"mock-{self._order_counter}"
        self.fills.append({
            "ts": self._current_bar.ts,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": fill_price,
            "fee": fee,
            "balance_after": self.balance,
        })
        return Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=fill_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="filled",
            filled_quantity=quantity,
            avg_fill_price=fill_price,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        return True  # all fills are immediate in this mock

    async def close_position(self, symbol: str, quantity: float | None = None) -> Order | None:
        pos = self._positions.get(symbol)
        if not pos or pos.quantity == 0:
            return None
        qty = quantity if quantity is not None else abs(pos.quantity)
        side: OrderSide = "sell" if pos.quantity > 0 else "buy"
        return await self.place_order(symbol, side, qty, order_type="market")
