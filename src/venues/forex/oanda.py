"""OANDA v20 REST venue adapter for forex (and OANDA CFDs).

Uses OANDA's REST API directly via `requests` so the only hard dep is what
we already have. `oandapyV20` is supported under the `oanda` extra for
richer ergonomics (streaming, pricing), but not required.

Symbol format follows OANDA's "BASE_QUOTE" e.g. "EUR_USD", "GBP_JPY".
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import os
import requests

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

_GRANULARITY = {
    "1m": "M1",
    "5m": "M5",
    "15m": "M15",
    "30m": "M30",
    "1h": "H1",
    "4h": "H4",
    "1d": "D",
}


class OandaVenue(Venue):
    name = "oanda"
    asset_class = "forex"

    def __init__(self):
        self.token      = os.environ.get("OANDA_API_TOKEN")  or CONFIG.get("oanda_api_token")  or ""
        self.account_id = os.environ.get("OANDA_ACCOUNT_ID") or CONFIG.get("oanda_account_id") or ""
        env = (os.environ.get("OANDA_ENV") or CONFIG.get("oanda_env") or "practice").lower()
        if env == "live":
            self.base_url = "https://api-fxtrade.oanda.com"
        else:
            self.base_url = "https://api-fxpractice.oanda.com"
        self.is_paper = False
        if not self.token or not self.account_id:
            logging.warning(
                "OANDA credentials missing — set OANDA_API_TOKEN and OANDA_ACCOUNT_ID."
            )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict:
        def _do():
            r = requests.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                params=params or {},
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        return await asyncio.to_thread(_do)

    async def _post(self, path: str, body: dict) -> dict:
        def _do():
            r = requests.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=body,
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        return await asyncio.to_thread(_do)

    async def _put(self, path: str, body: dict | None = None) -> dict:
        def _do():
            r = requests.put(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=body or {},
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        return await asyncio.to_thread(_do)

    async def get_balances(self) -> list[Balance]:
        data = await self._get(f"/v3/accounts/{self.account_id}/summary")
        acct = data.get("account") or {}
        return [
            Balance(
                currency=acct.get("currency") or "USD",
                total=float(acct.get("balance") or 0),
                available=float(acct.get("marginAvailable") or acct.get("balance") or 0),
            )
        ]

    async def get_positions(self) -> list[Position]:
        data = await self._get(f"/v3/accounts/{self.account_id}/openPositions")
        out: list[Position] = []
        for p in data.get("positions") or []:
            long_units = float((p.get("long") or {}).get("units") or 0)
            short_units = float((p.get("short") or {}).get("units") or 0)
            qty = long_units + short_units  # short_units is negative in OANDA
            if qty == 0:
                continue
            side = p.get("long") if long_units != 0 else p.get("short")
            out.append(
                Position(
                    symbol=p.get("instrument") or "",
                    quantity=qty,
                    entry_price=float((side or {}).get("averagePrice") or 0),
                    unrealized_pnl=float((side or {}).get("unrealizedPL") or 0),
                )
            )
        return out

    async def get_ticker(self, symbol: str) -> Ticker:
        data = await self._get(
            f"/v3/accounts/{self.account_id}/pricing",
            params={"instruments": symbol},
        )
        prices = data.get("prices") or []
        if not prices:
            return Ticker(symbol=symbol, last=0.0)
        p = prices[0]
        bid = float((p.get("bids") or [{}])[0].get("price") or 0)
        ask = float((p.get("asks") or [{}])[0].get("price") or 0)
        return Ticker(symbol=symbol, last=(bid + ask) / 2 if bid and ask else bid or ask, bid=bid, ask=ask)

    async def get_candles(self, symbol: str, timeframe: str, lookback: int) -> list[Candle]:
        gran = _GRANULARITY.get(timeframe, "M5")
        data = await self._get(
            f"/v3/instruments/{symbol}/candles",
            params={"granularity": gran, "count": lookback, "price": "M"},
        )
        out: list[Candle] = []
        for c in data.get("candles") or []:
            if not c.get("complete"):
                continue
            mid = c.get("mid") or {}
            from datetime import datetime
            ts = int(datetime.fromisoformat(c["time"].replace("Z", "+00:00")).timestamp())
            out.append(
                Candle(
                    ts=ts,
                    open=float(mid.get("o") or 0),
                    high=float(mid.get("h") or 0),
                    low=float(mid.get("l") or 0),
                    close=float(mid.get("c") or 0),
                    volume=float(c.get("volume") or 0),
                )
            )
        return out

    async def get_symbol_info(self, symbol: str) -> SymbolMeta:
        data = await self._get(
            f"/v3/accounts/{self.account_id}/instruments",
            params={"instruments": symbol},
        )
        instruments = data.get("instruments") or []
        info = instruments[0] if instruments else {}
        # OANDA displayPrecision = decimal places of the tick
        display_precision = int(info.get("displayPrecision") or 5)
        tick_size = 10 ** -display_precision
        pip_loc = int(info.get("pipLocation") or -4)
        pip_value = 10 ** pip_loc
        return SymbolMeta(
            symbol=symbol,
            asset_class="forex",
            tick_size=tick_size,
            lot_size=1.0,  # OANDA units are fractional
            min_notional=1.0,
            max_leverage=float(info.get("marginRate") and 1 / float(info["marginRate"]) or 30.0),
            pip_value=pip_value,
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
        if getattr(self, "is_paper", False):
            import uuid as _uuid
            return Order(
                order_id=str(_uuid.uuid4()),
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price or 0.0,
                status="filled",
                filled_quantity=quantity,
            )
        units = quantity if side == "buy" else -quantity
        order_body: dict = {
            "instrument": symbol,
            "units": str(units),
            "timeInForce": "FOK" if order_type == "market" else "GTC",
            "positionFill": "DEFAULT",
        }
        if order_type == "market":
            order_body["type"] = "MARKET"
        elif order_type == "limit":
            if price is None:
                raise ValueError("limit order requires price")
            order_body["type"] = "LIMIT"
            order_body["price"] = f"{price}"
        else:
            raise ValueError(f"OANDA adapter doesn't yet support order_type={order_type}")

        if stop_loss is not None:
            order_body["stopLossOnFill"] = {"price": f"{stop_loss}"}
        if take_profit is not None:
            order_body["takeProfitOnFill"] = {"price": f"{take_profit}"}

        resp = await self._post(
            f"/v3/accounts/{self.account_id}/orders",
            {"order": order_body},
        )
        fill = resp.get("orderFillTransaction") or {}
        order_id = str(fill.get("id") or resp.get("orderCreateTransaction", {}).get("id") or uuid.uuid4())
        return Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="filled" if fill else "open",
            filled_quantity=abs(float(fill.get("units") or 0)) if fill else 0.0,
            avg_fill_price=float(fill.get("price") or 0) or None,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        try:
            await self._put(f"/v3/accounts/{self.account_id}/orders/{order_id}/cancel")
            return True
        except Exception as e:
            logging.warning("OANDA cancel_order failed: %s", e)
            return False

    async def close_position(self, symbol: str, quantity: float | None = None) -> Order | None:
        positions = await self.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)
        if not pos:
            return None
        body: dict = {}
        if pos.quantity > 0:
            body["longUnits"] = "ALL" if quantity is None else str(quantity)
        else:
            body["shortUnits"] = "ALL" if quantity is None else str(quantity)
        try:
            resp = await self._put(
                f"/v3/accounts/{self.account_id}/positions/{symbol}/close",
                body,
            )
            fill = (
                resp.get("longOrderFillTransaction")
                or resp.get("shortOrderFillTransaction")
                or {}
            )
            return Order(
                order_id=str(fill.get("id") or uuid.uuid4()),
                symbol=symbol,
                side="sell" if pos.quantity > 0 else "buy",
                order_type="market",
                quantity=abs(float(fill.get("units") or pos.quantity)),
                avg_fill_price=float(fill.get("price") or 0) or None,
                status="filled",
            )
        except Exception as e:
            logging.warning("OANDA close_position failed: %s", e)
            return None
