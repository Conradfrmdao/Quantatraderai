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
import time

from src.config_loader import CONFIG
from src.venues.base import Venue
from src.venues.crypto.spot_portfolio import (
    SPOT_BALANCE_CACHE_TTL_S,
    base_currency_from_symbol,
    build_balances_from_ccxt_payload,
    is_cash_equivalent,
    pick_best_spot_symbol,
)
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
    asset_class = "crypto_spot"  # overridden in __init__ based on CCXT_MARKET env

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

        market_pref = (os.environ.get("CCXT_MARKET") or CONFIG.get("ccxt_market") or "spot").lower()
        options: dict[str, str] = {}
        if market_pref in ("futures", "perpetual", "perp", "swap"):
            # Best-effort default across the major derivatives exchanges we expose.
            options["defaultType"] = "swap" if exchange_id in {"bybit", "okx", "bitget", "gate", "mexc", "kucoin"} else "future"
        else:
            options["defaultType"] = "spot"

        exchange_cls = getattr(ccxt, exchange_id)
        self.client = exchange_cls({
            "apiKey": _ascii(os.environ.get("CCXT_API_KEY") or CONFIG.get("ccxt_api_key") or ""),
            "secret": _ascii(os.environ.get("CCXT_API_SECRET") or CONFIG.get("ccxt_api_secret") or ""),
            "enableRateLimit": True,
            "options": options,
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

        # Detect whether this instance handles perps or spot so the RiskManager
        # loads the correct risk.yaml override block.  CCXT_MARKET=futures (or
        # "perpetual") means perps; anything else (or unset) means spot.
        if market_pref in ("futures", "perpetual", "perp", "swap"):
            self.asset_class = "crypto_perp"
        else:
            self.asset_class = "crypto_spot"
        self._market_pref = market_pref
        self.is_paper = False
        self._spot_balances_cache: list[Balance] = []
        self._spot_balances_at: float = 0.0
        self._spot_cost_basis: dict[str, dict[str, float]] = {}

    # CCXT's sync calls wrapped in to_thread keep the adapter async-compatible.
    async def _call(self, fn, *args, **kwargs):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except UnicodeEncodeError as e:
            raise RuntimeError(
                f"Encoding error: {e}. Check your API key contains only "
                "standard ASCII characters and re-save the venue in Settings."
            ) from e

    async def _load_markets(self):
        if not getattr(self.client, "markets", None):
            await self._call(self.client.load_markets)

    async def _get_spot_balances(self, *, force: bool = False) -> list[Balance]:
        now = time.monotonic()
        if (
            not force
            and self._spot_balances_cache
            and (now - self._spot_balances_at) < SPOT_BALANCE_CACHE_TTL_S
        ):
            return list(self._spot_balances_cache)

        payload = await self._call(self.client.fetch_balance)
        balances = build_balances_from_ccxt_payload(payload)
        self._spot_balances_cache = balances
        self._spot_balances_at = now
        return list(balances)

    def _remember_spot_cost_basis(self, base_currency: str, quantity: float, entry_price: float) -> None:
        base = str(base_currency or "").upper()
        qty = float(quantity or 0)
        price = float(entry_price or 0)
        if not base or qty <= 0 or price <= 0:
            self._spot_cost_basis.pop(base, None)
            return
        self._spot_cost_basis[base] = {"quantity": qty, "entry_price": price}

    async def _sync_spot_cost_basis_after_fill(self, symbol: str, side: str, fill_price: float) -> None:
        base = base_currency_from_symbol(symbol)
        previous = self._spot_cost_basis.get(base) or {}
        previous_qty = float(previous.get("quantity") or 0.0)
        previous_entry = float(previous.get("entry_price") or 0.0)

        balances = await self._get_spot_balances(force=True)
        holding = next((b for b in balances if str(b.currency).upper() == base), None)
        actual_qty = float(getattr(holding, "total", 0.0) or 0.0)

        if actual_qty <= 0:
            self._spot_cost_basis.pop(base, None)
            return

        basis_price = float(fill_price or previous_entry or 0.0)
        if side == "buy" and previous_qty > 0 and previous_entry > 0:
            added_qty = max(actual_qty - previous_qty, 0.0)
            if added_qty > 0 and basis_price > 0:
                basis_price = ((previous_qty * previous_entry) + (added_qty * basis_price)) / actual_qty
            else:
                basis_price = previous_entry
        elif previous_entry > 0:
            basis_price = previous_entry

        if basis_price <= 0:
            basis_price = float(fill_price or 0.0)
        self._remember_spot_cost_basis(base, actual_qty, basis_price)

    async def _build_spot_positions(self) -> list[Position]:
        balances = await self._get_spot_balances()
        await self._load_markets()

        holdings = [b for b in balances if float(b.total or 0) > 0 and not is_cash_equivalent(b.currency)]
        if not holdings:
            self._spot_cost_basis = {}
            return []

        ticker_tasks: dict[str, asyncio.Task] = {}
        symbol_by_base: dict[str, str] = {}
        for balance in holdings:
            base = str(balance.currency or "").upper()
            symbol = pick_best_spot_symbol(self.client.markets or {}, base)
            if not symbol:
                continue
            symbol_by_base[base] = symbol
            ticker_tasks[base] = asyncio.create_task(self.get_ticker(symbol))

        positions: list[Position] = []
        next_basis: dict[str, dict[str, float]] = {}
        for balance in holdings:
            base = str(balance.currency or "").upper()
            symbol = symbol_by_base.get(base)
            if not symbol:
                continue

            ticker = await ticker_tasks[base]
            current_price = float(getattr(ticker, "last", 0) or 0)
            if current_price <= 0:
                continue

            quantity = float(balance.total or 0)
            cached = self._spot_cost_basis.get(base) or {}
            entry_price = float(cached.get("entry_price") or current_price)
            unrealized_pnl = (current_price - entry_price) * quantity
            next_basis[base] = {"quantity": quantity, "entry_price": entry_price}
            positions.append(
                Position(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=entry_price,
                    unrealized_pnl=unrealized_pnl,
                    current_price=current_price,
                )
            )

        self._spot_cost_basis = next_basis
        return positions

    async def get_balances(self) -> list[Balance]:
        if self.asset_class == "crypto_spot":
            return await self._get_spot_balances()

        bal = await self._call(self.client.fetch_balance)
        return build_balances_from_ccxt_payload(bal)

    async def get_positions(self) -> list[Position]:
        if self.asset_class == "crypto_spot":
            return await self._build_spot_positions()
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
        order = Order(
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
        if self.asset_class == "crypto_spot":
            fill_price = float(order.avg_fill_price or price or 0.0)
            await self._sync_spot_cost_basis_after_fill(symbol, side, fill_price)
        return order

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
