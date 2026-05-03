"""CCXT venue adapter — one implementation covers 100+ crypto exchanges.

Set `CCXT_EXCHANGE` to any CCXT-supported id (binance, bybit, coinbase,
kraken, okx, kucoin, bitget, gate, mexc, ...). API keys live under
`CCXT_API_KEY` / `CCXT_API_SECRET`; `CCXT_SANDBOX=true` enables testnet
on exchanges that support it.

Symbol format follows CCXT's unified notation, e.g. "BTC/USDT",
"ETH/USDT:USDT" (perp), "ETH/USD".
"""

from __future__ import annotations

import asyncio
import logging
import os

from src.config_loader import CONFIG
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


class CcxtVenue(Venue):
    name = "ccxt"
    # asset_class set dynamically per symbol; default to spot
    asset_class = "crypto_spot"

    def __init__(self, exchange_name: str | None = None):
        try:
            import ccxt  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "ccxt is not installed. Run `poetry install` (or pip install ccxt)."
            ) from e

        self._ccxt = ccxt
        exchange_id = (exchange_name or os.environ.get("CCXT_EXCHANGE") or CONFIG.get("ccxt_exchange") or "binance").lower()
        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"CCXT has no exchange named {exchange_id!r}")

        def _ascii(s: str) -> str:
            return s.encode("ascii", errors="ignore").decode("ascii").strip()

        exchange_cls = getattr(ccxt, exchange_id)
        self.client = exchange_cls({
            "apiKey": _ascii(os.environ.get("CCXT_API_KEY") or CONFIG.get("ccxt_api_key") or ""),
            "secret": _ascii(os.environ.get("CCXT_API_SECRET") or CONFIG.get("ccxt_api_secret") or ""),
            "enableRateLimit": True,
        })
        sandbox_val = os.environ.get("CCXT_SANDBOX") or str(CONFIG.get("ccxt_sandbox", "true"))
        sandbox = sandbox_val.lower() in {"1", "true", "yes"}
        if sandbox and hasattr(self.client, "set_sandbox_mode"):
            try:
                self.client.set_sandbox_mode(True)
            except Exception as e:
                logging.warning("CCXT %s does not support sandbox mode: %s", exchange_id, e)
        self.exchange_id = exchange_id
        self.name = f"ccxt:{exchange_id}"

    # CCXT's sync calls wrapped in to_thread keep the adapter async-compatible.
    async def _call(self, fn, *args, **kwargs):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except UnicodeEncodeError as e:
            raise RuntimeError(
                f"Encoding error: {e}. Check your API key contains only "
                "standard ASCII characters and re-save the venue in Settings."
            ) from e

    async def get_balances(self) -> list[Balance]:
        bal = await self._call(self.client.fetch_balance)
        out: list[Balance] = []
        for currency, amounts in (bal.get("total") or {}).items():
            total = float(amounts or 0)
            if total == 0:
                continue
            available = float((bal.get("free") or {}).get(currency) or 0)
            out.append(Balance(currency=currency, total=total, available=available))
        return out

    async def get_positions(self) -> list[Position]:
        if not self.client.has.get("fetchPositions"):
            return []  # spot exchanges don't have positions
        raw = await self._call(self.client.fetch_positions)
        out: list[Position] = []
        for p in raw or []:
            contracts = float(p.get("contracts") or 0)
            if contracts == 0:
                continue
            side = p.get("side") or "long"
            qty = contracts if side == "long" else -contracts
            out.append(
                Position(
                    symbol=p.get("symbol") or "",
                    quantity=qty,
                    entry_price=float(p.get("entryPrice") or 0),
                    unrealized_pnl=float(p.get("unrealizedPnl") or 0),
                    leverage=float(p.get("leverage") or 0) or None,
                    liquidation_price=float(p.get("liquidationPrice") or 0) or None,
                )
            )
        return out

    async def get_ticker(self, symbol: str) -> Ticker:
        t = await self._call(self.client.fetch_ticker, symbol)
        return Ticker(
            symbol=symbol,
            last=float(t.get("last") or 0),
            bid=float(t.get("bid") or 0) or None,
            ask=float(t.get("ask") or 0) or None,
        )

    async def get_candles(self, symbol: str, timeframe: str, lookback: int) -> list[Candle]:
        ohlcv = await self._call(self.client.fetch_ohlcv, symbol, timeframe, None, lookback)
        return [
            Candle(
                ts=int(row[0]) // 1000,
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in ohlcv or []
        ]

    async def get_symbol_info(self, symbol: str) -> SymbolMeta:
        await self._call(self.client.load_markets)
        market = self.client.market(symbol)
        is_perp = bool(market.get("contract") or market.get("swap"))
        limits = market.get("limits") or {}
        precision = market.get("precision") or {}
        return SymbolMeta(
            symbol=symbol,
            asset_class="crypto_perp" if is_perp else "crypto_spot",
            tick_size=float(precision.get("price") or 0) or 0.01,
            lot_size=float(precision.get("amount") or 0) or 0.0001,
            min_notional=float((limits.get("cost") or {}).get("min") or 5.0),
            max_leverage=float((market.get("info") or {}).get("maxLeverage") or (1.0 if not is_perp else 20.0)),
            extra=market,
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
        if leverage is not None and self.client.has.get("setLeverage"):
            try:
                await self._call(self.client.set_leverage, leverage, symbol)
            except Exception as e:
                logging.warning("CCXT set_leverage failed on %s: %s", self.exchange_id, e)

        params: dict = {}
        if stop_loss is not None:
            params["stopLossPrice"] = stop_loss
        if take_profit is not None:
            params["takeProfitPrice"] = take_profit

        result = await self._call(
            self.client.create_order,
            symbol,
            order_type,
            side,
            quantity,
            price,
            params,
        )
        return Order(
            order_id=str(result.get("id") or ""),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status=str(result.get("status") or "open"),
            filled_quantity=float(result.get("filled") or 0),
            avg_fill_price=float(result.get("average") or 0) or None,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        try:
            await self._call(self.client.cancel_order, order_id, symbol)
            return True
        except Exception as e:
            logging.warning("CCXT cancel_order failed: %s", e)
            return False

    async def close_position(self, symbol: str, quantity: float | None = None) -> Order | None:
        positions = await self.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)
        if not pos:
            return None
        qty = quantity if quantity is not None else abs(pos.quantity)
        side: OrderSide = "sell" if pos.quantity > 0 else "buy"
        return await self.place_order(symbol, side, qty, order_type="market")
