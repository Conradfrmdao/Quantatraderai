"""Hyperliquid venue adapter — wraps the legacy `HyperliquidAPI` facade.

The existing Hyperliquid code in `src/trading/hyperliquid_api.py` is kept as
the low-level SDK wrapper; this class exposes it through the `Venue`
interface so the agent and backtester can treat Hyperliquid like any other
exchange.
"""

from __future__ import annotations

from src.trading.hyperliquid_api import HyperliquidAPI
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


class HyperliquidVenue(Venue):
    name = "hyperliquid"
    asset_class = "crypto_perp"

    def __init__(self, api: HyperliquidAPI | None = None, is_paper: bool | None = None):
        self.api = api or HyperliquidAPI()
        self.is_paper = bool(is_paper) if is_paper is not None else False

    async def get_balances(self) -> list[Balance]:
        state = await self.api.get_user_state()
        margin = state.get("marginSummary", {}) if isinstance(state, dict) else {}
        total = float(margin.get("accountValue") or 0)
        # Hyperliquid uses USDC as margin currency
        return [Balance(currency="USDC", total=total, available=total)]

    async def get_positions(self) -> list[Position]:
        state = await self.api.get_user_state()
        out: list[Position] = []
        for p in (state.get("assetPositions") or []):
            pos = p.get("position") or {}
            size = float(pos.get("szi") or 0)
            if size == 0:
                continue
            out.append(
                Position(
                    symbol=pos.get("coin") or "",
                    quantity=size,
                    entry_price=float(pos.get("entryPx") or 0),
                    unrealized_pnl=float(pos.get("unrealizedPnl") or 0),
                    leverage=float(pos.get("leverage", {}).get("value")) if pos.get("leverage") else None,
                    liquidation_price=float(pos.get("liquidationPx") or 0) or None,
                )
            )
        return out

    async def get_ticker(self, symbol: str) -> Ticker:
        price = await self.api.get_current_price(symbol)
        return Ticker(symbol=symbol, last=float(price or 0))

    async def get_candles(self, symbol: str, timeframe: str, lookback: int) -> list[Candle]:
        raw = await self.api.get_candles(symbol, interval=timeframe, count=lookback)
        out: list[Candle] = []
        for c in raw or []:
            # Hyperliquid candle keys: t (open time ms), o, h, l, c, v
            out.append(
                Candle(
                    ts=int(c.get("t", 0)) // 1000,
                    open=float(c.get("o", 0)),
                    high=float(c.get("h", 0)),
                    low=float(c.get("l", 0)),
                    close=float(c.get("c", 0)),
                    volume=float(c.get("v", 0)),
                )
            )
        return out

    async def get_symbol_info(self, symbol: str) -> SymbolMeta:
        meta = await self.api.get_meta_and_ctxs()
        # meta is (universe, ctxs) tuple-like; best-effort lookup
        universe = meta[0].get("universe") if isinstance(meta, (list, tuple)) and len(meta) > 0 else []
        info = next((u for u in (universe or []) if u.get("name") == symbol), {})
        return SymbolMeta(
            symbol=symbol,
            asset_class="crypto_perp",
            tick_size=float(info.get("tickSize") or 0.01),
            lot_size=float(info.get("szDecimals") and 10 ** -int(info["szDecimals"]) or 0.0001),
            min_notional=10.0,  # Hyperliquid minimum
            max_leverage=float(info.get("maxLeverage") or 50),
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
            import uuid
            return Order(
                order_id=str(uuid.uuid4()),
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status="filled",
                filled_quantity=quantity,
            )
        is_buy = side == "buy"
        if order_type == "market":
            result = (
                await self.api.place_buy_order(symbol, quantity)
                if is_buy
                else await self.api.place_sell_order(symbol, quantity)
            )
        elif order_type == "limit":
            if price is None:
                raise ValueError("limit order requires price")
            result = (
                await self.api.place_limit_buy(symbol, quantity, price)
                if is_buy
                else await self.api.place_limit_sell(symbol, quantity, price)
            )
        else:
            raise ValueError(f"Hyperliquid adapter doesn't yet support order_type={order_type}")

        oids = self.api.extract_oids(result) or {}
        order_id = str(oids.get("resting") or oids.get("filled") or "")

        if stop_loss is not None:
            await self.api.place_stop_loss(symbol, is_buy, quantity, stop_loss)
        if take_profit is not None:
            await self.api.place_take_profit(symbol, is_buy, quantity, take_profit)

        return Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        try:
            await self.api.cancel_order(symbol, int(order_id))
            return True
        except Exception:
            return False

    async def close_position(self, symbol: str, quantity: float | None = None) -> Order | None:
        positions = await self.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)
        if not pos:
            return None
        qty = quantity if quantity is not None else abs(pos.quantity)
        side: OrderSide = "sell" if pos.quantity > 0 else "buy"
        return await self.place_order(symbol, side, qty, order_type="market")
