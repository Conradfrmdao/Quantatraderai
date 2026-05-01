"""MetaTrader 4/5 venue adapter via MetaAPI cloud SDK.

Installation (one-time):
    poetry add metaapi-cloud-sdk

Required env vars:
    METAAPI_TOKEN       — MetaAPI account token (metaapi.cloud dashboard)
    METAAPI_ACCOUNT_ID  — MT4/MT5 trading account ID on MetaAPI

Optional:
    MT_IS_PAPER=true    — skip live order placement (default: true)

MetaAPI supports 600+ brokers, MT4 + MT5, on Linux/Mac/Windows.
Free dev tier; ~$30/mo for production streaming.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from src.venues.base import Venue
from src.venues.models import (
    AssetClass, Balance, Candle, Order, Position, SymbolMeta, Ticker,
)

logger = logging.getLogger("qunta.venues.metatrader")

# MetaAPI timeframe mapping
_TF_MAP = {
    "1m": "1M", "5m": "5M", "15m": "15M", "30m": "30M",
    "1h": "1H", "4h": "4H", "1d": "1D",
}


def _require_metaapi():
    try:
        from metaapi_cloud_sdk import MetaApi  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "metaapi-cloud-sdk is not installed. Run: poetry add metaapi-cloud-sdk"
        ) from exc


class MetaTraderVenue(Venue):
    """Venue adapter that wraps MetaAPI to give MetaTrader the same interface
    as Binance / Hyperliquid — drop-in replacement."""

    name = "metatrader"
    asset_class: AssetClass = "forex"

    def __init__(
        self,
        token: str | None = None,
        account_id: str | None = None,
        is_paper: bool | None = None,
    ):
        _require_metaapi()
        self._token      = token      or os.getenv("METAAPI_TOKEN", "")
        self._account_id = account_id or os.getenv("METAAPI_ACCOUNT_ID", "")
        self._is_paper   = is_paper if is_paper is not None else (
            os.getenv("MT_IS_PAPER", "true").lower() in ("1", "true", "yes")
        )
        if not self._token or not self._account_id:
            raise ValueError("METAAPI_TOKEN and METAAPI_ACCOUNT_ID must be set")
        self._connection = None  # lazy-init

    async def _get_conn(self):
        if self._connection is not None:
            return self._connection
        from metaapi_cloud_sdk import MetaApi
        api     = MetaApi(self._token)
        account = await api.metatrader_account_api.get_account(self._account_id)
        conn    = account.get_rpc_connection()
        await conn.connect()
        await conn.wait_synchronized()
        self._connection = conn
        return conn

    # ── Balances ──────────────────────────────────────────────────────────────

    async def get_balances(self) -> list[Balance]:
        conn = await self._get_conn()
        info = await conn.get_account_information()
        return [Balance(
            currency=info.get("currency", "USD"),
            total=float(info.get("balance", 0)),
            available=float(info.get("freeMargin", info.get("balance", 0))),
        )]

    # ── Positions ─────────────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        conn      = await self._get_conn()
        raw_pos   = await conn.get_positions()
        positions = []
        for p in raw_pos:
            ptype = p.get("type", "")  # "POSITION_TYPE_BUY" or "POSITION_TYPE_SELL"
            qty   = float(p.get("volume", 0))
            if ptype == "POSITION_TYPE_SELL":
                qty = -qty
            positions.append(Position(
                symbol         = p.get("symbol", ""),
                quantity       = qty,
                entry_price    = float(p.get("openPrice", 0)),
                unrealized_pnl = float(p.get("profit", 0)),
                leverage       = None,
                liquidation_price = None,
            ))
        return positions

    # ── Ticker ────────────────────────────────────────────────────────────────

    async def get_ticker(self, symbol: str) -> Ticker:
        conn  = await self._get_conn()
        price = await conn.get_symbol_price(symbol)
        return Ticker(
            symbol=symbol,
            last=float(price.get("ask", 0)),
            bid=float(price.get("bid", 0)),
            ask=float(price.get("ask", 0)),
        )

    # ── Candles ───────────────────────────────────────────────────────────────

    async def get_candles(self, symbol: str, timeframe: str, lookback: int) -> list[Candle]:
        conn      = await self._get_conn()
        mt_tf     = _TF_MAP.get(timeframe, "1H")
        raw_bars  = await conn.get_historical_candles(symbol, mt_tf, None, lookback)
        candles   = []
        for bar in raw_bars:
            ts = bar.get("time")
            if isinstance(ts, str):
                ts = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
            elif isinstance(ts, datetime):
                ts = int(ts.timestamp())
            candles.append(Candle(
                ts=ts,
                open=float(bar.get("open", 0)),
                high=float(bar.get("high", 0)),
                low=float(bar.get("low", 0)),
                close=float(bar.get("close", 0)),
                volume=float(bar.get("tickVolume", 0)),
            ))
        return candles

    # ── Symbol info ───────────────────────────────────────────────────────────

    async def get_symbol_info(self, symbol: str) -> SymbolMeta:
        conn = await self._get_conn()
        spec = await conn.get_symbol_specification(symbol)
        return SymbolMeta(
            symbol       = symbol,
            asset_class  = "forex",
            tick_size    = float(spec.get("tickSize", 0.00001)),
            lot_size     = float(spec.get("lotSize", 100_000)),
            min_notional = float(spec.get("minVolume", 0.01)) * float(spec.get("lotSize", 100_000)),
            max_leverage = float(spec.get("maxLeverage", 100)),
            pip_value    = float(spec.get("pipValue", 10)),
        )

    # ── Orders ────────────────────────────────────────────────────────────────

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        leverage: float | None = None,
    ) -> Order:
        if self._is_paper:
            logger.info("[PAPER/MT] %s %s qty=%s", side.upper(), symbol, quantity)
            return Order(
                order_id="paper", symbol=symbol, side=side,  # type: ignore[arg-type]
                order_type=order_type,  # type: ignore[arg-type]
                quantity=quantity, status="paper",
            )
        conn = await self._get_conn()
        opts: dict = {}
        if stop_loss:
            opts["stopLoss"] = stop_loss
        if take_profit:
            opts["takeProfit"] = take_profit

        if side == "buy":
            result = await conn.create_market_buy_order(symbol, quantity, **opts)
        else:
            result = await conn.create_market_sell_order(symbol, quantity, **opts)

        order_id = result.get("orderId", result.get("positionId", "unknown"))
        return Order(
            order_id=str(order_id), symbol=symbol,
            side=side, order_type="market",  # type: ignore[arg-type]
            quantity=quantity,
            stop_loss=stop_loss, take_profit=take_profit,
            status="filled",
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        if self._is_paper:
            return True
        conn = await self._get_conn()
        try:
            await conn.cancel_order(order_id)
            return True
        except Exception as e:
            logger.warning("cancel_order failed: %s", e)
            return False

    async def close_position(self, symbol: str, quantity: float | None = None) -> Order | None:
        if self._is_paper:
            return None
        conn = await self._get_conn()
        positions = await conn.get_positions()
        for pos in positions:
            if pos.get("symbol") == symbol:
                pos_id = pos.get("id")
                try:
                    await conn.close_position(pos_id)
                    return Order(
                        order_id=f"close_{pos_id}", symbol=symbol,
                        side="sell", order_type="market",  # type: ignore[arg-type]
                        quantity=abs(float(pos.get("volume", 0))), status="filled",
                    )
                except Exception as e:
                    logger.warning("close_position %s failed: %s", symbol, e)
        return None
