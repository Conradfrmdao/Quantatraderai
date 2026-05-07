"""Dedicated Binance venue adapter.

Supports both:
  - Binance Spot (via CCXT ccxt.binance)
  - Binance USD-M Futures / USDT perpetuals (via CCXT ccxt.binanceusdm)

Set BINANCE_MARKET=spot | futures (default: futures).
Futures account uses USDT as collateral; spot account uses the quote asset.

BINANCE_API_KEY / BINANCE_API_SECRET must be set in .env.
Create the key with Trade permission only; withdrawals DISABLED; IP-allowlisted.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from src.config_loader import CONFIG
from src.venues.base import Venue
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

_CCXT_TIMEFRAMES = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}


class BinanceVenue(Venue):
    """Binance venue adapter (spot or USD-M futures).

    Uses CCXT under the hood but configured specifically for Binance with
    separate exchange IDs for spot vs. futures so the right endpoints and
    margin semantics are used.
    """

    def __init__(self, market: str | None = None):
        try:
            import ccxt  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "ccxt is required for BinanceVenue. Run `poetry install`."
            ) from e

        # Read live from os.environ so _inject_venue_env changes are picked up.
        # CONFIG is a static snapshot from startup; os.environ reflects injected creds.
        market = (market or os.environ.get("BINANCE_MARKET") or CONFIG.get("binance_market") or "futures").lower()
        self._market = market

        def _ascii(s: str) -> str:
            """Strip non-ASCII characters from API keys to prevent latin-1 encode errors."""
            return s.encode("ascii", errors="ignore").decode("ascii").strip()

        _raw_key = os.environ.get("BINANCE_API_KEY") or CONFIG.get("binance_api_key") or ""
        _raw_sec = os.environ.get("BINANCE_API_SECRET") or CONFIG.get("binance_api_secret") or ""
        _clean_key = _ascii(_raw_key)
        _clean_sec = _ascii(_raw_sec)

        cfg: dict[str, Any] = {
            "apiKey": _clean_key,
            "secret": _clean_sec,
            "enableRateLimit": True,
        }

        # Diagnostic — log key shape without revealing value
        logging.info(
            "Binance API key: len=%d first3=%s last3=%s | secret: len=%d",
            len(_clean_key), _clean_key[:3] if _clean_key else "???",
            _clean_key[-3:] if _clean_key else "???", len(_clean_sec),
        )
        if len(_clean_key) < 10:
            logging.warning("Binance API key looks too short (len=%d) — may be missing or corrupt", len(_clean_key))
        if len(_clean_sec) < 10:
            logging.warning("Binance API secret looks too short (len=%d) — may be missing or corrupt", len(_clean_sec))

        sandbox_raw = os.environ.get("BINANCE_SANDBOX") or str(CONFIG.get("binance_sandbox", "true"))
        sandbox = sandbox_raw.lower() in {"1", "true", "yes"}

        if market == "futures":
            self.client = ccxt.binanceusdm(cfg)  # USD-M perpetuals
            self.asset_class: AssetClass = "crypto_perp"
            self.name = "binance:futures"
        else:
            self.client = ccxt.binance(cfg)       # Spot
            self.asset_class = "crypto_spot"
            self.name = "binance:spot"

        # Paper trading: use live endpoint for read-only price/balance data.
        # Real order placement is blocked at the venue level when is_paper=True —
        # server.py also guards this, but double-gating here prevents accidents
        # when BinanceVenue is used outside the server (scripts, tests, etc.).
        #
        # Do NOT call client.set_sandbox_mode():
        #   - Futures testnet (testnet.binancefuture.com) requires separate testnet keys
        #   - Spot testnet requires separate testnet keys
        # Setting sandbox mode with live keys causes -2008 "Invalid API key".
        self.is_paper = sandbox
        if sandbox:
            logging.info(
                "Binance %s paper mode: price data from live endpoint; "
                "place_order() is a no-op (no real orders will be sent).", market
            )

    # ---- helpers --------------------------------------------------------

    async def _call(self, fn, *args, **kwargs):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except UnicodeEncodeError as e:
            # This happens when the API key/secret contains non-ASCII characters,
            # or when Binance returns an error message in a non-Latin script.
            raise RuntimeError(
                f"Encoding error communicating with Binance: {e}. "
                "Check that your API key and secret contain only standard ASCII "
                "characters (no spaces, Cyrillic, Chinese, or special symbols). "
                "Re-generate the key in Binance if unsure."
            ) from e

    async def _load_markets(self):
        if not self.client.markets:
            await self._call(self.client.load_markets)

    # ---- Venue interface ------------------------------------------------

    async def get_balances(self) -> list[Balance]:
        bal = await self._call(self.client.fetch_balance)
        out: list[Balance] = []
        for currency, total in (bal.get("total") or {}).items():
            if not total:
                continue
            free = float((bal.get("free") or {}).get(currency) or 0)
            out.append(Balance(currency=currency, total=float(total), available=free))
        return out

    async def get_positions(self) -> list[Position]:
        if self._market == "spot":
            return []  # spot has no derivative positions
        if not self.client.has.get("fetchPositions"):
            return []
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
                    leverage=float(p.get("leverage") or 1) or None,
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
        tf = _CCXT_TIMEFRAMES.get(timeframe, "1h")
        ohlcv = await self._call(self.client.fetch_ohlcv, symbol, tf, None, lookback)
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
        await self._load_markets()
        market = self.client.market(symbol)
        is_perp = bool(market.get("swap") or market.get("contract"))
        limits = market.get("limits") or {}
        precision = market.get("precision") or {}
        info = market.get("info") or {}
        return SymbolMeta(
            symbol=symbol,
            asset_class="crypto_perp" if is_perp else "crypto_spot",
            tick_size=float(precision.get("price") or 0.01),
            lot_size=float(precision.get("amount") or 0.001),
            min_notional=float((limits.get("cost") or {}).get("min") or 5.0),
            max_leverage=float(info.get("maxLeverage") or (1.0 if not is_perp else 20.0)),
            funding_rate=None,  # fetch via fetch_funding_rate if needed
            extra=info,
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
        if self.is_paper:
            logging.info(
                "Binance PAPER: simulated %s %s qty=%s price=%s (no real order sent)",
                side.upper(), symbol, quantity, price,
            )
            return Order(
                order_id="paper",
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status="filled",
                filled_quantity=quantity,
                avg_fill_price=price,
            )

        # Set leverage on futures before placing
        if self._market == "futures" and leverage and self.client.has.get("setLeverage"):
            try:
                await self._call(self.client.set_leverage, leverage, symbol)
            except Exception as e:
                logging.warning("Binance set_leverage(%s): %s", symbol, e)

        params: dict = {}
        if stop_loss is not None:
            params["stopLossPrice"] = stop_loss
        if take_profit is not None:
            params["takeProfitPrice"] = take_profit

        result = await self._call(
            self.client.create_order,
            symbol, order_type, side, quantity, price, params,
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
            logging.warning("Binance cancel_order failed: %s", e)
            return False

    async def close_position(self, symbol: str, quantity: float | None = None) -> Order | None:
        if self.is_paper:
            logging.info("Binance PAPER: simulated close_position %s qty=%s", symbol, quantity)
            return Order(
                order_id="paper",
                symbol=symbol,
                side="sell",
                order_type="market",
                quantity=quantity or 0,
                status="filled",
                filled_quantity=quantity or 0,
            )
        if self._market == "spot":
            # Spot: check balance and sell
            bal = await self.get_balances()
            base = symbol.split("/")[0] if "/" in symbol else symbol.replace("USDT", "")
            holding = next((b for b in bal if b.currency == base), None)
            if not holding or holding.available <= 0:
                return None
            qty = min(quantity or holding.available, holding.available)
            return await self.place_order(symbol, "sell", qty, order_type="market")
        # Futures: close via position
        positions = await self.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)
        if not pos:
            return None
        qty = quantity if quantity is not None else abs(pos.quantity)
        side: OrderSide = "sell" if pos.quantity > 0 else "buy"
        params = {"reduceOnly": True}
        try:
            result = await self._call(
                self.client.create_order, symbol, "market", side, qty, None, params
            )
            return Order(
                order_id=str(result.get("id") or ""),
                symbol=symbol, side=side, order_type="market",
                quantity=qty, status="filled",
                filled_quantity=float(result.get("filled") or qty),
            )
        except Exception as e:
            logging.error("Binance close_position failed: %s", e)
            return None
