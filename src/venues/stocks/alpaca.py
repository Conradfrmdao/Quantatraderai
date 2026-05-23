"""Alpaca venue adapter — US stocks and options (paper + live).

Installation:
    poetry add alpaca-py

Required env vars:
    ALPACA_API_KEY
    ALPACA_API_SECRET
    ALPACA_PAPER=true   (default true — use paper trading URL)
"""

from __future__ import annotations

import logging
import os

from src.venues.base import Venue
from src.venues.models import (
    AssetClass, Balance, Candle, Order, Position, SymbolMeta, Ticker,
)

logger = logging.getLogger("quantatraderai.venues.alpaca")

_TF_MAP = {
    "1m": "1Min", "5m": "5Min", "15m": "15Min", "30m": "30Min",
    "1h": "1Hour", "4h": "4Hour", "1d": "1Day",
}


def _require_alpaca():
    try:
        from alpaca.trading.client import TradingClient  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "alpaca-py not installed. Run: poetry add alpaca-py"
        ) from exc


class AlpacaVenue(Venue):
    name = "alpaca"
    asset_class: AssetClass = "stocks"

    def __init__(self, api_key: str | None = None, api_secret: str | None = None, paper: bool | None = None):
        _require_alpaca()
        self._key    = api_key    or os.getenv("ALPACA_API_KEY", "")
        self._secret = api_secret or os.getenv("ALPACA_API_SECRET", "")
        self._paper  = paper if paper is not None else os.getenv("ALPACA_PAPER", "true").lower() in ("1","true","yes")
        if not self._key or not self._secret:
            raise ValueError("ALPACA_API_KEY and ALPACA_API_SECRET must be set")
        from alpaca.trading.client import TradingClient
        from alpaca.data.historical import StockHistoricalDataClient
        self._trading = TradingClient(self._key, self._secret, paper=self._paper)
        self._data    = StockHistoricalDataClient(self._key, self._secret)

    async def get_balances(self) -> list[Balance]:
        import asyncio
        acct = await asyncio.to_thread(self._trading.get_account)
        return [Balance(
            currency="USD",
            total=float(acct.portfolio_value),
            available=float(acct.cash),
        )]

    async def get_positions(self) -> list[Position]:
        import asyncio
        raw = await asyncio.to_thread(self._trading.get_all_positions)
        return [
            Position(
                symbol=p.symbol,
                quantity=float(p.qty),
                entry_price=float(p.avg_entry_price),
                unrealized_pnl=float(p.unrealized_pl),
            )
            for p in raw
        ]

    async def get_ticker(self, symbol: str) -> Ticker:
        import asyncio
        from alpaca.data.requests import StockLatestQuoteRequest
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        data = await asyncio.to_thread(self._data.get_stock_latest_quote, req)
        quote = data[symbol]
        mid = (float(quote.bid_price) + float(quote.ask_price)) / 2
        return Ticker(symbol=symbol, last=mid, bid=float(quote.bid_price), ask=float(quote.ask_price))

    async def get_candles(self, symbol: str, timeframe: str, lookback: int) -> list[Candle]:
        import asyncio
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        tf_str = _TF_MAP.get(timeframe, "1Hour")
        # Parse "1Hour" → amount=1, unit=Hour
        _unit_map = {"Min": TimeFrameUnit.Minute, "Hour": TimeFrameUnit.Hour, "Day": TimeFrameUnit.Day}
        amount = int("".join(c for c in tf_str if c.isdigit()) or "1")
        unit_str = "".join(c for c in tf_str if not c.isdigit())
        unit = _unit_map.get(unit_str, TimeFrameUnit.Hour)
        tf = TimeFrame(amount, unit)
        from datetime import datetime, timedelta, timezone
        start = datetime.now(timezone.utc) - timedelta(hours=lookback * amount if unit == TimeFrameUnit.Hour else lookback)
        req  = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start, limit=lookback)
        data = await asyncio.to_thread(self._data.get_stock_bars, req)
        bars = data[symbol]
        return [
            Candle(
                ts=int(b.timestamp.timestamp()),
                open=float(b.open), high=float(b.high),
                low=float(b.low), close=float(b.close), volume=float(b.volume),
            )
            for b in bars
        ]

    async def get_symbol_info(self, symbol: str) -> SymbolMeta:
        return SymbolMeta(
            symbol=symbol, asset_class="stocks",
            tick_size=0.01, lot_size=1.0, min_notional=1.0, max_leverage=4.0,
        )

    async def place_order(self, symbol: str, side: str, quantity: float,
                          order_type: str = "market", price: float | None = None,
                          stop_loss: float | None = None, take_profit: float | None = None,
                          leverage: float | None = None) -> Order:
        import asyncio
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce
        alpaca_side = AlpacaSide.BUY if side == "buy" else AlpacaSide.SELL
        if order_type == "market":
            req = MarketOrderRequest(symbol=symbol, qty=quantity, side=alpaca_side, time_in_force=TimeInForce.DAY)
        else:
            req = LimitOrderRequest(symbol=symbol, qty=quantity, side=alpaca_side, limit_price=price, time_in_force=TimeInForce.DAY)  # type: ignore
        order = await asyncio.to_thread(self._trading.submit_order, req)
        return Order(
            order_id=str(order.id), symbol=symbol, side=side,  # type: ignore[arg-type]
            order_type=order_type, quantity=quantity, status=str(order.status),  # type: ignore[arg-type]
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        import asyncio
        from uuid import UUID
        try:
            await asyncio.to_thread(self._trading.cancel_order_by_id, UUID(order_id))
            return True
        except Exception as e:
            logger.warning("cancel_order %s: %s", order_id, e)
            return False

    async def close_position(self, symbol: str, quantity: float | None = None) -> Order | None:
        import asyncio
        try:
            result = await asyncio.to_thread(self._trading.close_position, symbol)
            return Order(
                order_id=str(result.id), symbol=symbol, side="sell",  # type: ignore[arg-type]
                order_type="market", quantity=float(result.qty or 0), status="filled",  # type: ignore[arg-type]
            )
        except Exception as e:
            logger.warning("close_position %s: %s", symbol, e)
            return None
