"""Interactive Brokers venue adapter via ib_insync.

Installation:
    poetry add ib_insync

Requires TWS or IB Gateway running locally (or in a Docker container).
Default connection: 127.0.0.1:7497 (paper) or 7496 (live).

Required env vars:
    IBKR_HOST=127.0.0.1  (default)
    IBKR_PORT=7497        (7497=paper, 7496=live)
    IBKR_CLIENT_ID=1      (unique per connection)
"""

from __future__ import annotations

import asyncio
import logging
import os

from src.venues.base import Venue
from src.venues.models import (
    AssetClass, Balance, Candle, Order, Position, SymbolMeta, Ticker,
)

logger = logging.getLogger("quantatraderai.venues.ibkr")

_TF_MAP = {
    "1m": "1 min", "5m": "5 mins", "15m": "15 mins", "30m": "30 mins",
    "1h": "1 hour", "4h": "4 hours", "1d": "1 day",
}
_DUR_MAP = {  # lookback bars → IB duration strings (approximate)
    "1 min":   "1 D", "5 mins":  "5 D", "15 mins": "2 W",
    "30 mins": "1 M", "1 hour":  "1 M", "4 hours": "3 M", "1 day": "1 Y",
}


def _require_ib():
    try:
        import ib_insync  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "ib_insync not installed. Run: poetry add ib_insync"
        ) from exc


class IBKRVenue(Venue):
    """Interactive Brokers adapter — stocks, options, futures, FX."""

    name = "ibkr"
    asset_class: AssetClass = "crypto_spot"  # used loosely for stocks

    def __init__(self):
        _require_ib()
        self._host      = os.getenv("IBKR_HOST", "127.0.0.1")
        self._port      = int(os.getenv("IBKR_PORT", "7497"))
        self._client_id = int(os.getenv("IBKR_CLIENT_ID", "1"))
        self._ib = None

    async def _get_ib(self):
        if self._ib and self._ib.isConnected():
            return self._ib
        import ib_insync
        ib = ib_insync.IB()
        await ib.connectAsync(self._host, self._port, clientId=self._client_id)
        self._ib = ib
        return ib

    @staticmethod
    def _stock(symbol: str):
        import ib_insync
        return ib_insync.Stock(symbol, "SMART", "USD")

    async def get_balances(self) -> list[Balance]:
        ib    = await self._get_ib()
        vals  = ib.accountValues()
        total = next((float(v.value) for v in vals if v.tag == "NetLiquidation" and v.currency == "USD"), 0.0)
        avail = next((float(v.value) for v in vals if v.tag == "AvailableFunds" and v.currency == "USD"), 0.0)
        return [Balance(currency="USD", total=total, available=avail)]

    async def get_positions(self) -> list[Position]:
        ib = await self._get_ib()
        return [
            Position(
                symbol=p.contract.symbol,
                quantity=float(p.position),
                entry_price=float(p.avgCost),
                unrealized_pnl=float(p.unrealizedPNL),
            )
            for p in ib.positions()
        ]

    async def get_ticker(self, symbol: str) -> Ticker:
        ib     = await self._get_ib()
        ticker = await ib.reqTickersAsync(self._stock(symbol))
        t      = ticker[0] if ticker else None
        last   = float(t.last or t.close or 0) if t else 0
        bid    = float(t.bid or 0) if t else None
        ask    = float(t.ask or 0) if t else None
        return Ticker(symbol=symbol, last=last, bid=bid, ask=ask)

    async def get_candles(self, symbol: str, timeframe: str, lookback: int) -> list[Candle]:
        ib     = await self._get_ib()
        ib_tf  = _TF_MAP.get(timeframe, "1 hour")
        dur    = _DUR_MAP.get(ib_tf, "1 M")
        bars   = await ib.reqHistoricalDataAsync(
            self._stock(symbol), endDateTime="", durationStr=dur,
            barSizeSetting=ib_tf, whatToShow="TRADES", useRTH=True,
        )
        return [
            Candle(
                ts=int(b.date.timestamp()),
                open=float(b.open), high=float(b.high),
                low=float(b.low), close=float(b.close), volume=float(b.volume),
            )
            for b in bars[-lookback:]
        ]

    async def get_symbol_info(self, symbol: str) -> SymbolMeta:
        return SymbolMeta(
            symbol=symbol, asset_class="crypto_spot",
            tick_size=0.01, lot_size=1.0, min_notional=1.0, max_leverage=4.0,
        )

    async def place_order(self, symbol: str, side: str, quantity: float,
                          order_type: str = "market", price: float | None = None,
                          stop_loss: float | None = None, take_profit: float | None = None,
                          leverage: float | None = None) -> Order:
        import ib_insync
        ib      = await self._get_ib()
        action  = "BUY" if side == "buy" else "SELL"
        if order_type == "market":
            order = ib_insync.MarketOrder(action, quantity)
        else:
            order = ib_insync.LimitOrder(action, quantity, price)  # type: ignore
        trade = ib.placeOrder(self._stock(symbol), order)
        await asyncio.sleep(0.5)  # allow partial fill event
        return Order(
            order_id=str(trade.order.orderId), symbol=symbol, side=side,  # type: ignore[arg-type]
            order_type=order_type, quantity=quantity, status=trade.orderStatus.status,  # type: ignore[arg-type]
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        import ib_insync
        ib    = await self._get_ib()
        order = ib_insync.Order(); order.orderId = int(order_id)
        ib.cancelOrder(order)
        return True

    async def close_position(self, symbol: str, quantity: float | None = None) -> Order | None:
        positions = await self.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)
        if not pos:
            return None
        qty = quantity or abs(pos.quantity)
        side = "sell" if pos.quantity > 0 else "buy"
        return await self.place_order(symbol, side, qty)
