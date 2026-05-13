"""Polymarket CLOB venue adapter.

Polymarket runs a Central Limit Order Book on Polygon (chain_id=137). Markets
are binary outcomes — every market has two ERC-1155 token IDs (YES / NO);
prices are probabilities in (0.0, 1.0).

Setup:
  POLYMARKET_ETH_PRIVATE_KEY  — Ethereum private key from a dedicated trading wallet
                                (NEVER paste your main wallet — use a fresh one).
                                Used once on init to derive L2 API credentials.
  POLYMARKET_CHAIN_ID         — usually 137 (Polygon mainnet)
  POLYMARKET_HOST             — default https://clob.polymarket.com
  POLYMARKET_IS_PAPER         — "true" → paper mode, no real trades

Symbol format:
  - Token IDs are long decimal/hex strings.
  - Adapter accepts either a raw token_id or a market slug like
    "will-bitcoin-hit-100k-by-end-of-2025-yes" — the latter is resolved via
    `client.get_markets()` lookup (cached for 5 minutes).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

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

logger = logging.getLogger("quantatraderai.venues.polymarket")


class PolymarketVenue(Venue):
    name = "polymarket"
    asset_class: AssetClass = "prediction"

    def __init__(self):
        eth_key   = os.environ.get("POLYMARKET_ETH_PRIVATE_KEY") or ""
        chain_id  = int(os.environ.get("POLYMARKET_CHAIN_ID") or 137)
        host      = os.environ.get("POLYMARKET_HOST") or "https://clob.polymarket.com"
        is_paper_str = os.environ.get("POLYMARKET_IS_PAPER", "false").lower()
        self._is_paper = is_paper_str in {"1", "true", "yes"}

        if not eth_key:
            raise RuntimeError(
                "Polymarket requires POLYMARKET_ETH_PRIVATE_KEY (a dedicated trading "
                "wallet's private key). Use Connect Wallet for the secure flow."
            )

        # Lazy import — keeps the optional SDK out of the import-time critical path.
        try:
            from py_clob_client.client import ClobClient  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "py-clob-client is required for PolymarketVenue. "
                "Install with: pip install py-clob-client"
            ) from e

        # L1 init: derive L2 API creds from the ETH private key (idempotent — safe
        # to call repeatedly; returns the same creds for the same wallet).
        self._client = ClobClient(host=host, chain_id=chain_id, key=eth_key)
        try:
            creds = self._client.create_or_derive_api_creds()
            self._client.set_api_creds(creds)
        except Exception as e:
            logger.warning("Polymarket L2 cred derivation failed: %s", e)
            raise

        self._market_cache: dict[str, dict] = {}
        self._market_cache_ts: float = 0.0

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _to_thread(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def _resolve_token_id(self, symbol: str) -> str:
        """Accept either a raw token_id or a market slug; return the YES token_id."""
        # Already-numeric or 0x-prefixed → assume token_id
        if symbol.isdigit() or symbol.startswith("0x"):
            return symbol

        # Lazy-load markets (5min cache)
        if not self._market_cache or time.monotonic() - self._market_cache_ts > 300:
            try:
                resp = await self._to_thread(self._client.get_markets)
                markets = resp.get("data", []) if isinstance(resp, dict) else (resp or [])
                self._market_cache = {m.get("market_slug", ""): m for m in markets if m.get("market_slug")}
                self._market_cache_ts = time.monotonic()
            except Exception as e:
                logger.warning("Polymarket get_markets failed: %s", e)
                raise RuntimeError(f"Cannot resolve Polymarket symbol {symbol!r}: {e}")

        match = self._market_cache.get(symbol.lower())
        if not match:
            raise RuntimeError(f"Polymarket: market slug {symbol!r} not found")
        # Pick YES token by default
        tokens = match.get("tokens", [])
        yes_token = next((t for t in tokens if t.get("outcome", "").lower() == "yes"), tokens[0] if tokens else None)
        if not yes_token:
            raise RuntimeError(f"Polymarket: no tokens in market {symbol!r}")
        return yes_token["token_id"]

    # ── Required Venue interface ──────────────────────────────────────────────

    async def get_balances(self) -> list[Balance]:
        try:
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType  # type: ignore
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            resp = await self._to_thread(self._client.get_balance_allowance, params)
            usdc_balance = float(resp.get("balance", 0)) / 1e6  # USDC has 6 decimals on Polygon
            return [Balance(currency="USDC", total=usdc_balance, available=usdc_balance)]
        except Exception as e:
            logger.warning("Polymarket get_balances failed: %s", e)
            return [Balance(currency="USDC", total=0, available=0)]

    async def get_positions(self) -> list[Position]:
        # Polymarket "positions" = open orders + filled token holdings.
        # The CLOB exposes open orders directly; filled positions require
        # querying token_id balances via get_balance_allowance(token_id).
        try:
            resp = await self._to_thread(self._client.get_orders)
            orders = resp if isinstance(resp, list) else resp.get("data", [])
            positions: list[Position] = []
            for o in orders:
                token_id  = str(o.get("asset_id", o.get("token_id", "")))
                side      = o.get("side", "BUY").upper()
                size      = float(o.get("size_matched", 0) or o.get("original_size", 0) or 0)
                price     = float(o.get("price", 0) or 0)
                if size <= 0 or not token_id:
                    continue
                qty = size if side == "BUY" else -size
                positions.append(Position(symbol=token_id, quantity=qty, entry_price=price))
            return positions
        except Exception as e:
            logger.warning("Polymarket get_positions failed: %s", e)
            return []

    async def get_ticker(self, symbol: str) -> Ticker:
        token_id = await self._resolve_token_id(symbol)
        try:
            last = await self._to_thread(self._client.get_last_trade_price, token_id)
            last_price = float(last.get("price", 0)) if isinstance(last, dict) else float(last or 0)
            bid = await self._to_thread(self._client.get_price, token_id, "BUY")
            ask = await self._to_thread(self._client.get_price, token_id, "SELL")
            bid_p = float(bid.get("price", 0)) if isinstance(bid, dict) else float(bid or 0)
            ask_p = float(ask.get("price", 0)) if isinstance(ask, dict) else float(ask or 0)
            return Ticker(symbol=token_id, last=last_price, bid=bid_p, ask=ask_p)
        except Exception as e:
            logger.warning("Polymarket get_ticker failed: %s", e)
            return Ticker(symbol=token_id, last=0.5)  # 50/50 default

    async def get_candles(self, symbol: str, timeframe: str, lookback: int) -> list[Candle]:
        # Polymarket has no candle API; we approximate from last_trade_price snapshots.
        # In paper mode just return a flat-line series so the agent has something to chew on.
        token_id = await self._resolve_token_id(symbol)
        try:
            last = await self._to_thread(self._client.get_last_trade_price, token_id)
            last_price = float(last.get("price", 0.5)) if isinstance(last, dict) else 0.5
        except Exception:
            last_price = 0.5

        now = int(time.time())
        interval_secs = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}.get(timeframe, 3600)
        return [
            Candle(ts=now - i * interval_secs, open=last_price, high=last_price,
                   low=last_price, close=last_price, volume=0.0)
            for i in range(lookback, 0, -1)
        ]

    async def get_symbol_info(self, symbol: str) -> SymbolMeta:
        token_id = await self._resolve_token_id(symbol)
        return SymbolMeta(
            symbol=token_id, asset_class=self.asset_class,
            tick_size=0.01,         # Polymarket prices in $0.01 increments
            lot_size=1.0,           # whole shares
            min_notional=1.0,       # $1 minimum
            max_leverage=1.0,       # spot only — no leverage
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
        token_id = await self._resolve_token_id(symbol)
        side_str = "BUY" if side == "buy" else "SELL"

        if self._is_paper:
            mid = (await self.get_ticker(symbol)).last or 0.5
            return Order(
                order_id=f"paper-{int(time.time()*1000)}",
                symbol=token_id, side=side, order_type=order_type,
                quantity=quantity, price=mid, status="paper",
                filled_quantity=quantity, avg_fill_price=mid,
            )

        try:
            from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OrderType as PolyOrderType  # type: ignore

            if order_type == "market":
                # Market BUY: amount = USDC; Market SELL: amount = shares
                # We standardise on `quantity` = shares; for buys multiply by current price
                # for the SDK.
                if side == "buy":
                    px = price or (await self.get_ticker(symbol)).last or 0.5
                    args = MarketOrderArgs(token_id=token_id, amount=quantity * px, side=side_str)
                else:
                    args = MarketOrderArgs(token_id=token_id, amount=quantity, side=side_str)
                signed = await self._to_thread(self._client.create_market_order, args)
                resp = await self._to_thread(self._client.post_order, signed, PolyOrderType.FOK)
            else:
                if price is None:
                    raise ValueError("Polymarket limit orders require an explicit price (0–1)")
                args = OrderArgs(token_id=token_id, price=price, size=quantity, side=side_str)
                signed = await self._to_thread(self._client.create_order, args)
                resp = await self._to_thread(self._client.post_order, signed, PolyOrderType.GTC)

            order_id = (resp or {}).get("orderID") or (resp or {}).get("order_id") or f"poly-{int(time.time()*1000)}"
            return Order(
                order_id=str(order_id), symbol=token_id, side=side,
                order_type=order_type, quantity=quantity, price=price, status="open",
            )
        except Exception as e:
            logger.error("Polymarket place_order failed: %s", e)
            raise

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        try:
            await self._to_thread(self._client.cancel, order_id)
            return True
        except Exception as e:
            logger.warning("Polymarket cancel_order failed: %s", e)
            return False

    async def close_position(self, symbol: str, quantity: float | None = None) -> Order | None:
        # Polymarket "close" = market sell remaining shares
        positions = await self.get_positions()
        token_id = await self._resolve_token_id(symbol)
        pos = next((p for p in positions if p.symbol == token_id), None)
        if not pos or pos.quantity == 0:
            return None
        qty = quantity if quantity is not None else abs(pos.quantity)
        side: OrderSide = "sell" if pos.quantity > 0 else "buy"
        return await self.place_order(token_id, side, qty, "market")
