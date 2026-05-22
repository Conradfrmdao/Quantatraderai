"""QuantatraderAI API Server — FastAPI + WebSocket.

Standalone production server.  Start with:
    poetry run python src/server.py

Default port: 8000 (set API_PORT env var to override).

REST Endpoints
--------------
GET  /api/status          — server / agent health
GET  /api/account         — portfolio snapshot (when agent running)
GET  /api/positions       — open positions
GET  /api/decisions       — last N AI decisions
GET  /api/risk            — active risk config
GET  /api/candles         — OHLCV candle data for any symbol (Binance public)
GET  /api/logs            — recent agent log messages
POST /api/agent/start     — start the trading loop
POST /api/agent/stop      — stop the trading loop
POST /api/agent/killswitch — close ALL positions immediately (emergency)

WebSocket
---------
WS   /ws   — real-time event stream (JWT-gated via subprotocol auth)

Requires CLERK_JWKS_URL env var for WebSocket auth. If unset, auth is skipped
(safe for local dev; never leave unset in production).

Phase 1 additions
-----------------
* Telegram alerts wired on trade_opened / risk_block / circuit_breaker / crash
* JWT validation on WebSocket handshake (RS256 via Clerk JWKS)
* Agent persistence via AgentRun table — auto-resumes on server restart
* Dead man's switch — closes all positions if no tick for 30 min
* Exponential backoff on Binance WebSocket reconnect (1→2→4→8→16→30s)
* decisions buffer already capped at 100 via deque(maxlen=100)
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import pathlib
import re
import sys
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import uvicorn

from src.config_loader import CONFIG
from src.ai.errors import AIError, AIErrorCode, safe_error_payload
from src.ai.governance import AIRequestContext, governed_stream, new_trace_id
from src.ai.limiter import counter_store_available, read_counter, reserve_counter
from src.ai.redaction import redact_text
from src.ai.telemetry import capture_posthog
from src.risk_manager import RiskManager
from src.agent.decision_maker import TradingAgent
from src.venues.base import Venue
from src.venues.crypto.spot_portfolio import PREFERRED_SPOT_QUOTES
from src.venues.crypto.spot_portfolio import base_currency_from_symbol
from src.venues.registry import get_venue
from src.venues.runtime import VenueRuntimeConfig, build_venue_from_runtime
from src.indicators.local_indicators import compute_all, latest
from src.utils.prompt_utils import round_or_none
from src.alerts.notifier import build_notifier, TradingEvent

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
)
logger = logging.getLogger("quantatraderai.server")

# ── Observability bootstrap ───────────────────────────────────────────────────
try:
    from src.observability.setup import setup_all as _setup_obs
    _metrics = _setup_obs()
except Exception as _obs_err:
    logger.warning("Observability setup failed: %s", _obs_err)
    _metrics: dict = {}

# ── Per-user plan checks (replaces global env flags) ─────────────────────────
_PLAN_CACHE: dict[str, tuple[str, float]] = {}  # userId → (plan, cached_at)
_PLAN_CACHE_TTL = 30.0  # 30 seconds — plan upgrades become effective quickly


def invalidate_plan_cache(clerk_user_id: str) -> None:
    """Drop a user's plan cache entry — call after Stripe upgrade webhook fires."""
    _PLAN_CACHE.pop(clerk_user_id, None)

async def _get_user_plan(clerk_user_id: str | None) -> str:
    """Return the plan tier for a user: FREE | STARTER | PRO | ENTERPRISE."""
    if not clerk_user_id:
        return "FREE"
    import time as _time
    cached = _PLAN_CACHE.get(clerk_user_id)
    if cached and _time.time() - cached[1] < _PLAN_CACHE_TTL:
        return cached[0]
    try:
        import asyncpg
        conn = await asyncpg.connect(os.getenv("DATABASE_URL", ""), timeout=5, statement_cache_size=0)
        try:
            row = await conn.fetchrow('SELECT plan FROM "User" WHERE "clerkId" = $1', clerk_user_id)
            plan = str(row["plan"]) if row else "FREE"
        finally:
            await conn.close()
        _PLAN_CACHE[clerk_user_id] = (plan, _time.time())
        return plan
    except Exception:
        return "FREE"  # fail safe

def _plan_allows(plan: str, feature: str) -> bool:
    """Check if a plan tier includes a feature."""
    limits = {
        "FREE":       {"liveTrading": False, "aiCouncil": False, "ragMemory": False, "copyTrading": False},
        "STARTER":    {"liveTrading": True,  "aiCouncil": False, "ragMemory": False, "copyTrading": False},
        "PRO":        {"liveTrading": True,  "aiCouncil": True,  "ragMemory": True,  "copyTrading": True},
        "ENTERPRISE": {"liveTrading": True,  "aiCouncil": True,  "ragMemory": True,  "copyTrading": True},
    }
    return limits.get(plan, limits["FREE"]).get(feature, False)



# ── Notifier (built once at import — reads TELEGRAM_BOT_TOKEN / CHAT_ID) ──────
_notifier = build_notifier()

# Platform bot token — used to send per-user alerts to their personal chat
_TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Shared asyncpg pool — initialised lazily, reused across the app.
# Eliminates the per-call connect/close overhead that exhausts Postgres
# connection slots under load (Supabase free tier = 60 connections).
_db_pool: "asyncpg.Pool | None" = None
_db_pool_lock = asyncio.Lock()


async def _get_pool():
    """Lazy-init shared asyncpg pool. Safe under concurrent access."""
    global _db_pool
    if _db_pool is not None:
        return _db_pool
    async with _db_pool_lock:
        if _db_pool is not None:
            return _db_pool
        try:
            import asyncpg
            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                raise RuntimeError("DATABASE_URL not set")
            _db_pool = await asyncpg.create_pool(
                db_url,
                min_size=2, max_size=10,
                command_timeout=8,
                max_inactive_connection_lifetime=300,
                statement_cache_size=0,
            )
            logger.info("asyncpg pool initialised (min=2 max=10)")
            return _db_pool
        except Exception as e:
            logger.error("asyncpg pool init failed", error=str(e))
            raise


async def _notify_user(user_id: str, event: "TradingEvent") -> None:
    """Send a Telegram alert to the user's personal chat ID (if they set one)."""
    if not _TG_TOKEN or not user_id:
        return
    try:
        pool = await _get_pool()
        row = await pool.fetchrow(
            'SELECT "telegramChatId" FROM "UserSettings" WHERE "userId" = '
            '(SELECT id FROM "User" WHERE "clerkId" = $1)',
            user_id,
        )
        chat_id = row["telegramChatId"] if row else None
        if not chat_id:
            return
        emoji = {
            "trade_opened":          "📈",
            "trade_closed":          "📉",
            "stop_loss_hit":         "🛑",
            "circuit_breaker_tripped": "⚡",
            "decision_error":        "⚠️",
            "info":                  "ℹ️",
        }.get(event.kind, "🔔")
        text = (
            f"{emoji} <b>QuantatraderAI</b>\n"
            f"<b>{event.kind.replace('_', ' ').title()}</b>\n"
            f"Venue: {event.venue}"
            + (f" · {event.symbol}" if event.symbol else "")
            + (f"\n{event.message}" if event.message else "")
        )
        import aiohttp as _ah
        async with _ah.ClientSession() as sess:
            await sess.post(
                f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML"},
                timeout=_ah.ClientTimeout(total=3),
            )
    except Exception as e:
        logger.warning("per-user telegram failed for %s: %s", user_id, e)

# ── JWKS / JWT helpers ────────────────────────────────────────────────────────
_jwks_cache: dict | None = None
_jwks_cache_ts: float = 0.0
_JWKS_TTL = 3600.0  # refresh keys hourly
_WS_APP_SUBPROTOCOL = "quantatraderai-v1"
_WS_AUTH_SUBPROTOCOL_PREFIX = "auth."


async def _get_jwks() -> dict | None:
    global _jwks_cache, _jwks_cache_ts
    now = time.monotonic()
    if _jwks_cache and now - _jwks_cache_ts < _JWKS_TTL:
        return _jwks_cache
    url = os.getenv("CLERK_JWKS_URL")
    if not url:
        return None
    try:
        import aiohttp as ah
        async with ah.ClientSession() as session:
            async with session.get(url, timeout=ah.ClientTimeout(total=5)) as resp:
                data = await resp.json()
        _jwks_cache = data
        _jwks_cache_ts = now
        return data
    except Exception as e:
        logger.warning("JWKS fetch failed: %s", e)
        return None


async def _verify_ws_token(token: str | None) -> tuple[bool, str | None]:
    """Verify WS token. Returns (allowed, user_id).

    Production behaviour (CLERK_JWKS_URL set + WS_AUTH_REQUIRED=true):
        - reject if token missing or invalid
        - return verified user_id from token sub claim
    Dev/local mode:
        - if WS_AUTH_REQUIRED is not "true" AND CLERK_JWKS_URL is unset, allow
          but mark user_id as None (legacy single-user mode).
    Fails CLOSED on any verification error in production.
    """
    require_auth = os.getenv("WS_AUTH_REQUIRED", "false").lower() in ("1", "true", "yes")
    jwks_url     = os.getenv("CLERK_JWKS_URL")

    # Dev mode: no JWKS, no enforcement
    if not require_auth and not jwks_url:
        return True, None

    # Production fail-closed: must have token
    if not token:
        return False, None

    jwks = await _get_jwks()
    if not jwks:
        # Fail closed when auth is required, fail open in dev
        return (not require_auth), None

    try:
        from jose import jwt as jose_jwt, jwk as jose_jwk
        header = jose_jwt.get_unverified_header(token)
        kid = header.get("kid")
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not key_data:
            return False, None
        public_key = jose_jwk.construct(key_data)
        claims = jose_jwt.decode(token, public_key, algorithms=["RS256"], options={"verify_aud": False})
        user_id = claims.get("sub") or claims.get("user_id")
        return True, user_id
    except Exception as e:
        logger.warning("WS token verification failed: %s", e)
        return False, None


def _parse_ws_subprotocols(header_value: str | None) -> list[str]:
    return [item.strip() for item in (header_value or "").split(",") if item.strip()]


def _resolve_ws_auth(ws: WebSocket, query_token: str | None) -> tuple[str | None, str | None]:
    protocols = _parse_ws_subprotocols(ws.headers.get("sec-websocket-protocol"))
    accepted_protocol = _WS_APP_SUBPROTOCOL if _WS_APP_SUBPROTOCOL in protocols else None
    protocol_token = next(
        (
            item[len(_WS_AUTH_SUBPROTOCOL_PREFIX):]
            for item in protocols
            if item.startswith(_WS_AUTH_SUBPROTOCOL_PREFIX) and len(item) > len(_WS_AUTH_SUBPROTOCOL_PREFIX)
        ),
        None,
    )
    return protocol_token or query_token, accepted_protocol


async def _verify_clerk_token(token: str | None) -> tuple[bool, str | None]:
    """Verify a Clerk session token for HTTP proxy requests."""
    if not token:
        return False, None

    jwks = await _get_jwks()
    if not jwks:
        return False, None

    try:
        from jose import jwt as jose_jwt, jwk as jose_jwk
        header = jose_jwt.get_unverified_header(token)
        kid = header.get("kid")
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not key_data:
            return False, None
        public_key = jose_jwk.construct(key_data)
        claims = jose_jwt.decode(token, public_key, algorithms=["RS256"], options={"verify_aud": False})
        user_id = claims.get("sub") or claims.get("user_id")
        return True, user_id
    except Exception as e:
        logger.warning("HTTP token verification failed: %s", e)
        return False, None


def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


async def _resolve_request_user_id(request: Request, requested_user_id: str | None = None) -> str | None:
    """Resolve a trusted Clerk user id from the internal proxy or a Clerk JWT."""
    internal_token = os.getenv("PYTHON_INTERNAL_TOKEN", "")
    proxy_token = request.headers.get("x-internal-token", "")
    header_user_id = request.headers.get("x-user-id")

    if internal_token:
        if proxy_token == internal_token:
            return header_user_id or requested_user_id
        verified, token_user_id = await _verify_clerk_token(_extract_bearer_token(request))
        return token_user_id if verified else None

    # Never trust raw x-user-id / userId on direct HTTP requests when no
    # internal proxy secret is configured. In that case only a verified Clerk
    # bearer token may identify the caller.
    verified, token_user_id = await _verify_clerk_token(_extract_bearer_token(request))
    return token_user_id if verified else None


async def _require_request_user_id(request: Request, requested_user_id: str | None = None) -> str:
    """Resolve the authenticated Clerk user id or raise 401."""
    user_id = await _resolve_request_user_id(request, requested_user_id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user_id


# ── Helpers ───────────────────────────────────────────────────────────────────

def _interval_seconds(iv: str) -> int:
    if iv.endswith("m"): return int(iv[:-1]) * 60
    if iv.endswith("h"): return int(iv[:-1]) * 3600
    if iv.endswith("d"): return int(iv[:-1]) * 86400
    return 3600


def _sharpe(trades: list[dict]) -> float:
    vals = [t.get("pnl", 0) for t in trades]
    if not vals:
        return 0.0
    mean = sum(vals) / len(vals)
    var  = sum((v - mean) ** 2 for v in vals) / len(vals)
    std  = math.sqrt(var) if var > 0 else 0
    return round(mean / std, 4) if std else 0.0


def _candle_dict(c) -> dict:
    return {
        "time": c.ts, "open": c.open, "high": c.high,
        "low":  c.low, "close": c.close, "volume": c.volume,
    }


_CASH_BALANCE_CODES = PREFERRED_SPOT_QUOTES
_CONNECTED_SNAPSHOT_TTL_S = 12


def _extract_cash_balance(balances, *, allow_fallback: bool = True) -> tuple[float, str | None]:
    for code in _CASH_BALANCE_CODES:
        match = next((b for b in balances if str(getattr(b, "currency", "")).upper() == code), None)
        if match:
            available = float(getattr(match, "available", 0) or 0)
            total = float(getattr(match, "total", 0) or 0)
            return (available if available > 0 else total), code

    if not balances or not allow_fallback:
        return 0.0, None

    richest = max(
        balances,
        key=lambda b: float(getattr(b, "available", 0) or getattr(b, "total", 0) or 0),
    )
    available = float(getattr(richest, "available", 0) or 0)
    total = float(getattr(richest, "total", 0) or 0)
    currency = str(getattr(richest, "currency", "") or "").upper() or None
    return (available if available > 0 else total), currency


def _serialize_positions(positions, price_cache: dict[str, float] | None = None) -> list[dict]:
    cache = price_cache or {}
    return [
        {
            "symbol":            p.symbol,
            "quantity":          p.quantity,
            "entry_price":       p.entry_price,
            "current_price":     (
                float(getattr(p, "current_price", 0) or 0)
                or cache.get(p.symbol.replace("/", "").split(":")[0], p.entry_price)
            ),
            "unrealized_pnl":    round(p.unrealized_pnl, 4),
            "leverage":          p.leverage,
            "liquidation_price": p.liquidation_price,
        }
        for p in positions
    ]


def _build_account_payload(balance: float, equity: float, open_positions: int, initial_equity: float | None = None) -> dict:
    starting_equity = initial_equity if initial_equity is not None else equity
    ret_pct = ((equity - starting_equity) / starting_equity * 100) if starting_equity else 0.0
    return {
        "balance":          round(balance, 4),
        "equity":           round(equity, 4),
        "initial_equity":   round(starting_equity, 4),
        "total_return_pct": round(ret_pct, 4),
        "open_positions":   open_positions,
        "sharpe":           0,
    }


def _is_live_spot_account(venue_name: str | None, market: str | None) -> bool:
    return _infer_asset_class(str(venue_name or ""), str(market or "")) == "crypto_spot"


def _calculate_live_account_snapshot(
    balances,
    positions,
    venue_name: str | None,
    market: str | None,
) -> tuple[float, float, float]:
    pnl_total = sum(float(getattr(p, "unrealized_pnl", 0.0) or 0.0) for p in positions)
    if _is_live_spot_account(venue_name, market):
        cash_balance, _currency = _extract_cash_balance(balances, allow_fallback=False)
        holdings_value = sum(
            abs(float(getattr(p, "quantity", 0.0) or 0.0)) * float(getattr(p, "current_price", 0.0) or 0.0)
            for p in positions
        )
        return cash_balance, cash_balance + holdings_value, pnl_total

    cash_balance, _currency = _extract_cash_balance(balances)
    return cash_balance, cash_balance + pnl_total, pnl_total


def _find_spot_holding_position(positions: list[dict] | list, symbol: str) -> dict | None:
    target_base = base_currency_from_symbol(symbol)
    for pos in positions or []:
        pos_symbol = str((pos.get("symbol") if isinstance(pos, dict) else getattr(pos, "symbol", "")) or "")
        if base_currency_from_symbol(pos_symbol) != target_base:
            continue
        qty = float((pos.get("quantity") if isinstance(pos, dict) else getattr(pos, "quantity", 0)) or 0)
        if qty > 0:
            return pos if isinstance(pos, dict) else {
                "symbol": pos_symbol,
                "quantity": qty,
                "current_price": float(getattr(pos, "current_price", 0) or 0),
                "entry_price": float(getattr(pos, "entry_price", 0) or 0),
            }
    return None


def _resolve_execution_quantity(
    s: "AgentState",
    action: str,
    symbol: str,
    allocation_usd: float,
    price: float,
) -> tuple[float, float]:
    if price <= 0:
        return 0.0, 0.0

    if action == "sell" and _is_live_spot_account(s.venue_name, s.market):
        pos = _find_spot_holding_position(s.positions, symbol)
        if not pos:
            return 0.0, 0.0

        held_qty = abs(float(pos.get("quantity") or 0.0))
        if held_qty <= 0:
            return 0.0, 0.0

        target_qty = allocation_usd / price if allocation_usd > 0 else held_qty
        held_value = held_qty * price
        if target_qty >= held_qty * 0.98 or allocation_usd >= held_value * 0.98:
            qty = held_qty
        else:
            qty = min(held_qty, target_qty)
        return qty, qty * price

    qty = allocation_usd / price
    return qty, allocation_usd


async def _load_strategy_rules_for_user(clerk_user_id: str | None):
    if not clerk_user_id:
        return []

    try:
        from src.agent.nl_parser import StrategyRule
        from src.services.supabase_reader import list_strategy_rules

        rows = await list_strategy_rules(clerk_user_id, active_only=True)
        rules = []
        for row in rows:
            rules.append(StrategyRule(
                id=str(row.get("id") or ""),
                raw_text=str(row.get("text") or row.get("condition") or ""),
                symbol=row.get("symbol"),
                action=str(row.get("action") or "buy"),
                condition=str(row.get("condition") or row.get("text") or ""),
                indicator=str(row.get("indicator") or "rsi"),
                operator=str(row.get("operator") or "lt"),
                threshold=float(row.get("threshold") or 0.0),
                allocation_pct=float(row.get("allocationPct") or 3.0),
                active=bool(row.get("isActive", True)),
            ))
        return rules
    except Exception as e:
        logger.warning("Strategy rule load failed for %s: %s", clerk_user_id, e)
        return []


async def _load_connected_snapshot(s: "AgentState", clerk_user_id: str | None) -> tuple[dict, list[dict], bool] | None:
    if not clerk_user_id:
        return None

    now = datetime.now(timezone.utc)
    if (
        s.connected_account_cache is not None
        and s.connected_snapshot_at is not None
        and (now - s.connected_snapshot_at).total_seconds() < _CONNECTED_SNAPSHOT_TTL_S
    ):
        return s.connected_account_cache, s.connected_positions_cache, s.is_paper

    try:
        from src.services.supabase_reader import get_user_venues

        venues = await get_user_venues(clerk_user_id, only_active=True)
        if not venues:
            venues = await get_user_venues(clerk_user_id, only_active=False)
        if not venues:
            return None

        match = next((v for v in venues if v.get("isActive")), venues[0])
        venue_type = str(match.get("type") or "")
        venue_key = _VENUE_TYPE_TO_NAME.get(venue_type, "").lower()
        if not venue_key:
            return None

        is_paper = bool(match.get("isPaper", True))
        s.is_paper = is_paper
        if is_paper:
            positions = list(s.paper_positions)
            configured_cap = max(100.0, float(match.get("paperCapital") or 10_000.0))
            paper_bal = float(s.paper_balance) if positions else configured_cap
            pnl_total = sum(float(p.get("unrealized_pnl", 0.0) or 0.0) for p in positions)
            account = _build_account_payload(
                paper_bal,
                paper_bal + pnl_total,
                len(positions),
                s.initial_equity if positions and s.initial_equity is not None else configured_cap,
            )
            s.connected_account_cache = account
            s.connected_positions_cache = positions
            s.connected_snapshot_at = now
            return account, positions, True

        runtime_config, _venue_registry_name, venue_market = _runtime_config_from_saved_venue(
            user_id=clerk_user_id,
            match=match,
            requested_venue=venue_key,
            is_paper=False,
        )
        venue = build_venue_from_runtime(runtime_config)
        venue.is_paper = False
        balances = await venue.get_balances()
        positions_raw = await venue.get_positions()
        balance, equity, _pnl_total = _calculate_live_account_snapshot(
            balances,
            positions_raw,
            venue_key,
            venue_market,
        )
        positions = _serialize_positions(positions_raw)
        account = _build_account_payload(balance, equity, len(positions))

        s.connected_account_cache = account
        s.connected_positions_cache = positions
        s.connected_snapshot_at = now
        return account, positions, False
    except Exception as e:
        logger.warning("Connected venue snapshot failed for %s: %s", clerk_user_id, e)
        return None


# ── Agent state ───────────────────────────────────────────────────────────────

class AgentState:
    def __init__(self):
        self.status: str         = "idle"
        self.user_id: str | None = None
        self.agent_run_id: str | None = None
        self.symbols: list[str]  = []
        self.timeframe: str      = "1h"
        self.is_paper: bool      = True
        self.market: str         = "futures"
        self.venue_name: str     = "binance"        # canonical venue identifier
        self.venue:    Venue | None = None
        self.risk_mgr: RiskManager  | None = None
        self.ai_agent: TradingAgent | None = None

        self.account:   dict       = {}
        self.positions: list[dict] = []
        self.decisions: deque      = deque(maxlen=100)
        self.logs:      deque      = deque(maxlen=500)

        self.price_cache:  dict[str, float]      = {}
        self.candle_cache: dict[str, list[dict]] = {}
        self.readiness: dict[str, Any] | None = None
        self.warm_snapshot_at: datetime | None = None

        self.start_time:     datetime | None = None
        self.initial_equity: float   | None = None
        self.paper_balance:  float          = 10_000.0
        self.paper_positions: list[dict]    = []
        # Lock protecting paper_positions and paper_balance from concurrent tick + order writes
        self._paper_lock: asyncio.Lock      = asyncio.Lock()
        self.trade_log:      list[dict]      = []
        self.tick_count:     int             = 0
        self.error:          str | None      = None
        self.last_tick_at:   datetime | None = None  # dead man's switch anchor
        self.connected_account_cache: dict | None = None
        self.connected_positions_cache: list[dict] = []
        self.connected_snapshot_at: datetime | None = None
        # Tracks last known unrealized PnL per symbol — used to record realized PnL on close
        self.prev_position_pnl: dict[str, float] = {}

        # Decision timeline — timestamped signal events shown in UI
        self.timeline: deque = deque(maxlen=200)

        # Protection state
        self.daily_loss_usd:     float = 0.0
        self.daily_trade_count:  int   = 0
        self.consecutive_losses: int   = 0
        self.day_reset_at:       str   = ""   # ISO date string of last reset

        self._loop_task:     asyncio.Task | None = None
        self._price_task:    asyncio.Task | None = None
        self._deadman_task:  asyncio.Task | None = None

        # Guard settings (set by StartRequest)
        self.min_confidence_pct: float = 0.0    # 0 = no gate
        self.max_daily_loss_pct: float = 0.0    # 0 = no limit
        self.max_trades_per_day: int   = 0       # 0 = no limit
        self.loss_cooldown_count: int  = 0       # 0 = no cooldown
        self.strategy_type:      str   = ""

        # Async queues — decouple slow LLM calls + order execution from tick timing.
        # The tick loop posts work; dedicated worker tasks drain these queues.
        # This prevents a slow LLM response from blocking all subsequent ticks.
        self._llm_queue:   asyncio.Queue = asyncio.Queue(maxsize=4)
        self._order_queue: asyncio.Queue = asyncio.Queue(maxsize=20)
        self._llm_worker_task:   asyncio.Task | None = None
        self._order_worker_task: asyncio.Task | None = None

    def log(self, msg: str):
        ts = datetime.now(timezone.utc).isoformat()
        entry = {"ts": ts, "msg": msg}
        self.logs.append(entry)
        logger.info(msg)

    def timeline_event(self, kind: str, symbol: str, detail: str,
                       confidence: float | None = None, action: str | None = None):
        """Append a timestamped event to the decision timeline."""
        self.timeline.append({
            "ts":         datetime.now(timezone.utc).isoformat(),
            "kind":       kind,       # signal | decision | executed | blocked | info
            "symbol":     symbol,
            "detail":     detail,
            "confidence": confidence,
            "action":     action,
        })


_state: AgentState              = AgentState()  # default/legacy single-user state
_states: dict[str, AgentState]  = {}            # per-user agent states (multi-tenant)
_ws_clients: set[WebSocket]     = set()
_ws_user_map: dict[WebSocket, str | None] = {}  # WS → user_id (for per-user broadcast)
_start_lock: asyncio.Lock       = asyncio.Lock()

# Pending orders — 2-second undo window before execution
_pending_orders: dict[str, dict] = {}  # order_id → {task, detail}

# Persona leaderboard — cumulative stats per strategy type (in-memory, resets on restart)
_persona_leaderboard: dict[str, dict] = {}


def get_state(user_id: str | None = None) -> AgentState:
    """Resolve per-user agent state. Falls back to the legacy global state."""
    if not user_id:
        return _state
    s = _states.get(user_id)
    if s is None:
        s = AgentState()
        s.user_id = user_id
        _states[user_id] = s
    return s


async def _build_ai_context_for_state(
    s: AgentState,
    *,
    action: str,
    trace_id: str | None = None,
    endpoint: str = "/api/agent/start",
    stream: bool = False,
    symbol: str = "",
) -> AIRequestContext:
    user_id = s.user_id or ""
    plan = await _get_user_plan(user_id) if user_id else "FREE"
    return AIRequestContext(
        user_id=user_id,
        trace_id=trace_id or new_trace_id(),
        plan=plan,
        action=action,  # type: ignore[arg-type]
        provider=(s.ai_agent.provider.name if s.ai_agent else "groq"),
        model=(s.ai_agent.provider.model if s.ai_agent else "llama-3.3-70b-versatile"),
        mode="paper" if s.is_paper else "live",
        venue=s.venue_name or "binance",
        symbol=symbol or ",".join(s.symbols),
        persona=s.strategy_type or "",
        agent_run_id=s.agent_run_id,
        endpoint=endpoint,
        stream=stream,
    )


def _safe_ai_error_message(error: AIError) -> str:
    return f"{error.definition.user_message} Trace ID: {error.trace_id}"


async def _persist_ai_decisions_for_state(
    s: AgentState,
    decisions: list[dict],
    *,
    trace_id: str,
    provider: str,
    model: str,
    council_opinions: list[dict] | None = None,
) -> None:
    if not s.user_id or not decisions:
        return
    try:
        from src.services.persistence import write_ai_council_vote, write_ai_decision
        from src.services.supabase_reader import find_venue_id

        venue_id = await find_venue_id(s.user_id, s.venue_name)
        council_lookup = {str(item.get("asset")): item for item in (council_opinions or [])}
        for dec in decisions:
            symbol = str(dec.get("asset") or "")
            decision_id = await write_ai_decision(
                s.user_id,
                agent_run_id=s.agent_run_id,
                venue_id=venue_id,
                trace_id=trace_id,
                mode="paper" if s.is_paper else "live",
                persona=s.strategy_type or None,
                symbol=symbol,
                provider=provider,
                model=model,
                final_action=str(dec.get("action") or "hold"),
                confidence=float(dec.get("confidence") or 0.0),
                reasoning_summary=redact_text(str(dec.get("rationale") or ""))[:1000],
                risk_decision="deadlock" if dec.get("deadlock") else str(dec.get("action") or "hold"),
                is_council=bool(council_opinions),
            )
            if not decision_id:
                continue
            council_entry = council_lookup.get(symbol)
            for opinion in council_entry.get("opinions", []) if council_entry else []:
                await write_ai_council_vote(
                    s.user_id,
                    decision_id=decision_id,
                    provider=str(opinion.get("provider") or ""),
                    model=str(opinion.get("model") or opinion.get("provider") or ""),
                    role=str(opinion.get("role") or ""),
                    vote_action=str(opinion.get("action") or "hold"),
                    confidence=float(opinion.get("confidence") or 0.0),
                    reasoning_summary=redact_text(str(opinion.get("rationale") or ""))[:1000],
                    latency_ms=int(opinion.get("latency_ms") or 0),
                    prompt_tokens=int(opinion.get("prompt_tokens") or 0),
                    completion_tokens=int(opinion.get("completion_tokens") or 0),
                    total_tokens=int(opinion.get("total_tokens") or 0),
                    estimated_cost_usd=float(opinion.get("estimated_cost_usd") or 0.0),
                    trace_id=str(opinion.get("trace_id") or trace_id),
                )
    except Exception as e:
        logger.warning("AI decision persistence skipped: %s", e)


# ── WebSocket broadcast ───────────────────────────────────────────────────────

async def _broadcast(event: dict, user_id: str | None = None):
    """Broadcast to all clients, or only to clients belonging to user_id."""
    dead: set[WebSocket] = set()
    for ws in list(_ws_clients):
        # Per-user filtering: only deliver if either no user_id specified
        # (legacy/global) or the client belongs to this user.
        if user_id is not None:
            if _ws_user_map.get(ws) != user_id:
                continue
        try:
            await ws.send_json(event)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _ws_clients.discard(ws)
        _ws_user_map.pop(ws, None)


# ── Price streaming — Binance WebSocket or venue polling ─────────────────────

async def _poll_prices(s: "AgentState", symbols: list[str], interval_secs: int = 5):
    """Ticker polling fallback for non-Binance venues (Hyperliquid, CCXT non-Binance, etc.).

    Polls every `interval_secs` seconds using the venue's get_ticker() method so
    price_cache stays fresh without requiring a dedicated WebSocket connection.
    """
    s.log(f"Price polling started for {symbols} (venue={s.venue_name})")
    while s.status == "running":
        if s.venue is None:
            await asyncio.sleep(interval_secs)
            continue
        for sym in symbols:
            try:
                ticker = await s.venue.get_ticker(sym)
                price  = ticker.last or 0.0
                key    = sym.replace("/", "")
                s.price_cache[key] = price
                event_ts = int(time.time())
                await _broadcast({
                    "type":       "price_update",
                    "symbol":     key,
                    "price":      price,
                    "ts":         event_ts,
                    "exchange_ts": None,
                    "source":     s.venue_name or "venue",
                    "transport":  "polling",
                }, s.user_id)
            except Exception as e:
                s.log(f"Price poll error {sym}: {e}")
        await asyncio.sleep(interval_secs)


async def _stream_prices_binance(s: "AgentState", symbols: list[str], timeframe: str):
    """Subscribe to Binance public kline WebSocket stream with exponential backoff."""
    import aiohttp as ah

    normalised = [sym.lower().replace("/", "") for sym in symbols]
    streams    = "/".join(f"{sym}@kline_{timeframe}" for sym in normalised)
    url        = f"wss://stream.binance.com:9443/stream?streams={streams}"

    retry_delay = 1.0
    max_delay   = 30.0
    fail_count  = 0

    while s.status == "running":
        try:
            async with ah.ClientSession() as session:
                async with session.ws_connect(url, heartbeat=20) as ws:
                    s.log(f"Binance price stream connected: {symbols}")
                    retry_delay = 1.0
                    fail_count  = 0
                    async for msg in ws:
                        if s.status != "running":
                            break
                        if msg.type == ah.WSMsgType.TEXT:
                            data  = json.loads(msg.data)
                            kline = data.get("data", {}).get("k", {})
                            if not kline:
                                continue
                            event_ts = int((data.get("data", {}).get("E") or 0) / 1000) or int(time.time())
                            raw_sym = kline["s"]
                            price   = float(kline["c"])
                            candle  = {
                                "time":   kline["t"] // 1000,
                                "open":   float(kline["o"]),
                                "high":   float(kline["h"]),
                                "low":    float(kline["l"]),
                                "close":  price,
                                "volume": float(kline["v"]),
                            }
                            s.price_cache[raw_sym] = price
                            key   = _candle_cache_key(raw_sym, timeframe)
                            cache = s.candle_cache.setdefault(key, [])
                            if cache and cache[-1]["time"] == candle["time"]:
                                cache[-1] = candle
                            elif not cache or candle["time"] > cache[-1]["time"]:
                                cache.append(candle)
                                if len(cache) > 500:
                                    cache.pop(0)
                            await _broadcast({
                                "type":        "price_update",
                                "symbol":      raw_sym,
                                "price":       price,
                                "candle":      candle,
                                "timeframe":   timeframe,
                                "ts":          int(time.time()),
                                "exchange_ts": event_ts,
                                "source":      "binance_ws",
                                "transport":   "websocket",
                            }, s.user_id)
        except Exception as e:
            if s.status != "running":
                break
            fail_count += 1
            s.log(f"Binance stream error (attempt {fail_count}): {e} — retry in {retry_delay:.0f}s")
            if fail_count >= 5:
                await _notifier.emit(TradingEvent(
                    kind="decision_error",
                    venue="binance",
                    message=f"Price stream failed {fail_count} times. Last error: {e}",
                ))
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)


async def _stream_prices(s: "AgentState", symbols: list[str], timeframe: str):
    """Route price streaming to the correct backend based on venue.

    Binance → Binance public kline WebSocket (low latency, push-based).
    All others → ticker polling every 5 s (universal, slightly higher latency).
    """
    vname = (s.venue_name or "").lower()
    if "binance" in vname:
        await _stream_prices_binance(s, symbols, timeframe)
    else:
        # Poll interval: use half the trading timeframe capped at 10s
        iv_secs = _interval_seconds(timeframe) // 2
        poll_secs = max(3, min(iv_secs, 10))
        await _poll_prices(s, symbols, interval_secs=poll_secs)


# ── Dead man's switch ─────────────────────────────────────────────────────────

async def _persist_equity(user_id: str, equity: float, balance: float, pnl: float, tick: int):
    try:
        from src.services.persistence import write_equity_point
        await write_equity_point(user_id, equity, balance, pnl, tick)
    except Exception:
        pass


async def _persist_audit(user_id: str | None, event: str, symbol: str | None = None,
                         action: str | None = None, data: dict | None = None):
    try:
        from src.services.persistence import write_audit
        await write_audit(user_id, event, symbol, action, data)
    except Exception:
        pass


async def _persist_trade(user_id: str | None, **kw):
    try:
        from src.services.persistence import write_trade_log
        await write_trade_log(user_id, **kw)
    except Exception:
        pass


async def _mirror_to_followers(leader_id: str, symbol: str, action: str,
                               alloc: float, equity: float,
                               sl: float | None, tp: float | None):
    """H11: Mirror with 3-attempt retry, structured error logging, non-blocking."""
    max_retries = 3
    delay       = 1.0
    for attempt in range(1, max_retries + 1):
        try:
            from src.copy_trading.mirror import mirror_trade
            results = await mirror_trade(leader_id, symbol, action, alloc, equity, sl, tp)
            if attempt > 1:
                logger.info("Copy mirror succeeded on attempt %d for leader %s", attempt, leader_id)
            # Log per-follower failures
            for r in (results or []):
                if not r.get("ok"):
                    logger.warning(
                        "Copy mirror partial failure | leader=%s follower=%s symbol=%s error=%s",
                        leader_id, r.get("follower_id"), symbol, r.get("error"),
                    )
            return
        except Exception as e:
            if attempt == max_retries:
                logger.error(
                    "Copy mirror exhausted retries | leader=%s symbol=%s action=%s error=%s",
                    leader_id, symbol, action, e,
                )
                await _notifier.emit(TradingEvent(
                    kind="decision_error",
                    venue="copy_trading",
                    message=f"Mirror failed for leader {leader_id} after {max_retries} attempts: {e}",
                ))
            else:
                logger.warning("Copy mirror attempt %d/%d failed: %s", attempt, max_retries, e)
                await asyncio.sleep(delay)
                delay *= 2


async def _dead_mans_switch_for(s: "AgentState"):
    """Two-stage dead man's switch for a single AgentState.

    Stage 1 — WARN (15 min silence): alert + broadcast paused, hold positions.
    Stage 2 — ACT  (30 min silence): close all positions and stop the agent.
    """
    _WARN_LIMIT = 900
    _KILL_LIMIT = 1800
    _warned = False

    while True:
        await asyncio.sleep(60)
        if s.status != "running" or s.last_tick_at is None:
            _warned = False
            continue

        elapsed = (datetime.now(timezone.utc) - s.last_tick_at).total_seconds()

        if elapsed >= _WARN_LIMIT and not _warned:
            _warned = True
            s.log(f"DEAD MAN'S WARNING: no tick for {elapsed/60:.0f}min — possible API hang")
            await _notifier.emit(TradingEvent(
                kind="decision_error",
                venue=s.venue_name or "unknown",
                message=f"WARNING: Agent (user={s.user_id or 'global'}) silent for {elapsed/60:.0f} min. Will close at 30 min.",
            ))
            await _broadcast({"type": "status_update", "status": "paused",
                               "reason": "dead_mans_warning", "elapsed": int(elapsed)}, s.user_id)
            continue

        if elapsed < _KILL_LIMIT:
            continue

        _warned = False
        s.log(f"DEAD MAN'S SWITCH: no tick for {elapsed/60:.0f}min — closing all positions")
        await _notifier.emit(TradingEvent(
            kind="circuit_breaker_tripped",
            venue=s.venue_name or "unknown",
            message=f"Dead man's switch fired for user={s.user_id or 'global'} after {elapsed/60:.0f} min silence.",
        ))

        if s.venue and s.positions:
            for pos in list(s.positions):
                sym = pos.get("symbol", "")
                qty = abs(float(pos.get("quantity", 0)))
                if qty > 0 and not s.is_paper:
                    try:
                        await s.venue.close_position(sym, qty)
                        s.log(f"Dead man's: closed {sym} qty={qty}")
                    except Exception as e:
                        s.log(f"Dead man's close error {sym}: {e}")

        s.status = "stopped"
        await _broadcast({"type": "status_update", "status": "stopped",
                          "reason": "dead_mans_switch"}, s.user_id)
        if s.user_id:
            try:
                from src.services.supabase_reader import upsert_agent_run
                await upsert_agent_run(
                    s.user_id, s.venue_name, s.symbols, s.timeframe,
                    s.is_paper, s.market, False,
                )
            except Exception:
                pass
        break


async def _dead_mans_switch():
    """Launch per-state dead man's switches for all running agents.

    Monitors the legacy global _state plus every per-user state in _states.
    Each state gets its own independent watch loop so a hung per-user agent
    doesn't block detection for other users.
    """
    _launched: set[str] = set()  # tracks which user_ids already have a watcher

    while True:
        await asyncio.sleep(30)
        # Global legacy state
        if _state.status == "running" and "global" not in _launched:
            _launched.add("global")
            asyncio.create_task(_dead_mans_switch_for(_state))

        # Per-user states
        for uid, s in list(_states.items()):
            if s.status == "running" and uid not in _launched:
                _launched.add(uid)
                asyncio.create_task(_dead_mans_switch_for(s))

        # Clean up stopped states from the tracking set so they can restart
        for uid in list(_launched):
            if uid == "global":
                if _state.status != "running":
                    _launched.discard("global")
            else:
                s = _states.get(uid)
                if s is None or s.status != "running":
                    _launched.discard(uid)


# ── Single trading tick ───────────────────────────────────────────────────────

async def _tick_for(s: "AgentState"):
    s.tick_count += 1
    s.last_tick_at = datetime.now(timezone.utc)
    _tick_start = time.time()
    # Update Prometheus gauges
    if _metrics.get("ws_clients"):    _metrics["ws_clients"].set(len(_ws_clients))
    if _metrics.get("agent_running"): _metrics["agent_running"].set(1 if s.status == "running" else 0)

    try:
        balances  = await s.venue.get_balances()
        positions = await s.venue.get_positions()
    except Exception as e:
        err_str = str(e)
        # Translate common exchange error codes to plain English
        human_msg = err_str
        if "-2008" in err_str or "Invalid Api-Key" in err_str or "invalid api" in err_str.lower():
            human_msg = (
                "Invalid API key (-2008) — Binance does not recognise this key. "
                "Most common causes: (1) extra space when pasting — delete the venue and re-paste carefully, "
                "(2) key was regenerated or deleted on binance.com/my/settings/api-management, "
                "(3) you pasted the Secret instead of the Key. "
                "NOTE: Read-Only is fine for paper trading but you need 'Enable Spot & Margin Trading' for live."
            )
        elif "-2015" in err_str or "permissions" in err_str.lower():
            human_msg = (
                "API key permissions error (-2015). "
                "For paper trading: Read-Only is enough. "
                "For live trading: go to binance.com → API Management → Edit → enable 'Spot & Margin Trading'."
            )
        elif "-1102" in err_str or "mandatory parameter" in err_str.lower():
            human_msg = "Binance rejected the request — missing a required parameter. Check venue settings."
        elif "401" in err_str or "403" in err_str or "Unauthorized" in err_str:
            human_msg = "Exchange returned 401/403 — API key is invalid or expired. Re-generate it in your exchange settings."
        elif "IP" in err_str and ("restrict" in err_str.lower() or "whitelist" in err_str.lower()):
            human_msg = "IP restriction: your API key only allows specific IPs. Remove IP restriction in Binance API settings or add your server IP."
        elif "Connection" in err_str or "Timeout" in err_str or "timeout" in err_str.lower():
            human_msg = "Network timeout connecting to exchange. Will retry next tick."
        elif "UnicodeEncodeError" in err_str or "latin-1" in err_str:
            human_msg = "API key contains invalid characters. Delete the venue and re-paste the key."
        elif "deprecated" in err_str.lower() or "testnet" in err_str.lower():
            human_msg = "Exchange testnet is deprecated. Running in paper mode — trades are simulated locally."
        s.log(f"Venue fetch error: {human_msg}")
        return

    if s.is_paper:
        # Hold the lock briefly to get a consistent snapshot of the paper account.
        async with s._paper_lock:
            balance   = s.paper_balance
            pnl_total = sum(p.get("unrealized_pnl", 0.0) for p in s.paper_positions)
        equity = balance + pnl_total
    else:
        balance, equity, pnl_total = _calculate_live_account_snapshot(
            balances,
            positions,
            s.venue_name,
            s.market,
        )

    if s.initial_equity is None:
        s.initial_equity = equity
    s.account = _build_account_payload(balance, equity, len(positions), s.initial_equity)
    s.account["sharpe"] = _sharpe(s.trade_log)
    # Persist equity point every tick (fire-and-forget)
    if s.user_id:
        asyncio.create_task(_persist_equity(s.user_id, equity, balance, pnl_total, s.tick_count))
    current_symbols = {p.symbol for p in positions}
    # Detect positions that closed since last tick and persist realized PnL
    for sym, last_pnl in s.prev_position_pnl.items():
        if sym not in current_symbols and last_pnl != 0.0:
            # Update loss protection counters
            s.daily_loss_usd += last_pnl  # negative if loss
            if last_pnl < 0:
                s.consecutive_losses += 1
                s.timeline_event("info", sym, f"Position closed at loss ${last_pnl:.2f}")
            else:
                s.consecutive_losses = 0
                s.timeline_event("info", sym, f"Position closed at profit ${last_pnl:.2f}")
            if s.user_id:
                asyncio.create_task(_persist_trade(
                    s.user_id, symbol=sym, action="close",
                    quantity=0, price=0, pnl=last_pnl, source="close",
                ))
    # Update prev_position_pnl for next tick
    s.prev_position_pnl = {p.symbol: round(p.unrealized_pnl, 4) for p in positions}

    s.positions = _serialize_positions(positions, s.price_cache)
    s.connected_account_cache = s.account
    s.connected_positions_cache = s.positions
    s.connected_snapshot_at = datetime.now(timezone.utc)
    await _broadcast({"type": "account_update", "data": s.account}, s.user_id)

    # ── Force-close positions that breach max_loss_per_position_pct ──────────
    if s.risk_mgr and not s.is_paper:
        positions_raw = [p.__dict__ for p in positions]
        to_close = s.risk_mgr.check_losing_positions(positions_raw)
        for ptc in to_close:
            sym  = ptc.get("coin") or ptc.get("symbol", "")
            size = ptc.get("size", 0)
            is_long = ptc.get("is_long", True)
            s.log(f"RISK FORCE-CLOSE: {sym} at {ptc['loss_pct']:.1f}% loss (PnL: ${ptc['pnl']:.2f})")
            try:
                await s.venue.close_position(sym, size)
                s.timeline_event("blocked", sym,
                    f"Force-closed by risk manager: {ptc['loss_pct']:.1f}% loss")
                await _notifier.emit(TradingEvent(
                    kind="risk_block",
                    venue=s.venue_name,
                    symbol=sym,
                    message=f"Force-closed {sym}: loss {ptc['loss_pct']:.1f}% exceeded limit",
                ))
                if s.user_id:
                    asyncio.create_task(_persist_audit(
                        s.user_id, "force_close", sym, "sell" if is_long else "buy",
                        {"loss_pct": ptc["loss_pct"], "pnl": ptc["pnl"]},
                    ))
            except Exception as fc_err:
                s.log(f"Force-close error {sym}: {fc_err}")

    _is_forex = s.venue_name in ("oanda", "metatrader")

    # ── FOREX market hours guard — skip ticks during weekend close ────────
    if _is_forex:
        _now_utc = datetime.now(timezone.utc)
        _wd = _now_utc.weekday()  # 0=Mon … 6=Sun
        # Forex is closed: Fri 22:00 UTC → Sun 22:00 UTC
        _closed = (
            _wd == 5  # all Saturday
            or (_wd == 6 and _now_utc.hour < 22)   # Sunday before 22:00 UTC
            or (_wd == 4 and _now_utc.hour >= 22)   # Friday after 22:00 UTC
        )
        if _closed:
            s.log("FOREX market closed (weekend) — skipping tick")
            return

    # ── For FOREX, refresh price cache via REST ticker (no Binance stream) ─
    ticker_context: dict[str, dict[str, float]] = {}
    if _is_forex:
        for sym in s.symbols:
            try:
                ticker = await s.venue.get_ticker(sym)
                mid = ((ticker.bid + ticker.ask) / 2
                       if (ticker.bid and ticker.ask) else ticker.last)
                if mid and mid > 0:
                    s.price_cache[sym.replace("/", "")] = mid
                ticker_context[sym] = {
                    "bid": float(ticker.bid or 0),
                    "ask": float(ticker.ask or 0),
                    "spread_pips": float((getattr(ticker, "extra", {}) or {}).get("spread_pips") or 0),
                }
            except Exception as _te:
                s.log(f"Ticker poll error {sym}: {_te}")

    market_sections = []
    market_data_status: dict[str, dict] = {}
    for sym in s.symbols:
        try:
            candles = await s.venue.get_candles(sym, s.timeframe, 100)
            raw     = [_candle_dict(c) for c in candles]
            key     = _candle_cache_key(sym, s.timeframe)
            s.candle_cache[key] = raw
            inds   = compute_all(raw)
            px_key = sym.replace("/", "")
            # For crypto: stream provides real-time price; only fill gap from candle.
            # For FOREX: ticker polling above already set the price; candle is fallback.
            if px_key not in s.price_cache and candles:
                s.price_cache[px_key] = candles[-1].close
            data_status = _build_market_data_status(
                sym,
                raw,
                inds,
                s.timeframe,
                float(s.price_cache.get(px_key, 0) or 0),
            )
            market_data_status[sym] = data_status
            market_data_status[_normalize_market_symbol(sym)] = data_status
            rsi_val  = round_or_none(latest(inds.get("rsi14", [])), 2)
            macd_val = round_or_none(latest(inds.get("macd",  [])), 2)
            ema_val  = round_or_none(latest(inds.get("ema20", [])), 2)
            market_sections.append({
                "asset":         sym,
                "current_price": round(s.price_cache.get(px_key, 0), 5 if _is_forex else 4),
                "bid":           ticker_context.get(sym, {}).get("bid") if _is_forex else None,
                "ask":           ticker_context.get(sym, {}).get("ask") if _is_forex else None,
                "spread_pips":   ticker_context.get(sym, {}).get("spread_pips") if _is_forex else None,
                "rsi14":         rsi_val,
                "ema20":         ema_val,
                "macd":          macd_val,
                "bars":          data_status["bars_available"],
                "data_ready":    data_status["ready"],
                "data_state":    data_status["status"],
                "latest_candle_ts": data_status["last_candle_ts"],
            })
            if rsi_val is not None:
                if rsi_val < 30:
                    s.timeline_event("signal", sym, f"RSI {rsi_val:.1f} — oversold zone entered")
                elif rsi_val > 70:
                    s.timeline_event("signal", sym, f"RSI {rsi_val:.1f} — overbought zone entered")
            if macd_val is not None and abs(macd_val) > 0:
                s.timeline_event("signal", sym, f"MACD {macd_val:+.4f} detected")
        except Exception as e:
            s.log(f"Data error {sym}: {e}")
            failed_status = {
                "symbol": sym,
                "status": "error",
                "ready": False,
                "bars_available": 0,
                "last_candle_ts": 0,
                "candles_fresh": False,
                "indicators_ready": False,
                "price_available": False,
                "fallback_rationale": f"Market data could not be loaded for {sym} on this tick.",
            }
            market_data_status[sym] = failed_status
            market_data_status[_normalize_market_symbol(sym)] = failed_status
            market_sections.append({
                "asset": sym,
                "current_price": round(s.price_cache.get(sym.replace("/", ""), 0), 5 if _is_forex else 4),
                "rsi14": None,
                "ema20": None,
                "macd": None,
                "bars": 0,
                "data_ready": False,
                "data_state": "error",
                "latest_candle_ts": 0,
            })

    # ── Intel feeds (calendar + sentiment) ────────────────────────────────
    # macro must be initialised BEFORE the intel block that may write to it
    macro: dict = {}

    # ── Phase 5 intelligence: MTF confluence + news + correlation ─────────
    intel_sections: list[dict] = []
    if (_plan_allows(await _get_user_plan(s.user_id), "aiCouncil") or os.getenv("ENABLE_INTEL", "false").lower() in ("1", "true", "yes")):
        for sym in s.symbols:
            sym_intel: dict = {"asset": sym}
            try:
                from src.intel.mtf_confluence import compute_mtf_confluence
                mtf = await compute_mtf_confluence(s.venue, sym)
                sym_intel["mtf_confluence"] = mtf
            except Exception as e:
                s.log(f"MTF error {sym}: {e}")
            try:
                from src.intel.news import get_news_sentiment
                news = await get_news_sentiment(sym)
                sym_intel["news_sentiment"] = news
            except Exception as e:
                s.log(f"News error {sym}: {e}")
            intel_sections.append(sym_intel)
        try:
            from src.intel.correlation import compute_correlation_matrix, format_matrix_summary
            corr_matrix = compute_correlation_matrix(s.candle_cache, s.symbols, s.timeframe)
            corr_summary = format_matrix_summary(corr_matrix)
            if corr_summary:
                macro["correlation"] = corr_summary
        except Exception as e:
            s.log(f"Correlation error: {e}")

    try:
        from src.intel.economic_calendar import should_pause, next_event_summary
        pause, pause_reason = await should_pause(s.symbols)
        if pause:
            s.log(f"CALENDAR PAUSE: {pause_reason}")
            s.last_tick_at = datetime.now(timezone.utc)  # prevent dead man's switch false-positive
            await _notifier.emit(TradingEvent(
                kind="info", venue=s.venue_name or "unknown",
                message=pause_reason,
            ))
            # Tell the frontend so the UI shows "Paused — calendar event" rather than silent inaction
            await _broadcast({
                "type":   "status_update",
                "status": "paused",
                "reason": "calendar_pause",
                "detail": pause_reason,
                "paper":  s.is_paper,
            }, s.user_id)
            return
        next_evt = await next_event_summary()
        if next_evt:
            macro["next_event"] = next_evt
    except Exception as e:
        s.log(f"Calendar check error: {e}")

    # Crypto Fear & Greed is not relevant for FOREX pairs
    if not _is_forex:
        try:
            from src.intel.sentiment import get_fear_greed
            fng = await get_fear_greed()
            macro["crypto_fear_greed"] = fng
        except Exception as e:
            s.log(f"Sentiment fetch error: {e}")

    # ── RAG memory retrieval ─────────────────────────────────────────────
    rag_context = ""
    if s.user_id and (_plan_allows(await _get_user_plan(s.user_id), "ragMemory") or os.getenv("ENABLE_RAG", "false").lower() in ("1", "true", "yes")):
        try:
            from src.memory.rag import retrieve_similar, format_rag_context
            context_summary = json.dumps({"market": market_sections, "macro": macro})[:2000]
            similar = await retrieve_similar(context_summary, s.user_id)
            rag_context = format_rag_context(similar)
        except Exception as e:
            s.log(f"RAG retrieval error: {e}")

    if s.user_id and market_sections:
        asyncio.create_task(_persist_warm_snapshot(s, market_sections=market_sections))

    context = json.dumps({
        "account":         s.account,
        "market_data":     market_sections,
        "risk_limits":     s.risk_mgr.get_risk_summary(),
        "macro_sentiment": macro,
        "intel":           intel_sections if intel_sections else None,
        "rag_memory":      rag_context or None,
        "instructions": {
            "assets":      s.symbols,
            "requirement": "Return strict JSON with trade_decisions array.",
        },
    })

    outputs: dict = {}
    council_opinions: list | None = None
    use_council = _plan_allows(await _get_user_plan(s.user_id), "aiCouncil") or os.getenv("ENABLE_COUNCIL", "false").lower() in ("1", "true", "yes")
    decision_trace_id = new_trace_id()
    try:
        if use_council:
            from src.agent.council import council_decide
            ai_ctx = await _build_ai_context_for_state(
                s,
                action="council_vote",
                trace_id=decision_trace_id,
                endpoint="/api/agent/start",
                stream=True,
            )
            council_results = await council_decide(
                s.symbols,
                context,
                ai_context=ai_ctx,
                stream_handler=lambda payload: _broadcast(payload, s.user_id),
            )
            decisions = []
            council_opinions = []
            for cd in council_results:
                decisions.append({
                    "asset":          cd.asset,
                    "action":         cd.action,
                    "allocation_usd": cd.allocation_usd,
                    "sl_price":       cd.sl_price,
                    "tp_price":       cd.tp_price,
                    "rationale":      cd.rationale,
                    "confidence":     cd.confidence,
                    "deadlock":       cd.deadlock,
                    "council":        [
                        {
                            "role": op.role,
                            "provider": op.provider,
                            "model": op.model,
                            "action": op.action,
                            "rationale": op.rationale[:120],
                            "confidence": op.confidence,
                            "veto": op.veto,
                            "trace_id": op.trace_id,
                            "latency_ms": op.latency_ms,
                            "prompt_tokens": op.prompt_tokens,
                            "completion_tokens": op.completion_tokens,
                            "total_tokens": op.total_tokens,
                            "estimated_cost_usd": op.estimated_cost_usd,
                        }
                        for op in cd.opinions
                    ],
                })
                council_opinions.append({
                    "asset": cd.asset,
                    "opinions": [
                        {
                            "role": op.role,
                            "provider": op.provider,
                            "model": op.model,
                            "action": op.action,
                            "confidence": op.confidence,
                            "rationale": op.rationale[:120],
                            "veto": op.veto,
                            "trace_id": op.trace_id,
                            "latency_ms": op.latency_ms,
                            "prompt_tokens": op.prompt_tokens,
                            "completion_tokens": op.completion_tokens,
                            "total_tokens": op.total_tokens,
                            "estimated_cost_usd": op.estimated_cost_usd,
                        }
                        for op in cd.opinions
                    ],
                    "vote": cd.action, "confidence": cd.confidence, "deadlock": cd.deadlock,
                })
            outputs = {"trace_id": decision_trace_id, "provider": "council", "model": "multi-role"}
        else:
            ai_ctx = await _build_ai_context_for_state(
                s,
                action="agent_decision",
                trace_id=decision_trace_id,
                endpoint="/api/agent/start",
                stream=True,
            )
            outputs = await s.ai_agent.decide_trade_async(
                s.symbols,
                context,
                ai_context=ai_ctx,
                stream_handler=lambda payload: _broadcast(payload, s.user_id),
            ) or {}
            decisions = outputs.get("trade_decisions", []) if isinstance(outputs, dict) else []
            decision_trace_id = str(outputs.get("trace_id") or decision_trace_id)
    except AIError as e:
        safe_msg = _safe_ai_error_message(e)
        s.log(f"AI blocked safely: {safe_msg}")
        await _notifier.emit(TradingEvent(
            kind="decision_error", venue=s.venue_name or "unknown",
            message=safe_msg,
        ))
        decisions = [{
            "asset": sym,
            "action": "hold",
            "allocation_usd": 0.0,
            "tp_price": None,
            "sl_price": None,
            "rationale": safe_msg,
        } for sym in s.symbols]
    except Exception as e:
        s.log(f"AI error: {e}")
        await _notifier.emit(TradingEvent(
            kind="decision_error", venue="binance",
            message=f"LLM decision error: {e}",
        ))
        decisions = []

    decisions = _apply_market_data_guards(decisions, market_data_status)

    if decisions:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": decision_trace_id,
            "reasoning_summary": redact_text(str(outputs.get("reasoning") or ""))[:500] if isinstance(outputs, dict) else "",
            "trade_decisions": decisions,
            "council": council_opinions,
        }
        s.decisions.appendleft(entry)
        await _persist_ai_decisions_for_state(
            s,
            decisions,
            trace_id=decision_trace_id,
            provider=str(outputs.get("provider") or ("council" if use_council else "unknown")) if isinstance(outputs, dict) else ("council" if use_council else "unknown"),
            model=str(outputs.get("model") or ("multi-role" if use_council else "")) if isinstance(outputs, dict) else ("multi-role" if use_council else ""),
            council_opinions=council_opinions,
        )
        await _broadcast({"type": "decisions_update", "data": list(s.decisions)[:20]}, s.user_id)
        # Timeline: record AI decision events
        for dec in decisions:
            action = dec.get("action", "hold")
            sym    = dec.get("asset", "")
            conf   = dec.get("confidence")
            conf_f = float(conf) if conf is not None else None
            if action != "hold":
                s.timeline_event(
                    "decision", sym,
                    f"AI decided {action.upper()} — confidence {int((conf_f or 0) * 100)}%",
                    confidence=conf_f, action=action,
                )
        # Persist decision-level audit record
        if s.user_id:
            for dec in decisions:
                asyncio.create_task(_persist_audit(
                    s.user_id, "decision", dec.get("asset"), dec.get("action"),
                    {"alloc": dec.get("allocation_usd"), "confidence": dec.get("confidence"),
                     "deadlock": dec.get("deadlock"), "venue": s.venue_name,
                     "rationale": (dec.get("rationale") or "")[:200]},
                ))

    # Record tick duration metric
    if _metrics.get("tick_duration"):
        _metrics["tick_duration"].observe(time.time() - _tick_start)

    # ── Evaluate NL strategy rules (loaded from DB, survives restarts) ───────
    strategy_rules = await _load_strategy_rules_for_user(s.user_id)
    if strategy_rules:
        try:
            from src.agent.nl_parser import evaluate_rule
            for sym in s.symbols:
                key = _candle_cache_key(sym, s.timeframe)
                bars = s.candle_cache.get(key, [])
                if not bars: continue
                inds  = compute_all(bars)
                price = s.price_cache.get(sym.replace("/",""), 0)
                equity = s.account.get("equity", 0)
                for rule in strategy_rules:
                    if rule.symbol and rule.symbol.upper() not in sym.upper(): continue
                    if evaluate_rule(rule, inds, price):
                        alloc = equity * (rule.allocation_pct / 100)
                        rule_dec = {
                            "asset": sym, "action": rule.action,
                            "allocation_usd": alloc, "current_price": price,
                            "rationale": f"[NL Rule] {rule.condition}",
                        }
                        decisions.append(rule_dec)
                        s.log(f"[NL RULE] Triggered: {rule.condition} → {rule.action} {sym}")
        except Exception as e:
            s.log(f"Strategy rule eval error: {e}")

    if s.is_paper:
        # Paper trading: simulate execution against s.paper_balance
        acc_state_paper = {"total_value": equity, "balance": balance, "positions": s.paper_positions}
        for dec in decisions:
            action = dec.get("action", "hold")
            sym    = dec.get("asset", "")
            alloc  = float(dec.get("allocation_usd", 0))
            if action not in ("buy", "sell") or alloc <= 0:
                s.log(f"[PAPER] HOLD {sym} — {dec.get('rationale','')[:80]}")
                continue

            # Apply beta cap and risk validation even for paper trades
            if s.risk_mgr:
                _beta = float(os.getenv("BETA_LIVE_CAP_USD", "500"))
                if _beta > 0 and alloc > _beta:
                    alloc = _beta; dec["allocation_usd"] = alloc
                dec["current_price"] = s.price_cache.get(sym.replace("/", ""), 0)
                if _is_forex and sym in ticker_context:
                    dec.update(ticker_context[sym])
                ok, reason, dec = s.risk_mgr.validate_trade(dec, acc_state_paper, s.initial_equity or 0)
                if not ok:
                    s.log(f"[PAPER] BLOCKED {sym}: {reason}")
                    continue

            price = dec.get("current_price") or s.price_cache.get(sym.replace("/", ""), 0)
            if price <= 0:
                s.log(f"[PAPER] {action.upper()} {sym} — price unknown, skipping")
                continue

            qty = alloc / price
            pnl = 0.0

            # Lock so tick loop and any concurrent order can't corrupt paper state.
            async with s._paper_lock:
                if action == "buy":
                    s.paper_balance -= alloc
                    s.paper_positions.append({
                        "symbol": sym, "quantity": qty, "entry_price": price,
                        "current_price": price, "unrealized_pnl": 0.0,
                        "sl_price": dec.get("sl_price"), "tp_price": dec.get("tp_price"),
                    })
                elif action == "sell":
                    matched = next((p for p in s.paper_positions if p["symbol"] == sym), None)
                    if matched:
                        pnl = (price - matched["entry_price"]) * matched["quantity"]
                        s.paper_balance += matched["quantity"] * price
                        s.paper_positions = [p for p in s.paper_positions if p["symbol"] != sym]
                        s.trade_log.append({"action": "sell", "price": price, "qty": qty, "pnl": pnl})
                        if pnl < 0: s.consecutive_losses += 1
                        else:       s.consecutive_losses = 0
                        s.daily_loss_usd += pnl
                    else:
                        s.log(f"[PAPER] SELL {sym} — no open position to close")
                        continue

                s.trade_log.append({"action": action, "price": price, "qty": qty, "pnl": pnl})
                s.daily_trade_count += 1
                for p in s.paper_positions:
                    cp = s.price_cache.get(p["symbol"].replace("/", ""), p["entry_price"])
                    p["current_price"]  = cp
                    p["unrealized_pnl"] = (cp - p["entry_price"]) * p["quantity"]
                _bal_snapshot = s.paper_balance

            s.timeline_event("executed", sym,
                f"[Paper] {action.upper()} {qty:.6f} @ ${price:.2f} | balance=${_bal_snapshot:.2f}",
                action=action)
            s.log(f"[PAPER] {action.upper()} {sym} qty={qty:.6f} @ ${price:.2f} "
                  f"balance=${_bal_snapshot:.2f} — {dec.get('rationale','')[:60]}")
            await _broadcast({"type": "trade_executed", "data": {
                "symbol": sym, "action": action, "price": price, "qty": qty,
                "venue": s.venue_name, "paper": True,
            }}, s.user_id)

        return

    # G22: Adaptive risk — auto-scale position size by rolling Sharpe each tick
    try:
        from src.risk.adaptive import get_adaptive_position_pct
        adaptive_pct = await get_adaptive_position_pct(s.user_id, default_pct=float(
            s.risk_mgr.config.get("max_position_pct", 3) if s.risk_mgr else 3.0
        ))
        if s.risk_mgr and adaptive_pct:
            s.risk_mgr.config["max_position_pct"] = adaptive_pct
    except Exception:
        pass

    # ── Daily reset ──────────────────────────────────────────────────────────────
    today = datetime.now(timezone.utc).date().isoformat()
    if s.day_reset_at != today:
        s.daily_loss_usd    = 0.0
        s.daily_trade_count = 0
        s.day_reset_at      = today

    # ── Loss Protection: daily loss limit ────────────────────────────────────────
    if s.max_daily_loss_pct > 0 and s.initial_equity and s.initial_equity > 0:
        loss_pct = (-s.daily_loss_usd / s.initial_equity) * 100
        if loss_pct >= s.max_daily_loss_pct:
            s.status = "stopping"
            s.log(f"LOSS PROTECTION: daily loss {loss_pct:.1f}% hit limit {s.max_daily_loss_pct}% — stopping agent")
            s.timeline_event("blocked", "", f"Daily loss limit {s.max_daily_loss_pct}% reached — agent paused")
            return

    # ── Loss Protection: max trades per day ──────────────────────────────────────
    if s.max_trades_per_day > 0 and s.daily_trade_count >= s.max_trades_per_day:
        s.log(f"LOSS PROTECTION: max {s.max_trades_per_day} trades/day reached — skipping")
        s.timeline_event("blocked", "", f"Max {s.max_trades_per_day} trades/day reached — no new trades")
        return

    # ── Loss Protection: consecutive loss cooldown ────────────────────────────────
    if s.loss_cooldown_count > 0 and s.consecutive_losses >= s.loss_cooldown_count:
        s.log(f"LOSS PROTECTION: {s.consecutive_losses} consecutive losses — 1 tick cooldown")
        s.timeline_event("blocked", "", f"{s.consecutive_losses} consecutive losses — cooling down")
        s.consecutive_losses = 0  # reset after enforcing one cooldown tick
        return

    acc_state = {"total_value": equity, "balance": balance, "positions": s.positions}
    for dec in decisions:
        sym    = dec.get("asset", "")
        action = dec.get("action", "hold")
        alloc  = float(dec.get("allocation_usd", 0))
        # Beta live cap — clamp live allocation to BETA_LIVE_CAP_USD
        if not s.is_paper:
            _beta = float(os.getenv('BETA_LIVE_CAP_USD', '500'))
            if _beta > 0 and alloc > _beta:
                s.log(f'[BETA CAP] Clamped ${alloc:.2f} to ${_beta:.2f}')
                alloc = _beta
                dec['allocation_usd'] = alloc

        s.log(f"AI: {action.upper()} {sym} ${alloc:.2f} — {dec.get('rationale','')[:80]}")

        if action not in ("buy", "sell") or alloc <= 0:
            continue

        # ── Confidence Gate ───────────────────────────────────────────────────────
        if s.min_confidence_pct > 0:
            raw_conf = dec.get("confidence")
            conf_pct = float(raw_conf) * 100 if raw_conf is not None else 0.0
            if conf_pct < s.min_confidence_pct:
                s.log(f"CONFIDENCE GATE: {sym} conf={conf_pct:.0f}% < threshold {s.min_confidence_pct:.0f}% — skipped")
                s.timeline_event("blocked", sym,
                    f"Confidence gate: {conf_pct:.0f}% below {s.min_confidence_pct:.0f}% threshold — skipped",
                    confidence=conf_pct/100, action=action)
                continue

        # G23: Correlation hedge — reduce size if we already hold a correlated position
        try:
            from src.risk.correlation_hedge import compute_hedge_scalar
            scalar = await compute_hedge_scalar(s.user_id, sym, action, s.positions)
            alloc  = alloc * scalar
            dec["allocation_usd"] = alloc
        except Exception:
            pass

        dec["current_price"] = s.price_cache.get(sym.replace("/", ""), 0)
        if _is_forex and sym in ticker_context:
            dec.update(ticker_context[sym])

        # G24: Slippage prediction — adjust take-profit upward to account for fill cost
        try:
            from src.risk.slippage import estimate_slippage_pct, adjust_tp_for_slippage
            slip = await estimate_slippage_pct(sym, alloc, s.venue_name)
            tp   = dec.get("tp_price")
            if tp:
                dec["tp_price"] = adjust_tp_for_slippage(tp, dec["current_price"], action, slip)
        except Exception:
            pass

        ok, reason, dec = s.risk_mgr.validate_trade(dec, acc_state, s.initial_equity or 0)
        if not ok:
            s.log(f"RISK BLOCKED {sym}: {reason}")
            s.timeline_event("blocked", sym, f"Risk blocked — {reason}", action=action)
            _rbe = TradingEvent(
                kind="circuit_breaker_tripped", venue=s.venue_name, symbol=sym,
                message=f"Risk blocked {action.upper()} {sym}: {reason}",
            )
            await _notifier.emit(_rbe)
            if s.user_id:
                asyncio.create_task(_notify_user(s.user_id, _rbe))
            asyncio.create_task(_persist_audit(
                s.user_id, "risk_block", sym, action,
                {"reason": reason, "allocation_usd": alloc, "venue": s.venue_name},
            ))
            if s.user_id:
                asyncio.create_task(capture_posthog("trade_blocked_by_risk", {
                    "user_id": s.user_id,
                    "plan": await _get_user_plan(s.user_id),
                    "mode": "paper" if s.is_paper else "live",
                    "venue": s.venue_name,
                    "persona": s.strategy_type or "",
                    "provider": outputs.get("provider") if isinstance(outputs, dict) else "",
                    "trace_id": decision_trace_id,
                    "success": True,
                    "reason_code": "risk_block",
                }))
            continue

        price = dec["current_price"]
        if price <= 0:
            s.log(f"Skipping {sym}: price unknown")
            continue

        qty, exec_alloc = _resolve_execution_quantity(
            s,
            action,
            sym,
            float(dec.get("allocation_usd", alloc)),
            price,
        )
        if qty <= 0:
            s.log(f"Skipping {sym}: no executable spot quantity available")
            continue
        try:
            await s.venue.place_order(
                symbol=sym,
                side="buy" if action == "buy" else "sell",
                quantity=qty, order_type="market",
                stop_loss=dec.get("sl_price"),
                take_profit=dec.get("tp_price"),
            )
            s.log(f"ORDER {action.upper()} {sym} qty={qty:.6f} @ ~${price}")
            s.trade_log.append({"action": action, "price": price, "qty": qty})
            s.daily_trade_count += 1
            s.timeline_event("executed", sym,
                f"Order filled: {action.upper()} {qty:.6f} @ ${price:.4f}",
                action=action)
            await _broadcast({
                "type": "trade_executed",
                "data": {"symbol": sym, "action": action, "price": price, "qty": qty, "venue": s.venue_name},
            }, s.user_id)
            _te = TradingEvent(
                kind="trade_opened", venue=s.venue_name, symbol=sym,
                message=f"{action.upper()} {qty:.6f} @ ${price:.4f} — {dec.get('rationale','')[:80]}",
                data={"allocation_usd": exec_alloc, "sl": dec.get("sl_price"), "tp": dec.get("tp_price")},
            )
            await _notifier.emit(_te)
            if s.user_id:
                asyncio.create_task(_notify_user(s.user_id, _te))
            # Persist to TradeLog + AuditLog
            asyncio.create_task(_persist_trade(
                s.user_id, symbol=sym, action=action, quantity=qty, price=price,
                allocation_usd=exec_alloc, source="agent", rationale=dec.get("rationale"),
                tp_price=dec.get("tp_price"), sl_price=dec.get("sl_price"),
            ))
            asyncio.create_task(_persist_audit(
                s.user_id, "order", sym, action,
                {"qty": qty, "price": price, "venue": s.venue_name, "allocation_usd": exec_alloc},
            ))
            if s.user_id:
                asyncio.create_task(capture_posthog("trade_executed", {
                    "user_id": s.user_id,
                    "plan": await _get_user_plan(s.user_id),
                    "mode": "paper" if s.is_paper else "live",
                    "venue": s.venue_name,
                    "persona": s.strategy_type or "",
                    "provider": outputs.get("provider") if isinstance(outputs, dict) else "",
                    "trace_id": decision_trace_id,
                    "success": True,
                    "reason_code": "trade_executed",
                }))
            # Mirror to copy-trading followers
            if s.user_id and (_plan_allows(await _get_user_plan(s.user_id), "copyTrading") or os.getenv("ENABLE_COPY_TRADING", "false").lower() in ("1", "true", "yes")):
                asyncio.create_task(_mirror_to_followers(
                    s.user_id, sym, action, exec_alloc, equity,
                    dec.get("sl_price"), dec.get("tp_price"),
                ))
        except Exception as e:
            s.log(f"Order error {sym}: {e}")


async def _tick():
    await _tick_for(_state)


# ── Main trading loop ─────────────────────────────────────────────────────────

# ── LLM Decision Worker ──────────────────────────────────────────────────────
# Drains s._llm_queue. Runs concurrently with the tick loop so a slow LLM
# call (3-5s) never blocks indicator collection or WebSocket broadcasts.

async def _llm_worker(s: "AgentState"):
    """Dedicated coroutine that processes LLM decision requests off the main tick path."""
    while s.status in ("running", "stopping"):
        try:
            ctx = await asyncio.wait_for(s._llm_queue.get(), timeout=2.0)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        try:
            if s.ai_agent:
                ai_ctx = await _build_ai_context_for_state(
                    s,
                    action="agent_decision",
                    trace_id=new_trace_id(),
                    endpoint="/api/agent/start",
                    stream=True,
                )
                result = await s.ai_agent.decide_trade_async(
                    ctx["symbols"],
                    ctx["context"],
                    ai_context=ai_ctx,
                    stream_handler=lambda payload: _broadcast(payload, s.user_id),
                )
                decisions = result.get("trade_decisions", []) if isinstance(result, dict) else []
                # Push decisions to the order queue for execution
                if decisions and not s.is_paper:
                    await s._order_queue.put({"decisions": decisions, "equity": ctx["equity"], "balance": ctx["balance"]})
                # Always update decision feed
                if decisions:
                    entry = {"ts": datetime.now(timezone.utc).isoformat(), "trade_decisions": decisions, "council": None}
                    s.decisions.appendleft(entry)
                    await _broadcast({"type": "decisions_update", "data": list(s.decisions)[:20]}, s.user_id)
        except Exception as e:
            s.log(f"[LLM worker] error: {e}")
        finally:
            s._llm_queue.task_done()


async def _order_worker(s: "AgentState"):
    """Dedicated coroutine that executes validated orders off the main tick path."""
    while s.status in ("running", "stopping"):
        try:
            job = await asyncio.wait_for(s._order_queue.get(), timeout=2.0)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        try:
            decisions = job.get("decisions", [])
            equity    = job.get("equity", 0.0)
            balance   = job.get("balance", 0.0)
            acc_state = {"total_value": equity, "balance": balance, "positions": s.positions}
            for dec in decisions:
                sym    = dec.get("asset", "")
                action = dec.get("action", "hold")
                alloc  = float(dec.get("allocation_usd", 0))
                if action not in ("buy", "sell") or alloc <= 0 or not s.risk_mgr:
                    continue
                dec["current_price"] = s.price_cache.get(sym.replace("/", ""), 0)
                ok, reason, dec = s.risk_mgr.validate_trade(dec, acc_state, s.initial_equity or 0)
                if not ok:
                    s.log(f"[ORDER worker] RISK BLOCKED {sym}: {reason}")
                    continue
                price = dec["current_price"]
                if price <= 0: continue
                qty, exec_alloc = _resolve_execution_quantity(s, action, sym, alloc, price)
                if qty <= 0:
                    s.log(f"[ORDER worker] skipping {sym}: no executable spot quantity available")
                    continue
                try:
                    await s.venue.place_order(symbol=sym, side=action, quantity=qty,
                                              order_type="market",
                                              stop_loss=dec.get("sl_price"),
                                              take_profit=dec.get("tp_price"))
                    s.log(f"[ORDER worker] {action.upper()} {sym} qty={qty:.6f} @ ~${price}")
                    s.trade_log.append({"action": action, "price": price, "qty": qty})
                    s.daily_trade_count += 1
                    await _broadcast({"type": "trade_executed", "data": {
                        "symbol": sym, "action": action, "price": price, "qty": qty,
                        "venue": s.venue_name,
                    }}, s.user_id)
                except Exception as e:
                    s.log(f"[ORDER worker] exec error {sym}: {e}")
        except Exception as e:
            s.log(f"[ORDER worker] job error: {e}")
        finally:
            s._order_queue.task_done()


async def _run_loop_for(s: "AgentState"):
    s.start_time   = datetime.now(timezone.utc)
    s.last_tick_at = datetime.now(timezone.utc)
    s.log(f"Agent started — symbols={s.symbols} tf={s.timeframe} paper={s.is_paper}")
    await _broadcast({"type": "status_update", "status": "running", "paper": s.is_paper}, s.user_id)

    # Only stream Binance prices for crypto venues; FOREX uses REST polling in _tick_for
    _forex_venues = ("oanda", "metatrader", "ibkr", "alpaca")
    if s.venue_name not in _forex_venues:
        s._price_task = asyncio.create_task(_stream_prices(s, s.symbols, s.timeframe))
    else:
        s._price_task = None  # no Binance stream for FOREX

    s._deadman_task      = asyncio.create_task(_dead_mans_switch_for(s))
    s._llm_worker_task   = asyncio.create_task(_llm_worker(s))
    s._order_worker_task = asyncio.create_task(_order_worker(s))

    try:
        while s.status == "running":
            try:
                await _tick_for(s)
            except Exception as e:
                s.log(f"Tick error: {e}")
                await _notifier.emit(TradingEvent(
                    kind="decision_error", venue="binance",
                    message=f"Unexpected tick error: {e}",
                ))
            await _broadcast({"type": "log", "data": list(s.logs)[-1] if s.logs else {}}, s.user_id)
            await asyncio.sleep(_interval_seconds(s.timeframe))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        s.log(f"Agent crashed: {e}")
        await _notifier.emit(TradingEvent(
            kind="decision_error", venue="binance",
            message=f"Agent loop crashed: {e}",
        ))
    finally:
        for task in (s._price_task, s._deadman_task, s._llm_worker_task, s._order_worker_task):
            if task:
                task.cancel()
        s.status = "stopped"
        s.log("Agent stopped")
        await _broadcast({"type": "status_update", "status": "stopped"}, s.user_id)
        # Fire agent-stopped email via Next.js (non-blocking)
        if s.user_id and os.getenv("NEXT_PUBLIC_APP_URL"):
            try:
                import aiohttp as _ah
                async with _ah.ClientSession() as _sess:
                    await asyncio.wait_for(
                        _sess.post(
                            f"{os.getenv('PYTHON_API_EMAIL_HOOK', '')}".rstrip("/") or
                            f"{os.getenv('NEXT_PUBLIC_APP_URL', '')}/api/email/agent-stopped",
                            json={"userId": s.user_id, "venue": s.venue_name, "reason": "Agent loop ended"},
                            timeout=_ah.ClientTimeout(total=3),
                        ),
                        timeout=3,
                    )
            except Exception:
                pass
        if s.user_id:
            try:
                from src.services.supabase_reader import upsert_agent_run
                await upsert_agent_run(
                    s.user_id, s.venue_name, s.symbols, s.timeframe, s.is_paper, s.market, False,
                )
            except Exception:
                pass
        # Update persona leaderboard with this session's metrics
        if s.strategy_type and s.trade_log:
            trades = s.trade_log
            wins    = sum(1 for t in trades if t.get("pnl", 0) > 0)
            total   = len(trades)
            gross   = sum(t.get("pnl", 0) for t in trades)
            lb      = _persona_leaderboard.setdefault(s.strategy_type, {
                "sessions": 0, "total_trades": 0, "wins": 0, "gross_pnl": 0.0,
            })
            lb["sessions"]      += 1
            lb["total_trades"]  += total
            lb["wins"]          += wins
            lb["gross_pnl"]     += round(gross, 2)


async def _run_loop():
    await _run_loop_for(_state)


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="QuantatraderAI API", version="1.0.0")

# ── CORS — lock down to your frontend domain in production ────────────────────
# Set ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
# Leave unset (or "*") only for local dev.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
_allow_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or ["http://localhost:3000"]
if "*" not in _allow_origins:
    logger.info("CORS locked to: %s", _allow_origins)
else:
    logger.warning("CORS is OPEN (*) — set ALLOWED_ORIGINS in production")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Rate limiting ─────────────────────────────────────────────────────────────
from collections import defaultdict
from fastapi.responses import JSONResponse as _JSONResponse

_rate_buckets: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60.0   # seconds
_RATE_LIMIT_MAX    = 120    # requests per window per IP

# Per-endpoint tighter limits: (max_calls, window_seconds)
_ENDPOINT_LIMITS: dict[str, tuple[int, float]] = {
    "/api/agent/start":           (10,  3600),   # 10 starts per hour
    "/api/backtest/run":          (5,   3600),   # 5 backtests per hour (LLM cost)
    "/api/agent/execute-signal":  (60,  3600),   # 60 webhook signals per hour
    "/api/agent/killswitch":      (5,    300),   # 5 kill switches per 5 min
}
_endpoint_buckets: dict[str, list[float]] = defaultdict(list)

def _check_endpoint_limit(endpoint: str, ip: str) -> bool:
    """Returns True if the request is allowed, False if rate-limited."""
    limit, window = _ENDPOINT_LIMITS[endpoint]
    key  = f"{ip}:{endpoint}"
    now  = time.time()
    hits = [t for t in _endpoint_buckets[key] if now - t < window]
    _endpoint_buckets[key] = hits
    if len(hits) >= limit:
        return False
    _endpoint_buckets[key].append(now)
    return True

@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    path      = request.url.path
    now       = time.time()

    # Per-endpoint check first (tighter limits)
    if path in _ENDPOINT_LIMITS and request.method == "POST":
        if not _check_endpoint_limit(path, client_ip):
            return _JSONResponse(
                {"detail": f"Rate limit exceeded for {path}. Please slow down."},
                status_code=429,
                headers={"Retry-After": "60"},
            )

    # Global per-IP check
    bucket = _rate_buckets[client_ip]
    _rate_buckets[client_ip] = [t for t in bucket if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_buckets[client_ip]) >= _RATE_LIMIT_MAX:
        return _JSONResponse({"detail": "Too many requests"}, status_code=429)
    _rate_buckets[client_ip].append(now)
    return await call_next(request)


# ── Startup: auto-resume any agent that was running before a restart ──────────

@app.on_event("startup")
async def _on_startup():
    # ── C5: Security checks on startup ────────────────────────────────────────
    enc_key = os.getenv("ENCRYPTION_KEY", "")
    if not enc_key:
        logger.critical(
            "ENCRYPTION_KEY is not set. Venue credentials cannot be decrypted. "
            "Set a strong random key (e.g. `openssl rand -base64 32`) in your environment."
        )
    elif len(enc_key) < 32:
        logger.warning(
            "ENCRYPTION_KEY looks weak (< 32 chars). Consider rotating to a 32+ byte key."
        )

    if not os.getenv("CLERK_JWKS_URL"):
        logger.warning(
            "CLERK_JWKS_URL is not set. WebSocket auth is running in unauthenticated mode. "
            "Set CLERK_JWKS_URL=https://YOUR_CLERK_DOMAIN/.well-known/jwks.json in production."
        )

    # ── Production-mode hard checks ───────────────────────────────────────────
    _is_prod = os.getenv("ENVIRONMENT", "development").lower() == "production"
    if _is_prod:
        _issues: list[str] = []
        if not os.getenv("ALLOWED_ORIGINS") or os.getenv("ALLOWED_ORIGINS") == "*":
            _issues.append("ALLOWED_ORIGINS is not set — CORS is open to all origins")
        if not os.getenv("CLERK_JWKS_URL"):
            _issues.append("CLERK_JWKS_URL is not set — WebSocket auth is disabled")
        if not os.getenv("ENCRYPTION_KEY"):
            _issues.append("ENCRYPTION_KEY is not set — venue credentials are unencryptable")
        if not os.getenv("SENTRY_DSN"):
            logger.warning("SENTRY_DSN not set — errors will not be tracked in production")
        if _issues:
            for issue in _issues:
                logger.critical("PRODUCTION MISCONFIGURATION: %s", issue)
            raise RuntimeError(
                "Server startup blocked — fix the above PRODUCTION MISCONFIGURATION errors "
                "before running in production mode."
            )

    # ── Agent auto-resume on restart ──────────────────────────────────────────
    # On every container start we attempt to resume EACH AgentRun row that has
    # isRunning=true. If a resume fails (missing creds, venue down, etc.) we
    # mark that row isRunning=false so the user can retry from a clean state
    # instead of being stuck with a zombie record.
    try:
        from src.services.supabase_reader import get_running_agents
        running = await get_running_agents()
    except Exception as e:
        logger.warning("Boot resume check failed: %s", e)
        return

    if not running:
        return

    logger.info("Boot resume: %d running agent(s) found in DB", len(running))

    for row in running:
        venue_name = row.get("venue") or "binance"
        stored_market = row.get("market") or "spot"
        try:
            logger.info("Auto-resuming agent for userId=%s venue=%s symbols=%s",
                        row["userId"], venue_name, row["symbols"])
            result = await _do_start(
                user_id=row["clerkId"],
                venue_name=venue_name,
                symbols=list(row["symbols"]),
                timeframe=row["timeframe"],
                is_paper=row["isPaper"],
                market=stored_market,
                api_key=None,
                api_secret=None,
            )
            if not result.get("ok"):
                raise RuntimeError(result.get("error") or "startup preflight failed")
        except Exception as e:
            logger.error("Auto-resume failed for userId=%s — marking isRunning=false", row["userId"], error=str(e))
            try:
                pool = await _get_pool()
                await pool.execute(
                    'UPDATE "AgentRun" SET "isRunning"=false WHERE "userId"=$1',
                    row["userId"],
                )
            except Exception as e2:
                logger.error("Failed to clear zombie isRunning row", user_id=row["userId"], error=str(e2))


# ── REST ──────────────────────────────────────────────────────────────────────

_server_start_ts: float = time.time()


@app.get("/api/admin/server-stats")
async def admin_server_stats(admin_key: str = ""):
    """Internal server stats for the admin dashboard.
    Protected by ADMIN_SECRET_KEY — only the Next.js server calls this."""
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or admin_key != expected:
        raise HTTPException(status_code=403, detail="Forbidden")
    active_states = [
        {"user_id": s.user_id, "venue": s.venue_name, "symbols": s.symbols,
         "tick_count": s.tick_count, "is_paper": s.is_paper,
         "uptime_s": int((datetime.now(timezone.utc) - s.start_time).total_seconds()) if s.start_time else 0}
        for s in list(_states.values()) + [_state]
        if s.status == "running"
    ]
    return {
        "active_agents":         len(active_states),
        "total_users_in_memory": len(_states),
        "agents":                active_states,
        "pending_orders":        len(_pending_orders),
        "ws_clients":            len(_ws_clients),
        "uptime_s":              int(time.time() - _server_start_ts),
    }


@app.get("/api/agent/test-key")
async def test_stored_key(request: Request, userId: Optional[str] = None):
    """Quick diagnostic: decrypt the stored API key and check its format/length.
    Does NOT call the exchange — purely local validation.
    Shows key length, first 4 chars, last 4 chars so the user can verify without exposing it."""
    # Internal token guard — only Next.js proxy may pass userId
    userId = await _resolve_request_user_id(request, userId)
    if not userId:
        return {"ok": False, "error": "Forbidden"}
    try:
        from src.services.supabase_reader import get_user_venues
        venues = await get_user_venues(userId)
        if not venues:
            return {"ok": False, "error": "No venues configured for this user"}
        results = []
        for v in venues:
            vtype = v.get("type", "unknown")
            key   = v.get("apiKey", "") or ""
            sec   = v.get("apiSecret", "") or ""
            results.append({
                "type":          vtype,
                "key_len":       len(key),
                "key_preview":   f"{key[:4]}...{key[-4:]}" if len(key) >= 8 else f"<{len(key)} chars — too short>",
                "secret_len":    len(sec),
                "secret_ok":     len(sec) >= 20,
                "key_ok":        len(key) >= 20,
                "key_ascii":     key.isascii(),
                "has_spaces":    " " in key or " " in sec,
                "diagnosis":     (
                    "✓ Key format looks correct" if len(key) >= 60 else
                    f"⚠ Key only {len(key)} chars — Binance keys are 64 chars. Was it cut off when pasting?"
                ),
            })
        return {"ok": True, "venues": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/status")
async def get_status(request: Request, userId: Optional[str] = None):
    userId = await _resolve_request_user_id(request, userId)
    s      = get_state(userId)
    now    = datetime.now(timezone.utc)
    uptime = int((now - s.start_time).total_seconds()) if s.start_time else 0
    tick_interval = _interval_seconds(s.timeframe)
    last_tick_ago = int((now - s.last_tick_at).total_seconds()) if s.last_tick_at else None
    next_tick_in  = max(0, int(tick_interval - (last_tick_ago or tick_interval))) if s.status == "running" else None

    # Get the most recent log message so dashboard can show "what is it doing?"
    latest_log = list(s.logs)[-1] if s.logs else None

    return {
        "status":           s.status,
        "provider":         CONFIG.get("llm_provider") or "groq",
        "model":            CONFIG.get("llm_model")    or "llama-3.3-70b-versatile",
        "venue":            s.venue_name,
        "assets":           s.symbols,
        "tick_count":       s.tick_count,
        "uptime_seconds":   uptime,
        "timeframe":        s.timeframe,
        "market":           s.market,
        "asset_class":      _infer_asset_class(s.venue_name, s.market),
        "is_paper":         s.is_paper,
        "last_tick_ago_s":  last_tick_ago,
        "next_tick_in_s":   next_tick_in,
        "tick_interval_s":  int(tick_interval),
        "strategy_type":    s.strategy_type or None,
        "latest_log":       latest_log,
        "daily_trade_count": s.daily_trade_count,
        "consecutive_losses": s.consecutive_losses,
        "readiness_state":  (s.readiness or {}).get("state"),
        "readiness_summary": (s.readiness or {}).get("summary"),
    }


@app.get("/api/account")
async def get_account(request: Request, userId: Optional[str] = None):
    userId = await _resolve_request_user_id(request, userId)
    s = get_state(userId)
    if s.account and s.status in ("running", "stopping"):
        return s.account
    snapshot = await _load_connected_snapshot(s, userId)
    if snapshot:
        account, _positions, _is_paper = snapshot
        return account
    # Agent not running yet — show paper starting balance if paper mode, else zeros
    paper_bal = s.paper_balance if hasattr(s, "paper_balance") else 10_000.0
    is_paper  = s.is_paper
    return {
        "balance": paper_bal if is_paper else 0,
        "equity":  paper_bal if is_paper else 0,
        "initial_equity": paper_bal if is_paper else 0,
        "total_return_pct": 0, "open_positions": 0, "sharpe": 0,
    }


@app.get("/api/positions")
async def get_positions(request: Request, userId: Optional[str] = None):
    userId = await _resolve_request_user_id(request, userId)
    s = get_state(userId)
    # Always return paper positions in paper mode (real exchange positions are irrelevant)
    if s.status in ("running", "stopping") and s.is_paper:
        return {"positions": s.paper_positions, "is_paper": True}
    if s.status in ("running", "stopping"):
        return {"positions": s.positions, "is_paper": False}
    snapshot = await _load_connected_snapshot(s, userId)
    if snapshot:
        _account, positions, is_paper = snapshot
        return {"positions": positions, "is_paper": is_paper}
    return {"positions": s.paper_positions if s.is_paper else [], "is_paper": s.is_paper}


@app.get("/api/risk")
async def get_risk(request: Request, userId: Optional[str] = None):
    """Live risk config for the requesting user's session (or fallback global)."""
    userId = await _resolve_request_user_id(request, userId)
    s = get_state(userId)
    if s.risk_mgr:
        cfg = s.risk_mgr.config if s.risk_mgr and hasattr(s.risk_mgr, "config") else {}
    else:
        cfg = CONFIG
    return {
        "max_position_pct":               cfg.get("max_position_pct"),
        "max_leverage":                   cfg.get("max_leverage"),
        "mandatory_sl_pct":               cfg.get("mandatory_sl_pct"),
        "max_loss_per_position_pct":      cfg.get("max_loss_per_position_pct"),
        "daily_loss_circuit_breaker_pct": cfg.get("daily_loss_circuit_breaker_pct"),
        "max_total_exposure_pct":         cfg.get("max_total_exposure_pct"),
        "max_concurrent_positions":       cfg.get("max_concurrent_positions"),
    }


class RiskRefreshRequest(BaseModel):
    userId: str
    venueId: Optional[str] = None
    risk: dict


class PlanRefreshRequest(BaseModel):
    userId: str


@app.post("/api/plan/refresh")
async def refresh_plan(request: Request, req: PlanRefreshRequest):
    """C3: Invalidate the cached plan so next request fetches fresh from DB.
    Called by the Next.js Stripe webhook handler after a successful upgrade."""
    user_id = await _require_request_user_id(request, req.userId)
    invalidate_plan_cache(user_id)
    return {"ok": True}


@app.post("/api/risk/refresh")
async def refresh_risk(request: Request, req: RiskRefreshRequest):
    """C1: Apply risk profile updates to the running agent immediately.

    Maps Prisma camelCase fields to internal snake_case config keys, then
    broadcasts the new config to all connected WS clients for instant UI sync.
    """
    user_id = await _require_request_user_id(request, req.userId)
    s = get_state(user_id)

    KEY_MAP = {
        "maxPositionPct":           "max_position_pct",
        "maxLeverage":              "max_leverage",
        "mandatorySlPct":           "mandatory_sl_pct",
        "maxLossPerPositionPct":    "max_loss_per_position_pct",
        "dailyLossCircuitBreaker":  "daily_loss_circuit_breaker_pct",
        "maxTotalExposurePct":      "max_total_exposure_pct",
        "maxConcurrentPositions":   "max_concurrent_positions",
    }
    new_cfg = {}
    for k, v in req.risk.items():
        snake = KEY_MAP.get(k)
        if snake:
            new_cfg[snake] = v

    if s.risk_mgr:
        s.risk_mgr.config.update(new_cfg)

    await _broadcast({"type": "risk_update", "data": new_cfg}, s.user_id)
    return {"ok": True, "applied": new_cfg}


def _parse_decision_timestamp(entry: dict) -> datetime | None:
    raw_ts = entry.get("ts")
    if not raw_ts:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw_ts))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _filter_decisions_for_active_run(entries: list[dict], run_started_at: datetime | None, limit: int) -> list[dict]:
    if not run_started_at:
        return list(entries)[:limit]
    run_start = run_started_at.astimezone(timezone.utc)
    filtered: list[dict] = []
    for entry in entries:
        parsed = _parse_decision_timestamp(entry)
        if parsed and parsed >= run_start:
            filtered.append(entry)
    return filtered[:limit]


async def _load_session_scoped_decisions(user_id: str | None, state: AgentState, limit: int) -> list[dict]:
    in_memory = list(state.decisions)[:limit]
    if not user_id:
        return in_memory

    active_run = state.status in ("running", "paused", "stopping")
    if active_run and in_memory:
        return in_memory

    try:
        from src.services.supabase_reader import list_ai_decisions
        persisted = await list_ai_decisions(user_id, limit=limit)
    except Exception as e:
        logger.warning("Falling back to in-memory decisions for %s: %s", user_id, e)
        return in_memory

    if active_run:
        filtered = _filter_decisions_for_active_run(persisted, state.start_time, limit)
        return filtered if filtered else in_memory

    return persisted if persisted else in_memory


@app.get("/api/decisions")
async def get_decisions(request: Request, limit: int = 20, userId: Optional[str] = None):
    userId = await _resolve_request_user_id(request, userId)
    state = get_state(userId)
    return {"decisions": await _load_session_scoped_decisions(userId, state, limit)}


@app.get("/api/trust/metrics")
async def get_trust_metrics(request: Request, userId: Optional[str] = None):
    """Trust Dashboard — win rate, profit curve, drawdown, Sharpe, AI accuracy."""
    userId = await _resolve_request_user_id(request, userId)
    s = get_state(userId)
    trades = list(s.trade_log)

    wins        = sum(1 for t in trades if t.get("pnl", 0) > 0)
    losses      = sum(1 for t in trades if t.get("pnl", 0) < 0)
    total       = len(trades)
    win_rate    = round(wins / total * 100, 1) if total else 0.0
    gross_pnl   = sum(t.get("pnl", 0) for t in trades)
    avg_win     = round(sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0) / wins, 2) if wins else 0.0
    avg_loss    = round(sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) < 0) / losses, 2) if losses else 0.0
    sharpe      = _sharpe(trades)

    # Max drawdown
    equity = s.initial_equity or 10_000.0
    peak   = equity
    mdd    = 0.0
    running = equity
    for t in trades:
        running += t.get("pnl", 0)
        if running > peak: peak = running
        dd = (peak - running) / peak if peak > 0 else 0
        if dd > mdd: mdd = dd

    # Profit curve (last 50 trades)
    curve: list[dict] = []
    running = equity
    for i, t in enumerate(trades[-50:]):
        running += t.get("pnl", 0)
        curve.append({"i": i, "equity": round(running, 2)})

    # AI prediction accuracy: decisions where action matched next-candle direction
    decisions_snap = list(s.decisions)[:100]
    correct = sum(1 for d in decisions_snap
                  if any(dec.get("confidence", 0) > 0.6 for dec in d.get("trade_decisions", [])))
    ai_accuracy = round(correct / len(decisions_snap) * 100, 1) if decisions_snap else None

    return {
        "total_trades":  total,
        "win_rate_pct":  win_rate,
        "wins":          wins,
        "losses":        losses,
        "gross_pnl":     round(gross_pnl, 2),
        "avg_win":       avg_win,
        "avg_loss":      avg_loss,
        "max_drawdown_pct": round(mdd * 100, 2),
        "sharpe":        sharpe,
        "ai_accuracy_pct": ai_accuracy,
        "profit_curve":  curve,
        "running":       s.status == "running",
    }


@app.get("/api/candles")
async def get_candles(
    request: Request,
    symbol:    str = "BTCUSDT",
    timeframe: str = "1h",
    limit:     int = 200,
    venue:     Optional[str] = None,
    userId:    Optional[str] = None,
):
    """Return candle data for any configured venue.

    Order of resolution:
      1. In-memory cache (if the agent is running and has fetched these bars)
      2. Live venue adapter (if agent is running and matches requested venue)
      3. User-bound saved venue adapter (works even when agent is idle)
      4. Binance public REST fallback (crypto symbols only)
    """
    user_id = await _resolve_request_user_id(request, userId)
    state = get_state(user_id) if user_id else None

    key = _candle_cache_key(symbol, timeframe)
    cached = state.candle_cache.get(key) if state else None
    stale_cached = cached[-limit:] if cached else None
    v = (venue or (state.venue_name if state else None) or "binance").lower()
    if _candles_are_fresh(cached, timeframe):
        return {"candles": cached[-limit:], "source": "cache", **_candle_response_meta(v)}

    # If agent is live and the venue matches, use its adapter
    if state and state.venue is not None and v == state.venue_name:
        try:
            bars = await state.venue.get_candles(symbol, timeframe, min(limit, 500))
            candles = [
                {"time": c.ts, "open": c.open, "high": c.high,
                 "low": c.low, "close": c.close, "volume": c.volume}
                for c in bars
            ]
            state.candle_cache[key] = candles
            return {"candles": candles[-limit:], "source": "agent", **_candle_response_meta(v)}
        except Exception as e:
            logger.warning("Venue candle fetch failed, falling back to Binance: %s", e)

    # If a user has a connected venue, fetch real candles from saved credentials
    if user_id and v:
        try:
            bound = await _build_user_bound_venue(user_id, v)
            if bound:
                venue_obj, _match, _registry_name, _venue_market = bound
                bars = await venue_obj.get_candles(symbol, timeframe, min(limit, 500))
                candles = [
                    {"time": c.ts, "open": c.open, "high": c.high,
                     "low": c.low, "close": c.close, "volume": c.volume}
                    for c in bars
                ]
                if candles:
                    if state:
                        state.candle_cache[key] = candles
                    return {"candles": candles[-limit:], "source": "venue", **_candle_response_meta(v)}
        except Exception as e:
            logger.warning("Saved venue candle fetch failed for %s on %s: %s", symbol, v, e)

    # Fallback: Binance public REST for crypto symbols
    try:
        import aiohttp as ah
        tf_map = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                  "1h": "1h", "4h": "4h", "1d": "1d"}
        tf  = tf_map.get(timeframe, "1h")
        binance_symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
        url = (
            f"https://api.binance.com/api/v3/klines"
            f"?symbol={binance_symbol}&interval={tf}&limit={min(limit, 1000)}"
        )
        async with ah.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        if not isinstance(data, list):
            return {"candles": [], "source": "public", **_candle_response_meta("binance")}
        candles = [
            {"time": int(row[0]) // 1000,
             "open": float(row[1]), "high": float(row[2]),
             "low":  float(row[3]), "close": float(row[4]),
             "volume": float(row[5])}
            for row in data
        ]
        if state:
            state.candle_cache[key] = candles
        return {"candles": candles[-limit:], "source": "public", **_candle_response_meta("binance")}
    except Exception as e:
        if stale_cached:
            logger.warning(
                "Returning stale candle cache after live fetch failure for %s %s on %s",
                symbol,
                timeframe,
                v,
            )
            return {"candles": stale_cached, "source": "stale_cache", **_candle_response_meta(v)}
        raise HTTPException(status_code=502, detail=f"Candle fetch failed: {e}")


@app.get("/api/logs")
async def get_logs(request: Request, limit: int = 100, userId: Optional[str] = None):
    userId = await _resolve_request_user_id(request, userId)
    s = get_state(userId)
    return {"logs": list(s.logs)[-limit:]}


# ── Agent control ─────────────────────────────────────────────────────────────

_SYMBOL_RE = re.compile(r"^[A-Z0-9/_-]{1,20}$")

class StartRequest(BaseModel):
    userId:        Optional[str] = None
    venue:         str           = "binance"   # hyperliquid | binance | oanda | metatrader | alpaca | ibkr | bybit | okx | kraken | coinbase | ccxt:<id>
    symbols:       list[str]     = Field(default=["BTC/USDT"], max_length=20)
    timeframe:     str           = "1h"
    isPaper:       bool          = True
    market:        str           = ""       # blank = use the saved venue market mode
    apiKey:        Optional[str] = None
    apiSecret:     Optional[str] = None
    strategyType:     Optional[str] = None   # MOMENTUM_HUNTER | SCALPER_AI | SWING_MASTER | NEWS_REACTOR
    minConfidencePct: float = 0.0            # 0–100: skip trades below this confidence
    maxDailyLossPct:  float = 0.0            # 0: disabled; e.g. 5.0 = stop after 5% daily loss
    maxTradesPerDay:  int   = 0              # 0: no limit
    lossCooldownCount: int  = 0             # pause after N consecutive losses
    paperCapital:      float = 10_000.0      # simulated starting balance for paper mode

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: list[str]) -> list[str]:
        if len(v) > 20:
            raise ValueError("symbols list must not exceed 20 items")
        cleaned = []
        for sym in v:
            s = sym.strip().upper()
            if not _SYMBOL_RE.match(s):
                raise ValueError(f"Invalid symbol: {sym!r}")
            cleaned.append(s)
        return cleaned


# Map frontend VenueType enum → backend registry name
_VENUE_TYPE_TO_NAME: dict[str, str] = {
    "HYPERLIQUID": "hyperliquid",
    "BINANCE":     "binance",
    "BYBIT":       "bybit",
    "OKX":         "okx",
    "KRAKEN":      "kraken",
    "COINBASE":    "coinbase",
    "OANDA":       "oanda",
    "METATRADER":  "metatrader",
    "ALPACA":      "alpaca",
    "IBKR":        "ibkr",
    "CCXT":        "ccxt",
    "POLYMARKET":  "polymarket",
}


_FUTURES_MARKETS = {"futures", "perpetual", "perp", "swap"}


def _default_market_for_backend_name(venue_name: str | None) -> str:
    v = (venue_name or "").lower().strip().split(":")[0]
    if v in ("hyperliquid", "bybit"):
        return "futures"
    if v in ("oanda", "metatrader", "mt4", "mt5"):
        return "forex"
    if v in ("alpaca", "ibkr"):
        return "stocks"
    if v == "polymarket":
        return "prediction"
    return "spot"


def _default_market_for_venue_type(venue_type: str | None) -> str:
    return _default_market_for_backend_name(_VENUE_TYPE_TO_NAME.get(venue_type or "", venue_type or ""))


def _normalize_market_for_backend_name(venue_name: str | None, market: str | None) -> str:
    v = (venue_name or "").lower().strip().split(":")[0]
    requested = (market or "").lower().strip()
    if v in ("binance", "bybit", "okx", "ccxt"):
        return requested if requested in ("spot", "futures") else _default_market_for_backend_name(v)
    return _default_market_for_backend_name(v)


def _infer_asset_class(venue_name: str, market: str) -> str:
    v = venue_name.lower().strip().split(":")[0]
    m = (market or "").lower()
    if v in ("oanda", "metatrader", "mt4", "mt5"):
        return "forex"
    if v in ("alpaca", "ibkr"):
        return "crypto_spot"
    if v == "polymarket":
        return "prediction"
    if v == "hyperliquid":
        return "crypto_perp"
    if v in ("binance", "bybit", "okx", "ccxt") and m in _FUTURES_MARKETS:
        return "crypto_perp"
    if v in ("binance", "bybit", "okx", "ccxt") and m == "spot":
        return "crypto_spot"
    return _ASSET_CLASS.get(v, "crypto_spot")


def _normalize_market_symbol(symbol: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(symbol or "").upper())


def _candle_cache_key(symbol: str | None, timeframe: str | None) -> str:
    return f"{_normalize_market_symbol(symbol)}:{timeframe or '1h'}"


_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def _timeframe_seconds(timeframe: str | None) -> int:
    return _TIMEFRAME_SECONDS.get((timeframe or "1h").lower(), 3600)


def _candles_are_fresh(candles: list[dict] | None, timeframe: str | None, now_ts: int | None = None) -> bool:
    """Treat the current or previous timeframe bucket as fresh cache."""
    if not candles:
        return False
    last_ts = int(candles[-1].get("time") or 0)
    if last_ts <= 0:
        return False
    interval_s = max(_timeframe_seconds(timeframe), 60)
    current_bucket = (int(now_ts or time.time()) // interval_s) * interval_s
    return last_ts >= max(0, current_bucket - interval_s)


_VENUE_EXCHANGE_TIMEZONES: dict[str, str] = {
    "alpaca": "America/New_York",
    "ibkr": "America/New_York",
}


def _exchange_timezone_for_venue(venue_name: str | None) -> str:
    base = str(venue_name or "").lower().split(":")[0]
    return _VENUE_EXCHANGE_TIMEZONES.get(base, "UTC")


def _candle_response_meta(venue_name: str | None) -> dict:
    return {
        "time_basis": "utc_epoch",
        "exchange_timezone": _exchange_timezone_for_venue(venue_name),
        "server_ts": int(time.time()),
    }


def _build_market_data_status(
    symbol: str,
    candles: list[dict],
    indicators: dict,
    timeframe: str,
    current_price: float,
    now_ts: int | None = None,
) -> dict:
    now_ts = int(now_ts or time.time())
    last_candle_ts = int(candles[-1].get("time") or 0) if candles else 0
    bars_available = len(candles)
    rsi_ready = latest(indicators.get("rsi14", [])) is not None
    ema_ready = latest(indicators.get("ema20", [])) is not None
    macd_ready = latest(indicators.get("macd", [])) is not None
    indicators_ready = rsi_ready and ema_ready and macd_ready
    candles_fresh = _candles_are_fresh(candles, timeframe, now_ts=now_ts)
    price_available = bool(current_price and current_price > 0)

    if bars_available == 0:
        status = "missing"
        fallback = f"No candles are available yet for {symbol}."
    elif bars_available < 35:
        status = "warmup"
        fallback = f"Indicator warm-up in progress for {symbol} — only {bars_available} candles available."
    elif not candles_fresh:
        status = "stale"
        lag_s = max(0, now_ts - last_candle_ts) if last_candle_ts else None
        fallback = (
            f"Market data is stale for {symbol}."
            if lag_s is None else
            f"Market data is stale for {symbol} — latest candle is {lag_s}s old."
        )
    elif not indicators_ready:
        status = "indicators_warming"
        fallback = f"Indicators are still warming up for {symbol} on {timeframe}."
    elif not price_available:
        status = "price_missing"
        fallback = f"Live price is unavailable for {symbol} on this tick."
    else:
        status = "ready"
        fallback = "No high-confidence setup after the latest live market scan."

    return {
        "symbol": symbol,
        "status": status,
        "ready": status == "ready",
        "bars_available": bars_available,
        "last_candle_ts": last_candle_ts,
        "candles_fresh": candles_fresh,
        "indicators_ready": indicators_ready,
        "price_available": price_available,
        "fallback_rationale": fallback,
    }


def _missing_market_data_rationale(text: str | None) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return True
    markers = (
        "insufficient market data",
        "insufficient data",
        "not enough data",
        "data unavailable",
        "missing market data",
        "trend evaluation",
    )
    return any(marker in normalized for marker in markers)


def _normalize_hold_rationale(rationale: str | None, data_status: dict | None) -> str:
    text = str(rationale or "").strip()
    if not data_status:
        return text or "No high-confidence setup after the latest live market scan."
    if not text or _missing_market_data_rationale(text):
        return str(data_status.get("fallback_rationale") or text or "No high-confidence setup after the latest live market scan.")
    return text


def _apply_market_data_guards(decisions: list[dict] | None, data_status_map: dict[str, dict]) -> list[dict]:
    guarded: list[dict] = []
    for dec in decisions or []:
        if not isinstance(dec, dict):
            continue
        out = dict(dec)
        symbol = str(out.get("asset") or "")
        data_status = data_status_map.get(symbol) or data_status_map.get(_normalize_market_symbol(symbol))
        action = str(out.get("action") or "hold").lower()

        if data_status and not data_status.get("ready") and action in ("buy", "sell"):
            out["action"] = "hold"
            out["allocation_usd"] = 0.0
            out["tp_price"] = None
            out["sl_price"] = None
            out["reason_code"] = (
                "market_data_stale"
                if data_status.get("status") == "stale"
                else "market_data_not_ready"
            )
            if data_status.get("status") == "stale":
                out["rationale"] = "Market data is stale. Agent paused trading for safety."
            action = "hold"

        if data_status and not data_status.get("ready"):
            if data_status.get("status") == "stale" and out.get("reason_code") == "market_data_stale":
                out["rationale"] = "Market data is stale. Agent paused trading for safety."
            else:
                out["rationale"] = str(
                    data_status.get("fallback_rationale")
                    or out.get("rationale")
                    or "Market data is not ready for this tick."
                )
                out.setdefault(
                    "reason_code",
                    "market_data_stale" if data_status.get("status") == "stale" else "market_data_not_ready",
                )
        elif action == "hold":
            out["rationale"] = _normalize_hold_rationale(out.get("rationale"), data_status)

        if data_status:
            out["data_ready"] = bool(data_status.get("ready"))
            out["data_status"] = data_status.get("status")

        guarded.append(out)
    return guarded


_LIVE_PRICE_FRESHNESS_S = 120
_WARM_SNAPSHOT_CANDLE_LIMIT = 120


def _readiness_check(
    key: str,
    label: str,
    status: str,
    summary: str,
    *,
    required: bool,
    detail: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "key": key,
        "label": label,
        "status": status,
        "required": required,
        "summary": summary,
    }
    if detail:
        payload["detail"] = detail
    if meta:
        payload["meta"] = meta
    return payload


def _parse_snapshot_ts(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = int(value)
        return ts if ts > 0 else None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _warm_snapshot_price_is_recent(snapshot_ts: int | None, now_ts: int | None = None) -> bool:
    if not snapshot_ts:
        return False
    return max(0, int(now_ts or time.time()) - snapshot_ts) <= _LIVE_PRICE_FRESHNESS_S


def _apply_warm_snapshot_to_state(s: "AgentState", warm_state: dict[str, Any] | None) -> dict[str, Any]:
    info: dict[str, Any] = {"used": False, "age_s": None, "snapshot_at": None, "snapshot_ts": None, "restored_symbols": []}
    if not warm_state:
        return info

    if str(warm_state.get("venue") or "").lower() != (s.venue_name or "").lower():
        return info
    if str(warm_state.get("market") or "").lower() != (s.market or "").lower():
        return info
    if str(warm_state.get("timeframe") or "").lower() != (s.timeframe or "").lower():
        return info

    snapshot_ts = _parse_snapshot_ts(warm_state.get("snapshot_at") or warm_state.get("persisted_at"))
    info["snapshot_ts"] = snapshot_ts
    if snapshot_ts:
        info["snapshot_at"] = datetime.fromtimestamp(snapshot_ts, tz=timezone.utc).isoformat()
        info["age_s"] = max(0, int(time.time()) - snapshot_ts)

    stored_prices = warm_state.get("price_cache") or {}
    stored_candles = warm_state.get("candle_cache") or {}

    for sym in s.symbols:
        norm_symbol = _normalize_market_symbol(sym)
        key = _candle_cache_key(sym, s.timeframe)
        restored = False

        if norm_symbol in stored_prices:
            try:
                s.price_cache[norm_symbol] = float(stored_prices[norm_symbol])
                restored = True
            except Exception:
                pass

        candles = stored_candles.get(key)
        if isinstance(candles, list) and candles:
            s.candle_cache[key] = candles[-_WARM_SNAPSHOT_CANDLE_LIMIT:]
            restored = True

        if restored:
            info["restored_symbols"].append(sym)

    info["used"] = bool(info["restored_symbols"])
    if info["used"] and snapshot_ts:
        s.warm_snapshot_at = datetime.fromtimestamp(snapshot_ts, tz=timezone.utc)
    return info


def _build_warm_snapshot(s: "AgentState", market_sections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    relevant_prices: dict[str, float] = {}
    relevant_candles: dict[str, list[dict[str, Any]]] = {}
    for sym in s.symbols:
        norm_symbol = _normalize_market_symbol(sym)
        price = s.price_cache.get(norm_symbol)
        if price is not None:
            relevant_prices[norm_symbol] = float(price)
        key = _candle_cache_key(sym, s.timeframe)
        candles = s.candle_cache.get(key) or []
        if candles:
            relevant_candles[key] = candles[-_WARM_SNAPSHOT_CANDLE_LIMIT:]

    payload: dict[str, Any] = {
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "venue": s.venue_name,
        "market": s.market,
        "timeframe": s.timeframe,
        "symbols": list(s.symbols),
        "price_cache": relevant_prices,
        "candle_cache": relevant_candles,
    }
    if market_sections:
        payload["market_sections"] = market_sections
    return payload


async def _persist_warm_snapshot(s: "AgentState", market_sections: list[dict[str, Any]] | None = None) -> None:
    if not s.user_id:
        return
    try:
        from src.services.supabase_reader import save_agent_warm_state

        snapshot = _build_warm_snapshot(s, market_sections=market_sections)
        saved = await save_agent_warm_state(s.user_id, snapshot)
        if saved:
            snapshot_ts = _parse_snapshot_ts(snapshot.get("snapshot_at"))
            if snapshot_ts:
                s.warm_snapshot_at = datetime.fromtimestamp(snapshot_ts, tz=timezone.utc)
    except Exception as e:
        logger.warning("Warm snapshot persist failed for %s: %s", s.user_id, e)


async def _load_saved_warm_snapshot(user_id: str | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    try:
        from src.services.supabase_reader import load_agent_warm_state

        return await load_agent_warm_state(user_id)
    except Exception as e:
        logger.warning("Warm snapshot load failed for %s: %s", user_id, e)
        return None


async def _enforce_start_plan_mode(user_id: str | None, is_paper: bool) -> tuple[bool, str | None]:
    if not user_id:
        return is_paper, None
    try:
        plan = await _get_user_plan(user_id)
        if not _plan_allows(plan, "liveTrading") and not is_paper:
            logger.warning(
                "Forcing paper mode: user %s on plan %s — liveTrading not allowed.",
                user_id,
                plan,
            )
            return True, (
                f"Your {plan} plan does not include live trading. "
                "Agent started in paper mode. Upgrade to go live."
            )
    except Exception as e:
        logger.warning("Plan re-validation failed (forcing paper): %s", e)
        return True, "Plan check failed — started in paper mode for safety."
    return is_paper, None


async def _prepare_agent_start_bundle(
    *,
    user_id: str | None,
    venue_name: str,
    market: str,
    is_paper: bool,
    api_key: str | None,
    api_secret: str | None,
) -> dict[str, Any]:
    v_key = venue_name.lower().strip().split(":")[0]

    api_passphrase = ""
    account_id = ""
    network = ""
    meta_token = ""
    meta_account_id = ""
    ccxt_exchange = ""
    saved_market = _default_market_for_backend_name(v_key)
    matched_saved_venue: dict[str, Any] | None = None

    if user_id:
        try:
            from src.services.supabase_reader import get_user_venues

            venues = await get_user_venues(user_id)
            for venue_row in venues:
                name = _VENUE_TYPE_TO_NAME.get(venue_row.get("type", ""), "").lower()
                if name != v_key:
                    continue
                matched_saved_venue = venue_row
                api_key = api_key or venue_row.get("apiKey")
                api_secret = api_secret or venue_row.get("apiSecret")
                api_passphrase = venue_row.get("apiPassphrase") or ""
                account_id = venue_row.get("accountId") or ""
                network = venue_row.get("network") or ""
                meta_token = venue_row.get("metaApiToken") or ""
                meta_account_id = venue_row.get("metaApiAccountId") or ""
                ccxt_exchange = venue_row.get("ccxtExchangeId") or ""
                saved_market = str(
                    venue_row.get("market")
                    or _default_market_for_venue_type(venue_row.get("type"))
                ).lower()
                logger.info("Loaded %s credentials from Supabase for user %s", venue_name, user_id)
                break
        except Exception as e:
            logger.warning("Supabase credential load failed: %s — falling back to .env", e)

    normalized_market = _normalize_market_for_backend_name(v_key, (market or "").lower() or saved_market)

    if not api_key and v_key == "binance":
        api_key = CONFIG.get("binance_api_key") or ""
        api_secret = CONFIG.get("binance_api_secret") or ""
    elif not api_key and v_key == "hyperliquid":
        api_key = CONFIG.get("hyperliquid_private_key") or ""

    try:
        asset_class = _infer_asset_class(v_key, normalized_market)
        venue_match_key, venue_registry_name, venue_market = _resolve_test_venue_target(v_key, normalized_market)
        if matched_saved_venue:
            runtime_config, venue_registry_name, venue_market = _runtime_config_from_saved_venue(
                user_id=user_id,
                match=matched_saved_venue,
                requested_venue=venue_registry_name,
                is_paper=is_paper,
            )
        else:
            runtime_config = _runtime_config_from_inputs(
                user_id=user_id,
                venue_name=venue_match_key,
                registry_name=venue_registry_name,
                market=venue_market,
                is_paper=is_paper,
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase,
                account_id=account_id,
                network=network,
                meta_token=meta_token,
                meta_account_id=meta_account_id,
                ccxt_exchange=ccxt_exchange,
            )
        venue = build_venue_from_runtime(runtime_config)
        venue.is_paper = is_paper
        risk_mgr = RiskManager(venue=v_key, asset_class=asset_class)
        venue_ctx = "forex" if asset_class == "forex" else "crypto"
        ai_agent = TradingAgent(hyperliquid=None, venue_context=venue_ctx)
    except Exception as e:
        return {
            "ok": False,
            "error": f"Venue init failed: {e}",
            "v_key": v_key,
            "market": normalized_market,
        }

    return {
        "ok": True,
        "v_key": v_key,
        "market": venue_market,
        "venue": venue,
        "risk_mgr": risk_mgr,
        "ai_agent": ai_agent,
    }


async def _probe_governance_store(user_id: str | None) -> tuple[bool, str]:
    if not user_id:
        return False, "Authenticated user context is required for AI governance."
    if not counter_store_available():
        return False, "AI governance counter store is unavailable."
    probe_key = f"{user_id}:{new_trace_id()}"
    try:
        await reserve_counter("ai:readiness", probe_key, 1, 60)
        current = await read_counter("ai:readiness", probe_key)
        if current < 1:
            return False, "AI governance probe did not confirm the counter write."
        return True, "AI governance counters are writable."
    except Exception as e:
        return False, f"AI governance probe failed: {e}"


def _finalize_readiness_payload(
    *,
    s: "AgentState",
    checks: list[dict[str, Any]],
    market_sections: list[dict[str, Any]],
    warm_snapshot: dict[str, Any],
) -> dict[str, Any]:
    blocked_checks = [check for check in checks if check.get("status") == "blocked" and check.get("required")]
    degraded_checks = [check for check in checks if check.get("status") == "degraded"]
    if blocked_checks:
        state = "blocked"
        summary = blocked_checks[0]["summary"]
    elif degraded_checks:
        state = "degraded"
        summary = degraded_checks[0]["summary"]
    else:
        state = "ready"
        summary = f"Ready to trade {len(s.symbols)} symbol(s) with live venue access and warmed market data."

    return {
        "state": state,
        "can_start": state != "blocked",
        "summary": summary,
        "checks": checks,
        "warnings": [check["summary"] for check in degraded_checks],
        "market": {
            "symbols": list(s.symbols),
            "timeframe": s.timeframe,
            "venue": s.venue_name,
            "market": s.market,
            "sections": market_sections,
        },
        "warm_snapshot": warm_snapshot,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def _evaluate_agent_readiness(
    s: "AgentState",
    *,
    warm_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now_ts = int(time.time())
    checks: list[dict[str, Any]] = []
    market_sections: list[dict[str, Any]] = []
    warm_info = _apply_warm_snapshot_to_state(s, warm_state)
    warm_snapshot_ts = warm_info.get("snapshot_ts")
    is_forex = s.venue_name in ("oanda", "metatrader")

    try:
        balances = await s.venue.get_balances()
        positions = await s.venue.get_positions()
        venue_summary = f"Venue access confirmed; loaded {len(balances)} balance(s) and {len(positions)} position(s)."
        checks.append(_readiness_check(
            "venue_access",
            "Venue Access",
            "ready",
            venue_summary,
            required=True,
        ))
    except Exception as e:
        checks.append(_readiness_check(
            "venue_access",
            "Venue Access",
            "blocked",
            "Could not authenticate or read the connected venue account.",
            required=True,
            detail=str(e),
        ))

    ticker_context: dict[str, dict[str, float]] = {}
    price_failures: list[str] = []
    price_degraded: list[str] = []
    for sym in s.symbols:
        norm_symbol = _normalize_market_symbol(sym)
        try:
            ticker = await s.venue.get_ticker(sym)
            live_price = float(getattr(ticker, "last", 0) or 0)
            if is_forex:
                bid = float(getattr(ticker, "bid", 0) or 0)
                ask = float(getattr(ticker, "ask", 0) or 0)
                live_price = ((bid + ask) / 2) if bid and ask else live_price
                ticker_context[sym] = {
                    "bid": bid,
                    "ask": ask,
                    "spread_pips": float((getattr(ticker, "extra", {}) or {}).get("spread_pips") or 0),
                }
            if live_price <= 0:
                raise ValueError("ticker returned no positive price")
            s.price_cache[norm_symbol] = live_price
        except Exception as e:
            cached_price = float(s.price_cache.get(norm_symbol, 0) or 0)
            if cached_price > 0 and _warm_snapshot_price_is_recent(warm_snapshot_ts, now_ts=now_ts):
                price_degraded.append(sym)
            else:
                price_failures.append(f"{sym}: {e}")

    if price_failures:
        checks.append(_readiness_check(
            "live_prices",
            "Live Prices",
            "blocked",
            "One or more symbols do not have a fresh live price yet.",
            required=True,
            detail="; ".join(price_failures[:4]),
            meta={"affected_symbols": price_failures},
        ))
    elif price_degraded:
        age_s = warm_info.get("age_s")
        checks.append(_readiness_check(
            "live_prices",
            "Live Prices",
            "degraded",
            "Using a recent warm snapshot price while one or more live tickers reconnect.",
            required=True,
            detail=f"Warm snapshot age: {age_s}s" if age_s is not None else None,
            meta={"affected_symbols": price_degraded},
        ))
    else:
        checks.append(_readiness_check(
            "live_prices",
            "Live Prices",
            "ready",
            f"Fresh live prices loaded for {len(s.symbols)} symbol(s).",
            required=True,
        ))

    market_failures: list[str] = []
    market_degraded: list[str] = []
    for sym in s.symbols:
        key = _candle_cache_key(sym, s.timeframe)
        norm_symbol = _normalize_market_symbol(sym)
        live_candles = False
        try:
            candles = await s.venue.get_candles(sym, s.timeframe, 100)
            raw = [_candle_dict(candle) for candle in candles]
            if not raw:
                raise ValueError("venue returned no candles")
            s.candle_cache[key] = raw
            live_candles = True
        except Exception as e:
            raw = list(s.candle_cache.get(key) or [])
            if _candles_are_fresh(raw, s.timeframe, now_ts=now_ts):
                market_degraded.append(sym)
            else:
                raw = []
                market_failures.append(f"{sym}: {e}")

        indicators = compute_all(raw) if raw else {}
        data_status = _build_market_data_status(
            sym,
            raw,
            indicators,
            s.timeframe,
            float(s.price_cache.get(norm_symbol, 0) or 0),
            now_ts=now_ts,
        )
        if not data_status["ready"]:
            market_failures.append(f"{sym}: {data_status['fallback_rationale']}")

        market_sections.append({
            "asset": sym,
            "current_price": round(float(s.price_cache.get(norm_symbol, 0) or 0), 5 if is_forex else 4),
            "bid": ticker_context.get(sym, {}).get("bid") if is_forex else None,
            "ask": ticker_context.get(sym, {}).get("ask") if is_forex else None,
            "spread_pips": ticker_context.get(sym, {}).get("spread_pips") if is_forex else None,
            "bars": data_status["bars_available"],
            "data_ready": data_status["ready"],
            "data_state": data_status["status"],
            "latest_candle_ts": data_status["last_candle_ts"],
            "candle_source": "live" if live_candles else "warm_snapshot",
        })

    if market_failures:
        checks.append(_readiness_check(
            "market_data",
            "Market Data",
            "blocked",
            "Fresh candles and indicators are not fully warmed yet.",
            required=True,
            detail="; ".join(market_failures[:4]),
            meta={"affected_symbols": market_failures},
        ))
    elif market_degraded:
        checks.append(_readiness_check(
            "market_data",
            "Market Data",
            "degraded",
            "Warm snapshot candles are temporarily covering a live market-data reconnect.",
            required=True,
            meta={"affected_symbols": market_degraded},
        ))
    else:
        checks.append(_readiness_check(
            "market_data",
            "Market Data",
            "ready",
            f"Fresh candles and indicators are warmed for {len(s.symbols)} symbol(s).",
            required=True,
        ))

    provider = getattr(s.ai_agent, "provider", None)
    if provider and getattr(provider, "name", None) and getattr(provider, "model", None):
        checks.append(_readiness_check(
            "ai_provider",
            "AI Provider",
            "ready",
            f"{provider.name} / {provider.model} is configured for governed execution.",
            required=True,
        ))
    else:
        checks.append(_readiness_check(
            "ai_provider",
            "AI Provider",
            "blocked",
            "The trading model provider is not configured correctly.",
            required=True,
        ))

    governance_ok, governance_summary = await _probe_governance_store(s.user_id)
    checks.append(_readiness_check(
        "ai_governance",
        "AI Governance",
        "ready" if governance_ok else "blocked",
        governance_summary,
        required=True,
    ))

    plan = await _get_user_plan(s.user_id) if s.user_id else "FREE"
    intel_enabled = _plan_allows(plan, "aiCouncil") or os.getenv("ENABLE_INTEL", "false").lower() in ("1", "true", "yes")
    if intel_enabled:
        news_states: list[str] = []
        news_errors: list[str] = []
        try:
            from src.intel.news import get_news_sentiment

            for sym in s.symbols:
                news = await get_news_sentiment(sym)
                if news.get("stale"):
                    news_states.append(sym)
                elif news.get("error"):
                    news_errors.append(f"{sym}: {news['error']}")
            if news_errors:
                checks.append(_readiness_check(
                    "intel_news",
                    "News Feed",
                    "degraded",
                    "News enrichment is running in degraded mode.",
                    required=False,
                    detail="; ".join(news_errors[:3]),
                ))
            elif news_states:
                checks.append(_readiness_check(
                    "intel_news",
                    "News Feed",
                    "degraded",
                    "News enrichment is serving a recent cached snapshot while upstream recovers.",
                    required=False,
                    meta={"affected_symbols": news_states},
                ))
            else:
                checks.append(_readiness_check(
                    "intel_news",
                    "News Feed",
                    "ready",
                    "News sentiment enrichment is healthy.",
                    required=False,
                ))
        except Exception as e:
            checks.append(_readiness_check(
                "intel_news",
                "News Feed",
                "degraded",
                "News enrichment could not be warmed during preflight.",
                required=False,
                detail=str(e),
            ))
    else:
        checks.append(_readiness_check(
            "intel_news",
            "News Feed",
            "skipped",
            "News enrichment is disabled for this plan/runtime.",
            required=False,
        ))

    try:
        from src.intel.economic_calendar import get_calendar_feed_status

        calendar_status = await get_calendar_feed_status(force_refresh=True)
        calendar_state = str(calendar_status.get("state") or "ready")
        checks.append(_readiness_check(
            "intel_calendar",
            "Calendar Feed",
            "ready" if calendar_state == "ready" else "degraded" if calendar_state in {"stale", "empty"} else "skipped",
            str(calendar_status.get("summary") or "Calendar feed checked."),
            required=False,
        ))
    except Exception as e:
        checks.append(_readiness_check(
            "intel_calendar",
            "Calendar Feed",
            "degraded",
            "Calendar feed could not be refreshed during preflight.",
            required=False,
            detail=str(e),
        ))

    if is_forex:
        checks.append(_readiness_check(
            "intel_sentiment",
            "Fear & Greed",
            "skipped",
            "Crypto Fear & Greed is not used for forex venues.",
            required=False,
        ))
    else:
        try:
            from src.intel.sentiment import get_fear_greed

            fng = await get_fear_greed()
            checks.append(_readiness_check(
                "intel_sentiment",
                "Fear & Greed",
                "degraded" if fng.get("stale") else "ready",
                "Using a cached market sentiment snapshot while the upstream refreshes." if fng.get("stale") else "Crypto market sentiment is healthy.",
                required=False,
            ))
        except Exception as e:
            checks.append(_readiness_check(
                "intel_sentiment",
                "Fear & Greed",
                "degraded",
                "Crypto market sentiment could not be refreshed during preflight.",
                required=False,
                detail=str(e),
            ))

    payload = _finalize_readiness_payload(
        s=s,
        checks=checks,
        market_sections=market_sections,
        warm_snapshot=warm_info,
    )
    s.readiness = payload
    return payload


def _resolve_test_venue_target(requested_venue: str, stored_market: str | None = None) -> tuple[str, str, str]:
    """Resolve a venue test target into (match_key, registry_name, market).

    Saved venues can specify a market mode (spot / futures / forex / etc.).
    Tests should use that stored mode unless the caller explicitly overrides it
    with a suffix like ``binance:futures``.
    """
    requested = (requested_venue or "").lower().strip()
    base, _, suffix = requested.partition(":")
    market = _normalize_market_for_backend_name(base, suffix or stored_market)

    if base == "binance":
        return "binance", f"binance:{market}", market

    return requested, requested, market


def _runtime_config_from_saved_venue(
    *,
    user_id: str | None,
    match: dict[str, Any],
    requested_venue: str,
    is_paper: bool | None = None,
) -> tuple[VenueRuntimeConfig, str, str]:
    """Build a per-user venue runtime config from a saved DB venue row."""
    venue_type = str(match.get("type") or "")
    venue_key = _VENUE_TYPE_TO_NAME.get(venue_type, requested_venue).lower()
    stored_market = str(match.get("market") or _default_market_for_venue_type(venue_type)).lower()
    venue_match_key, venue_registry_name, venue_market = _resolve_test_venue_target(
        requested_venue or venue_key,
        stored_market,
    )
    runtime = VenueRuntimeConfig(
        user_id=user_id,
        venue_id=str(match.get("id") or "") or None,
        venue_name=venue_match_key,
        registry_name=venue_registry_name,
        market=venue_market,
        is_paper=bool(match.get("isPaper", True)) if is_paper is None else bool(is_paper),
        network=str(match.get("network") or ""),
        api_key=str(match.get("apiKey") or ""),
        api_secret=str(match.get("apiSecret") or ""),
        api_passphrase=str(match.get("apiPassphrase") or ""),
        account_id=str(match.get("accountId") or ""),
        meta_api_token=str(match.get("metaApiToken") or ""),
        meta_api_account_id=str(match.get("metaApiAccountId") or ""),
        ccxt_exchange_id=str(match.get("ccxtExchangeId") or ""),
    )
    return runtime, venue_registry_name, venue_market


def _runtime_config_from_inputs(
    *,
    user_id: str | None,
    venue_name: str,
    registry_name: str,
    market: str,
    is_paper: bool,
    api_key: str | None = None,
    api_secret: str | None = None,
    api_passphrase: str = "",
    account_id: str = "",
    network: str = "",
    meta_token: str = "",
    meta_account_id: str = "",
    ccxt_exchange: str = "",
) -> VenueRuntimeConfig:
    return VenueRuntimeConfig(
        user_id=user_id,
        venue_id=None,
        venue_name=venue_name,
        registry_name=registry_name,
        market=market,
        is_paper=is_paper,
        network=network,
        api_key=api_key or "",
        api_secret=api_secret or "",
        api_passphrase=api_passphrase,
        account_id=account_id,
        meta_api_token=meta_token,
        meta_api_account_id=meta_account_id,
        ccxt_exchange_id=ccxt_exchange,
    )

# Per-venue env-var injection so adapters find their credentials
def _inject_venue_env(venue_name: str, market: str, is_paper: bool,
                      api_key: str, api_secret: str, api_passphrase: str,
                      account_id: str, network: str,
                      meta_token: str, meta_account_id: str,
                      ccxt_exchange: str) -> None:
    v = venue_name.lower().split(":")[0]
    if v == "binance":
        os.environ["BINANCE_API_KEY"]    = api_key    or ""
        os.environ["BINANCE_API_SECRET"] = api_secret or ""
        os.environ["BINANCE_MARKET"]     = market
        os.environ["BINANCE_SANDBOX"]    = "true" if is_paper else "false"
    elif v == "hyperliquid":
        if api_key:   os.environ["HYPERLIQUID_PRIVATE_KEY"] = api_key
        if network:   os.environ["HYPERLIQUID_NETWORK"]     = network
    elif v == "oanda":
        if api_key:    os.environ["OANDA_API_TOKEN"]  = api_key
        if account_id: os.environ["OANDA_ACCOUNT_ID"] = account_id
        os.environ["OANDA_ENV"] = "practice" if is_paper else "live"
    elif v == "metatrader" or v in ("mt4", "mt5"):
        if meta_token:      os.environ["METAAPI_TOKEN"]      = meta_token
        if meta_account_id: os.environ["METAAPI_ACCOUNT_ID"] = meta_account_id
        os.environ["MT_IS_PAPER"] = "true" if is_paper else "false"
    elif v == "alpaca":
        if api_key:    os.environ["ALPACA_API_KEY"]    = api_key
        if api_secret: os.environ["ALPACA_API_SECRET"] = api_secret
        os.environ["ALPACA_PAPER"] = "true" if is_paper else "false"
    elif v == "ibkr":
        pass  # IBKR config (host/port/client ID) is env-driven, not per-user for now
    elif v in ("bybit", "okx", "kraken", "coinbase", "ccxt"):
        if api_key:        os.environ["CCXT_API_KEY"]    = api_key
        if api_secret:     os.environ["CCXT_API_SECRET"] = api_secret
        if api_passphrase: os.environ["CCXT_API_PASSPHRASE"] = api_passphrase
        if ccxt_exchange:  os.environ["CCXT_EXCHANGE"]   = ccxt_exchange
        os.environ["CCXT_MARKET"] = market or "spot"
        os.environ["CCXT_SANDBOX"] = "true" if is_paper else "false"
    elif v == "polymarket":
        if api_key:  os.environ["POLYMARKET_ETH_PRIVATE_KEY"] = api_key
        os.environ["POLYMARKET_CHAIN_ID"] = network or "137"
        os.environ["POLYMARKET_IS_PAPER"] = "true" if is_paper else "false"


async def _build_user_bound_venue(clerk_user_id: str, requested_venue: str) -> tuple[Venue, dict[str, Any], str, str] | None:
    """Hydrate a venue adapter from the user's saved credentials."""
    from src.services.supabase_reader import get_user_venues

    v_key = (requested_venue or "").lower().strip().split(":")[0]
    venues = await get_user_venues(clerk_user_id)
    match = None
    for v in venues:
        name = _VENUE_TYPE_TO_NAME.get(v.get("type", ""), "").lower()
        if name == v_key:
            match = v
            break
    if not match:
        return None

    runtime_config, venue_registry_name, venue_market = _runtime_config_from_saved_venue(
        user_id=clerk_user_id,
        match=match,
        requested_venue=v_key,
    )
    venue = build_venue_from_runtime(runtime_config)
    venue.is_paper = runtime_config.is_paper
    return venue, match, venue_registry_name, venue_market


# Asset-class inference per venue
_ASSET_CLASS: dict[str, str] = {
    "hyperliquid": "crypto_perp",
    "binance":     "crypto_spot",   # overridden below for futures
    "bybit":       "crypto_perp",
    "okx":         "crypto_perp",
    "kraken":      "crypto_spot",
    "coinbase":    "crypto_spot",
    "ccxt":        "crypto_spot",
    "oanda":       "forex",
    "metatrader":  "forex",
    "alpaca":      "crypto_spot",   # used loosely for stocks
    "ibkr":        "crypto_spot",
    "polymarket":  "prediction",
}


async def _do_start(
    user_id: str | None,
    venue_name: str,
    symbols: list[str],
    timeframe: str,
    is_paper: bool,
    market: str,
    api_key: str | None,
    api_secret: str | None,
    strategy_type:      str | None = None,
    min_confidence_pct: float = 0.0,
    max_daily_loss_pct: float = 0.0,
    max_trades_per_day: int   = 0,
    loss_cooldown_count: int  = 0,
    paper_capital:      float = 10_000.0,
    _requested_paper:   bool  = True,  # caller's original is_paper before plan check
) -> dict:
    # Timeframe whitelist — rejects garbage strings before they reach the venue
    _VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}
    if timeframe not in _VALID_TIMEFRAMES:
        return {"ok": False, "error": f"Invalid timeframe '{timeframe}'. Valid: {sorted(_VALID_TIMEFRAMES)}"}

    # H-G: Defense-in-depth — re-validate plan even if the Next.js proxy was bypassed.
    is_paper, forced_paper_warning = await _enforce_start_plan_mode(user_id, is_paper)

    # BETA LIVE CAP — hard server-side dollar ceiling during beta.
    # Set BETA_LIVE_CAP_USD=0 in .env to remove after public launch.
    _beta_cap = float(os.getenv("BETA_LIVE_CAP_USD", "500"))
    if not is_paper and _beta_cap > 0:
        logger.info("Beta live cap active: max $%.0f per-trade allocation", _beta_cap)

    final_state = get_state(user_id) if user_id else _state
    previous_status = final_state.status
    # H8: idempotency lock + per-user state binding (no global _state mutation).
    # Each user gets an isolated AgentState. The global _state is only used as a
    # fallback for unauthenticated dev mode — never reassigned here.
    async with _start_lock:
        if final_state.status in ("running", "starting"):
            return {"ok": False, "error": "Your agent is already running" if user_id else "Agent already running"}
        final_state.status = "starting"
        final_state.user_id = user_id

    bundle = await _prepare_agent_start_bundle(
        user_id=user_id,
        venue_name=venue_name,
        market=market,
        is_paper=is_paper,
        api_key=api_key,
        api_secret=api_secret,
    )
    if not bundle.get("ok"):
        final_state.status = previous_status
        final_state.error = bundle.get("error")
        final_state.readiness = None
        logger.error("Venue init failed — state rolled back, previous agent unaffected: %s", bundle.get("error"))
        return {"ok": False, "error": bundle.get("error") or "Venue init failed"}

    v_key = str(bundle["v_key"])
    market = str(bundle["market"])

    candidate_state = AgentState()
    candidate_state.venue = bundle["venue"]
    candidate_state.risk_mgr = bundle["risk_mgr"]
    candidate_state.ai_agent = bundle["ai_agent"]
    candidate_state.symbols = list(symbols)
    candidate_state.timeframe = timeframe
    candidate_state.is_paper = is_paper
    candidate_state.market = market
    candidate_state.venue_name = v_key
    candidate_state.user_id = user_id
    candidate_state.strategy_type = strategy_type or ""

    warm_state = await _load_saved_warm_snapshot(user_id)
    try:
        readiness = await _evaluate_agent_readiness(candidate_state, warm_state=warm_state)
    except Exception as e:
        readiness = {
            "state": "blocked",
            "can_start": False,
            "summary": "Startup preflight could not complete safely.",
            "checks": [
                _readiness_check(
                    "startup_preflight",
                    "Startup Preflight",
                    "blocked",
                    "Startup preflight could not complete safely.",
                    required=True,
                    detail=str(e),
                )
            ],
            "warnings": [],
            "market": {
                "symbols": list(symbols),
                "timeframe": timeframe,
                "venue": v_key,
                "market": market,
                "sections": [],
            },
            "warm_snapshot": {"used": False, "age_s": None, "snapshot_at": None, "snapshot_ts": None, "restored_symbols": []},
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    if not readiness.get("can_start"):
        final_state.status = previous_status
        final_state.error = readiness.get("summary")
        final_state.readiness = readiness
        return {
            "ok": False,
            "error": readiness.get("summary") or "Startup preflight failed",
            "readiness": readiness,
        }

    # All components succeeded and the startup preflight says we are tradable.
    final_state.venue = candidate_state.venue
    final_state.risk_mgr = candidate_state.risk_mgr
    final_state.ai_agent = candidate_state.ai_agent

    final_state.symbols        = symbols
    final_state.timeframe      = timeframe
    final_state.is_paper       = is_paper
    final_state.market         = market
    final_state.venue_name     = v_key
    final_state.status         = "running"
    final_state.user_id        = user_id
    final_state.readiness      = readiness
    # ── Full state reset — prevents any bleed from a previous session ────────
    final_state.decisions.clear()
    final_state.trade_log.clear()
    final_state.logs.clear()
    final_state.timeline            = deque(maxlen=200)
    final_state.account             = {}
    final_state.positions           = []
    final_state.initial_equity      = None   # set fresh on first tick
    final_state.prev_position_pnl   = {}     # prevents ghost close-events from old positions
    final_state.price_cache         = dict(candidate_state.price_cache)
    final_state.candle_cache        = {key: list(value) for key, value in candidate_state.candle_cache.items()}
    final_state.tick_count          = 0
    final_state.error               = None
    final_state.last_tick_at        = datetime.now(timezone.utc)
    final_state.connected_account_cache = None
    final_state.connected_positions_cache = []
    final_state.connected_snapshot_at = None
    final_state.warm_snapshot_at    = candidate_state.warm_snapshot_at
    final_state.min_confidence_pct  = min_confidence_pct
    final_state.max_daily_loss_pct  = max_daily_loss_pct
    final_state.max_trades_per_day  = max_trades_per_day
    final_state.loss_cooldown_count = loss_cooldown_count
    final_state.strategy_type       = strategy_type or ""
    final_state.daily_loss_usd      = 0.0
    final_state.daily_trade_count   = 0
    final_state.consecutive_losses  = 0
    final_state.day_reset_at        = datetime.now(timezone.utc).date().isoformat()
    # Reset paper trading simulation on every fresh start
    if is_paper:
        _cap = max(100.0, float(paper_capital or 10_000.0))
        async with final_state._paper_lock:
            final_state.paper_balance   = _cap
            final_state.paper_positions = []
        final_state.initial_equity = _cap

    # Strategy persona — apply risk overrides and inject prompt addendum
    if strategy_type:
        try:
            from src.agent.strategy_personas import get_persona, get_risk_overrides, build_persona_prompt
            persona = get_persona(strategy_type)
            if persona and final_state.risk_mgr:
                for k, v in get_risk_overrides(strategy_type).items():
                    final_state.risk_mgr.config[k] = v
            if persona and final_state.ai_agent:
                final_state.ai_agent.system_prompt_addendum = build_persona_prompt(strategy_type)
        except Exception as e:
            logger.warning("Strategy persona load failed: %s", e)

    final_state.log(
        "Startup preflight passed — venue, prices, candles, indicators, and AI governance are ready."
    )
    for warning in readiness.get("warnings", []):
        final_state.log(f"Startup readiness warning: {warning}")

    # Persist to DB so server restart can resume
    if user_id:
        try:
            from src.services.supabase_reader import upsert_agent_run
            final_state.agent_run_id = await upsert_agent_run(user_id, v_key, symbols, timeframe, is_paper, market, True)
        except Exception as e:
            logger.warning("AgentRun persist failed: %s", e)
        await _persist_warm_snapshot(final_state, market_sections=readiness.get("market", {}).get("sections"))
        asyncio.create_task(_persist_audit(
            user_id, "agent_start", None, None,
            {"venue": v_key, "symbols": symbols, "timeframe": timeframe, "is_paper": is_paper},
        ))
        asyncio.create_task(capture_posthog("agent_started", {
            "user_id": user_id,
            "plan": await _get_user_plan(user_id),
            "mode": "paper" if is_paper else "live",
            "venue": v_key,
            "persona": strategy_type or "",
            "provider": final_state.ai_agent.provider.name if final_state.ai_agent else "",
            "trace_id": new_trace_id(),
            "success": True,
            "reason_code": "agent_started",
        }))
        asyncio.create_task(capture_posthog("paper_mode_started" if is_paper else "live_mode_started", {
            "user_id": user_id,
            "plan": await _get_user_plan(user_id),
            "mode": "paper" if is_paper else "live",
            "venue": v_key,
            "persona": strategy_type or "",
            "provider": final_state.ai_agent.provider.name if final_state.ai_agent else "",
            "trace_id": new_trace_id(),
            "success": True,
            "reason_code": "mode_started",
        }))

    final_state._loop_task = asyncio.create_task(_run_loop_for(final_state))

    result: dict = {
        "ok": True,
        "venue": v_key,
        "symbols": symbols,
        "timeframe": timeframe,
        "paper": is_paper,
        "readiness": readiness,
    }
    if forced_paper_warning:
        result["warning"] = forced_paper_warning
    return result


@app.post("/api/agent/start")
async def start_agent(request: Request, req: StartRequest):
    user_id = await _resolve_request_user_id(request, req.userId)
    if req.userId and not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = await _do_start(
        user_id=user_id,
        venue_name=req.venue,
        symbols=req.symbols,
        timeframe=req.timeframe,
        is_paper=req.isPaper,
        market=req.market,
        api_key=req.apiKey,
        api_secret=req.apiSecret,
        strategy_type=req.strategyType,
        min_confidence_pct=req.minConfidencePct,
        max_daily_loss_pct=req.maxDailyLossPct,
        max_trades_per_day=req.maxTradesPerDay,
        loss_cooldown_count=req.lossCooldownCount,
        paper_capital=req.paperCapital,
        _requested_paper=req.isPaper,
    )
    if not result.get("ok", False):
        raise HTTPException(status_code=409, detail=result.get("error") or "Could not start agent")
    return result


@app.get("/api/agent/readiness")
async def get_agent_readiness(
    request: Request,
    venue: str = "binance",
    symbols: str = "BTC/USDT",
    timeframe: str = "1h",
    market: str = "",
    isPaper: bool = True,
    userId: Optional[str] = None,
):
    resolved_user_id = await _resolve_request_user_id(request, userId)
    if userId and not resolved_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    requested_symbols = [part.strip().upper() for part in symbols.split(",") if part.strip()]
    if not requested_symbols:
        requested_symbols = ["BTC/USDT"]
    try:
        validated = StartRequest(
            userId=resolved_user_id,
            venue=venue,
            symbols=requested_symbols,
            timeframe=timeframe,
            isPaper=isPaper,
            market=market,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    effective_is_paper, forced_paper_warning = await _enforce_start_plan_mode(resolved_user_id, validated.isPaper)
    bundle = await _prepare_agent_start_bundle(
        user_id=resolved_user_id,
        venue_name=validated.venue,
        market=validated.market,
        is_paper=effective_is_paper,
        api_key=validated.apiKey,
        api_secret=validated.apiSecret,
    )

    if not bundle.get("ok"):
        payload = {
            "state": "blocked",
            "can_start": False,
            "summary": bundle.get("error") or "Venue init failed",
            "checks": [
                _readiness_check(
                    "venue_init",
                    "Venue Setup",
                    "blocked",
                    bundle.get("error") or "Venue init failed",
                    required=True,
                )
            ],
            "warnings": [forced_paper_warning] if forced_paper_warning else [],
            "market": {
                "symbols": validated.symbols,
                "timeframe": validated.timeframe,
                "venue": bundle.get("v_key") or validated.venue,
                "market": bundle.get("market") or validated.market,
                "sections": [],
            },
            "warm_snapshot": {"used": False, "age_s": None, "snapshot_at": None, "snapshot_ts": None, "restored_symbols": []},
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        get_state(resolved_user_id).readiness = payload
        return payload

    candidate_state = AgentState()
    candidate_state.venue = bundle["venue"]
    candidate_state.risk_mgr = bundle["risk_mgr"]
    candidate_state.ai_agent = bundle["ai_agent"]
    candidate_state.symbols = list(validated.symbols)
    candidate_state.timeframe = validated.timeframe
    candidate_state.is_paper = effective_is_paper
    candidate_state.market = str(bundle["market"])
    candidate_state.venue_name = str(bundle["v_key"])
    candidate_state.user_id = resolved_user_id

    warm_state = await _load_saved_warm_snapshot(resolved_user_id)
    readiness = await _evaluate_agent_readiness(candidate_state, warm_state=warm_state)
    if forced_paper_warning:
        readiness["warnings"] = [*readiness.get("warnings", []), forced_paper_warning]
    get_state(resolved_user_id).readiness = readiness
    return readiness


@app.get("/api/agent/personas")
async def list_personas():
    from src.agent.strategy_personas import list_personas as _list
    return {"personas": [p.to_dict() for p in _list()]}


@app.get("/api/agent/timeline")
async def get_timeline(request: Request, userId: Optional[str] = None, limit: int = 50):
    resolved_user_id = await _resolve_request_user_id(request, userId)
    if userId and not resolved_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    s = get_state(resolved_user_id)
    return {"timeline": list(s.timeline)[-limit:]}


@app.get("/api/agent/personas/leaderboard")
async def personas_leaderboard():
    from src.agent.strategy_personas import list_personas as _list_personas, PERSONAS
    rows = []
    for p in _list_personas():
        lb = _persona_leaderboard.get(p.id, {})
        total  = lb.get("total_trades", 0)
        wins   = lb.get("wins", 0)
        gross  = lb.get("gross_pnl", 0.0)
        rows.append({
            **p.to_dict(),
            "sessions":      lb.get("sessions", 0),
            "total_trades":  total,
            "win_rate_pct":  round(wins / total * 100, 1) if total else None,
            "gross_pnl":     gross,
            "active":        any(
                ss.strategy_type == p.id and ss.status == "running"
                for ss in list(_states.values()) + [_state]
            ),
        })
    # Sort by gross_pnl desc
    rows.sort(key=lambda r: r["gross_pnl"], reverse=True)
    return {"leaderboard": rows}


@app.post("/api/agent/stop")
async def stop_agent(request: Request, body: dict = {}):
    requested_user_id = body.get("userId") if body else None
    user_id = await _resolve_request_user_id(request, requested_user_id)
    if requested_user_id and not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Resolve the correct per-user state — same pattern as every other endpoint
    s = get_state(user_id)
    if s.status not in ("running", "starting"):
        return {"ok": False, "error": "Agent is not running"}
    s.status = "stopping"

    # Cancel main loop + ALL child tasks (price stream, dead-man's-switch,
    # LLM worker, order worker). Without this, child tasks keep running
    # after stop, leaking WS connections and potentially executing trades.
    tasks_to_cancel = [
        s._loop_task, s._price_task, s._deadman_task,
        s._llm_worker_task, s._order_worker_task,
    ]
    for t in tasks_to_cancel:
        if t and not t.done():
            t.cancel()
    # Wait for tasks to actually finish their cleanup
    try:
        await asyncio.wait_for(
            asyncio.gather(*[t for t in tasks_to_cancel if t], return_exceptions=True),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        logger.warning("agent stop: some tasks did not exit within 5s")

    s.status = "stopped"
    # Broadcast so all connected WebSocket clients update immediately
    await _broadcast({"type": "status_update", "status": "stopped", "reason": "user_stop", "paper": s.is_paper}, s.user_id)
    if s.user_id:
        try:
            from src.services.supabase_reader import upsert_agent_run
            await upsert_agent_run(
                s.user_id, s.venue_name, s.symbols, s.timeframe,
                s.is_paper, s.market, False,
            )
        except Exception:
            pass
        asyncio.create_task(_persist_audit(
            s.user_id, "agent_stop", None, None, {"venue": s.venue_name},
        ))
        asyncio.create_task(capture_posthog("agent_stopped", {
            "user_id": s.user_id,
            "plan": await _get_user_plan(s.user_id),
            "mode": "paper" if s.is_paper else "live",
            "venue": s.venue_name,
            "persona": s.strategy_type or "",
            "provider": s.ai_agent.provider.name if s.ai_agent else "",
            "trace_id": new_trace_id(),
            "success": True,
            "reason_code": "agent_stopped",
        }))
    return {"ok": True}


class StrategyRequest(BaseModel):
    text:   str
    userId: Optional[str] = None


class AITextStreamRequest(BaseModel):
    text: str
    userId: Optional[str] = None
    symbol: str = ""
    venue: str = "binance"


@app.post("/api/strategies")
async def create_strategy(request: Request, req: StrategyRequest):
    user_id = await _resolve_request_user_id(request, req.userId)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from src.agent.nl_parser import parse_nl_rule
    from src.services.supabase_reader import create_strategy_rule

    ai_ctx = AIRequestContext(
        user_id=user_id,
        trace_id=new_trace_id(),
        plan=await _get_user_plan(user_id),
        action="manual_command_parse",
        provider="groq",
        model="",
        mode="paper",
        venue="strategy_rules",
        endpoint="/api/strategies",
        stream=False,
    )
    try:
        rule = await parse_nl_rule(req.text, ai_context=ai_ctx)
    except AIError as error:
        raise HTTPException(status_code=error.http_status, detail=safe_error_payload(error)["error"])
    if not rule:
        raise HTTPException(status_code=422, detail="Could not parse rule")
    saved = await create_strategy_rule(user_id, rule)
    if not saved:
        raise HTTPException(status_code=500, detail="Could not save rule")
    return {"ok": True, "rule": {"id": rule.id, "condition": rule.condition, "action": rule.action, "symbol": rule.symbol, "threshold": rule.threshold}}


@app.post("/api/strategies/stream")
async def create_strategy_stream(request: Request, req: StrategyRequest):
    user_id = await _resolve_request_user_id(request, req.userId)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from src.agent.nl_parser import parse_nl_rule
    from src.services.supabase_reader import create_strategy_rule

    async def event_stream():
        events: list[dict] = []

        async def collect(event: dict):
            events.append(event)

        ai_ctx = AIRequestContext(
            user_id=user_id,
            trace_id=new_trace_id(),
            plan=await _get_user_plan(user_id),
            action="manual_command_parse",
            provider="groq",
            model="",
            mode="paper",
            venue="strategy_rules",
            endpoint="/api/strategies/stream",
            stream=True,
        )
        try:
            rule = await parse_nl_rule(req.text, ai_context=ai_ctx, stream_handler=collect)
            for event in events:
                yield f"data: {json.dumps(event, default=str)}\n\n"
            if not rule:
                yield f"data: {json.dumps({'type': 'ai_stream_failed', 'trace_id': ai_ctx.trace_id, 'message': 'Could not parse rule safely.'})}\n\n"
                return
            saved = await create_strategy_rule(user_id, rule)
            payload = {
                "type": "strategy_saved",
                "trace_id": ai_ctx.trace_id,
                "final": True,
                "rule": {
                    "id": rule.id,
                    "condition": rule.condition,
                    "action": rule.action,
                    "symbol": rule.symbol,
                    "threshold": rule.threshold,
                },
                "saved": bool(saved),
            }
            yield f"data: {json.dumps(payload)}\n\n"
        except AIError as error:
            yield f"data: {json.dumps({'type': 'ai_stream_failed', **safe_error_payload(error)['error']})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/explanations/stream")
async def explanation_stream(request: Request, req: AITextStreamRequest):
    user_id = await _require_request_user_id(request, req.userId)
    from src.agent.providers.factory import get_provider

    async def event_stream():
        provider = get_provider()
        ai_ctx = AIRequestContext(
            user_id=user_id,
            trace_id=new_trace_id(),
            plan=await _get_user_plan(user_id),
            action="trade_explanation",
            provider=provider.name,
            model=provider.model,
            mode="paper",
            venue=req.venue or "binance",
            symbol=req.symbol,
            endpoint="/api/explanations/stream",
            stream=True,
        )
        events = await governed_stream(
            provider=provider,
            system="You explain a completed trading decision clearly and safely. Keep it concise and actionable.",
            messages=[{"role": "user", "content": req.text}],
            max_tokens=600,
            context=ai_ctx,
        )
        for event in events:
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/backtest/commentary/stream")
async def backtest_commentary_stream(request: Request, req: AITextStreamRequest):
    user_id = await _require_request_user_id(request, req.userId)
    from src.agent.providers.factory import get_provider

    async def event_stream():
        provider = get_provider()
        ai_ctx = AIRequestContext(
            user_id=user_id,
            trace_id=new_trace_id(),
            plan=await _get_user_plan(user_id),
            action="backtest_commentary",
            provider=provider.name,
            model=provider.model,
            mode="paper",
            venue=req.venue or "binance",
            symbol=req.symbol,
            endpoint="/api/backtest/commentary/stream",
            stream=True,
        )
        events = await governed_stream(
            provider=provider,
            system="You summarize a backtest result without making live trading guarantees. Mention risks and limitations.",
            messages=[{"role": "user", "content": req.text}],
            max_tokens=800,
            context=ai_ctx,
        )
        for event in events:
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/strategies")
async def list_strategies(request: Request, userId: Optional[str] = None):
    user_id = await _resolve_request_user_id(request, userId)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from src.services.supabase_reader import list_strategy_rules

    rules = await list_strategy_rules(user_id, active_only=False)
    return {"rules": [{
        "id": r.get("id"),
        "condition": r.get("condition") or r.get("text"),
        "action": r.get("action"),
        "symbol": r.get("symbol"),
        "active": r.get("isActive", True),
    } for r in rules]}


@app.delete("/api/strategies/{rule_id}")
async def delete_strategy(rule_id: str, request: Request, userId: Optional[str] = None):
    user_id = await _resolve_request_user_id(request, userId)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from src.services.supabase_reader import delete_strategy_rule

    deleted = await delete_strategy_rule(user_id, rule_id)
    return {"ok": deleted}


class VenueTestRequest(BaseModel):
    userId:  str
    venue:   str
    isPaper: bool = True


@app.post("/api/venues/test")
async def test_venue(request: Request, req: VenueTestRequest):
    """Initialise the venue adapter with the user's stored credentials and
    call get_balances() as a smoke test. Returns {ok, balance, currency}.

    B2: Venue-specific error messages so users understand exactly what is wrong.
    """
    user_id = await _require_request_user_id(request, req.userId)
    venue_match_key, _, _ = _resolve_test_venue_target(req.venue)
    try:
        from src.services.supabase_reader import get_user_venues
        venues = await get_user_venues(user_id)
        match = None
        for v in venues:
            name = _VENUE_TYPE_TO_NAME.get(v.get("type", ""), "").lower()
            if name == venue_match_key:
                match = v; break
        if not match:
            return {"ok": False, "error": f"No {req.venue} venue configured. Add credentials in Settings → Venues first."}

        # ── Per-venue pre-flight credential checks (clearer errors) ──────────
        api_key   = match.get("apiKey") or ""
        api_sec   = match.get("apiSecret") or ""
        passph    = match.get("apiPassphrase") or ""
        acct_id   = match.get("accountId") or ""
        meta_tok  = match.get("metaApiToken") or ""
        meta_acct = match.get("metaApiAccountId") or ""
        stored_market = str(match.get("market") or _default_market_for_venue_type(match.get("type"))).lower()
        venue_match_key, venue_registry_name, venue_market = _resolve_test_venue_target(req.venue, stored_market)

        if venue_match_key in ("binance", "bybit", "kraken", "coinbase", "binanceusdm"):
            if not api_key or not api_sec:
                return {"ok": False, "error": f"{req.venue} requires API key + secret."}
            # Validate Binance key format — should be ~64 alphanumeric chars
            if venue_match_key in ("binance", "binanceusdm"):
                if len(api_key) < 20:
                    return {"ok": False, "error": (
                        f"Binance API key looks wrong — only {len(api_key)} characters. "
                        "A valid key is 64 characters. Check Settings → Venues and re-paste it."
                    )}
                if len(api_sec) < 20:
                    return {"ok": False, "error": (
                        f"Binance API secret looks wrong — only {len(api_sec)} characters. "
                        "A valid secret is 64 characters. Check Settings → Venues and re-paste it."
                    )}
                if not api_key.replace("-", "").replace("_", "").isalnum():
                    return {"ok": False, "error": (
                        "Binance API key contains invalid characters. "
                        "Keys are alphanumeric only. Re-paste carefully."
                    )}
        if venue_match_key == "okx" and (not api_key or not api_sec or not passph):
            return {"ok": False, "error": "OKX requires API key, secret, AND passphrase."}
        if venue_match_key == "hyperliquid" and not api_key:
            return {"ok": False, "error": "Hyperliquid requires a private key (your wallet seed in API Key field)."}
        if venue_match_key == "oanda":
            if not api_key:  return {"ok": False, "error": "OANDA requires an API token (Account → API Access)."}
            if not acct_id:  return {"ok": False, "error": "OANDA requires an Account ID (e.g. 101-001-12345-001)."}
        if venue_match_key == "metatrader":
            if not meta_tok:   return {"ok": False, "error": "MetaTrader requires a MetaAPI cloud token. Sign up at metaapi.cloud."}
            if not meta_acct:  return {"ok": False, "error": "MetaTrader requires a MetaAPI account ID."}
        if venue_match_key == "alpaca":
            if not api_key or not api_sec:
                return {"ok": False, "error": "Alpaca requires API key + secret. Get them from app.alpaca.markets."}
        if venue_match_key == "polymarket":
            if not api_key:
                return {"ok": False, "error": "Polymarket requires the private key of a dedicated trading wallet (not your main wallet). Coming soon: Connect Wallet."}
            if not (api_key.startswith("0x") and len(api_key) >= 64):
                return {"ok": False, "error": "Polymarket private key must be 0x-prefixed and 32 bytes long."}

        runtime_config, venue_registry_name, venue_market = _runtime_config_from_saved_venue(
            user_id=user_id,
            match=match,
            requested_venue=req.venue,
            is_paper=req.isPaper,
        )
        venue = build_venue_from_runtime(runtime_config)
        balances = await venue.get_balances()

        # Phase 4: Withdrawal-permission warning for Binance / CCXT venues.
        # If the user's API key has withdrawal rights enabled, surface a warning so
        # they regenerate it as trading-only.
        warning = None
        if venue_match_key in ("binance", "bybit", "kraken", "coinbase", "ccxt"):
            try:
                client = getattr(venue, "client", None)
                info = None
                if client and hasattr(client, "fetchAccountInfo"):
                    info = await asyncio.to_thread(client.fetchAccountInfo)
                elif client and hasattr(client, "private_get_account"):
                    info = await asyncio.to_thread(client.private_get_account)
                if isinstance(info, dict) and info.get("canWithdraw"):
                    warning = (
                        "Your API key has WITHDRAWAL permission enabled. "
                        "For safety, regenerate the key with only 'Enable Trading' checked "
                        "(uncheck 'Enable Withdrawals')."
                    )
            except Exception:
                pass  # non-fatal; not all venues expose this

        if balances:
            b = balances[0]
            result = {"ok": True, "currency": b.currency, "balance": b.total, "available": b.available, "venue": req.venue}
            asyncio.create_task(capture_posthog("venue_connected", {
                "user_id": user_id,
                "plan": await _get_user_plan(user_id),
                "mode": "paper" if req.isPaper else "live",
                "venue": req.venue,
                "persona": "",
                "provider": "",
                "trace_id": new_trace_id(),
                "success": True,
                "reason_code": "venue_connected",
            }))
            if warning: result["warning"] = warning
            return result
        result = {"ok": True, "currency": "—", "balance": 0, "available": 0, "venue": req.venue,
                  "note": "Connection succeeded but no balances returned (account may be empty)."}
        asyncio.create_task(capture_posthog("venue_connected", {
            "user_id": user_id,
            "plan": await _get_user_plan(user_id),
            "mode": "paper" if req.isPaper else "live",
            "venue": req.venue,
            "persona": "",
            "provider": "",
            "trace_id": new_trace_id(),
            "success": True,
            "reason_code": "venue_connected_empty",
        }))
        if warning: result["warning"] = warning
        return result
    except Exception as e:
        msg = str(e)
        # Map common errors to user-friendly hints
        if "Invalid API" in msg or "Unauthorized" in msg or "401" in msg:
            hint = "Invalid API key / secret. Check the credentials in Settings."
        elif "403" in msg or "Forbidden" in msg:
            hint = "API key lacks the required permissions. For trading enable trade permission."
        elif "rate" in msg.lower() and "limit" in msg.lower():
            hint = "Rate-limited by the exchange. Try again in a minute."
        elif "ECONNREFUSED" in msg or "Connection" in msg or "timeout" in msg.lower():
            hint = "Network error reaching the exchange. Try again."
        else:
            hint = msg[:200]
        logger.warning("venue test failed for %s: %s", venue_match_key, e)
        asyncio.create_task(capture_posthog("venue_connection_failed", {
            "user_id": user_id,
            "plan": await _get_user_plan(user_id),
            "mode": "paper" if req.isPaper else "live",
            "venue": req.venue,
            "persona": "",
            "provider": "",
            "trace_id": new_trace_id(),
            "success": False,
            "reason_code": "venue_connection_failed",
        }))
        return {"ok": False, "error": hint, "raw": msg[:500]}


class BacktestRequest(BaseModel):
    symbol:          str   = "BTC/USDT"
    venue:           str   = "binance"
    timeframe:       str   = "1h"
    days:            int   = 30
    initial_capital: float = 10_000.0
    strategy:        str   = "rsi"   # "rsi" | "llm"
    asset_class:     str   = ""      # auto-detected from venue when blank


@app.get("/api/rag-memory")
async def get_rag_memories(request: Request, userId: Optional[str] = None, limit: int = 50):
    """Return stored RAG decision embeddings for a user."""
    db_url = os.getenv("DATABASE_URL")
    clerk_user_id = await _resolve_request_user_id(request, userId)
    if not db_url or not clerk_user_id:
        return {"memories": []}
    try:
        import asyncpg
        conn = await asyncpg.connect(db_url, timeout=5, statement_cache_size=0)
        try:
            rows = await conn.fetch(
                'SELECT de."id",de."asset",de."action",de."rationale",de."qualityScore",de."createdAt" '
                'FROM "DecisionEmbedding" de '
                'JOIN "User" u ON u.id = de."userId" '
                'WHERE u."clerkId"=$1 ORDER BY de."createdAt" DESC LIMIT $2',
                clerk_user_id, limit,
            )
            return {"memories": [dict(r) for r in rows]}
        finally:
            await conn.close()
    except Exception as e:
        return {"memories": [], "error": str(e)}


@app.delete("/api/rag-memory/{memory_id}")
async def delete_rag_memory(request: Request, memory_id: str, userId: Optional[str] = None):
    db_url = os.getenv("DATABASE_URL")
    clerk_user_id = await _require_request_user_id(request, userId)
    if not db_url:
        raise HTTPException(status_code=400, detail="Database not configured")
    try:
        import asyncpg
        conn = await asyncpg.connect(db_url, timeout=5, statement_cache_size=0)
        try:
            await conn.execute(
                'DELETE FROM "DecisionEmbedding" de USING "User" u '
                'WHERE de."id"=$1 AND de."userId" = u.id AND u."clerkId"=$2',
                memory_id, clerk_user_id,
            )
        finally:
            await conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}


@app.get("/api/intel/summary")
async def get_intel_summary(request: Request, userId: Optional[str] = None):
    """Aggregated macro intel for the dashboard MacroIntelStrip widget."""
    userId = await _resolve_request_user_id(request, userId)
    s = get_state(userId)

    result: dict = {}
    try:
        from src.intel.sentiment import get_fear_greed
        result["fear_greed"] = await get_fear_greed()
    except Exception:
        pass

    if s.symbols and s.venue:
        mtf_data: dict = {}
        news_data: dict = {}
        for sym in s.symbols[:4]:
            try:
                from src.intel.mtf_confluence import compute_mtf_confluence
                mtf_data[sym] = await compute_mtf_confluence(s.venue, sym)
            except Exception:
                pass
            try:
                from src.intel.news import get_news_sentiment
                news_data[sym] = await get_news_sentiment(sym)
            except Exception:
                pass
        if mtf_data:
            result["mtf"] = mtf_data
        if news_data:
            result["news"] = news_data
        try:
            from src.intel.correlation import compute_correlation_matrix, format_matrix_summary
            corr = compute_correlation_matrix(s.candle_cache, s.symbols, s.timeframe)
            result["correlation"] = format_matrix_summary(corr)
        except Exception:
            pass
    return result


@app.get("/api/calendar/next")
async def get_calendar_next():
    """Return the next high-impact economic event label for the StatusBar."""
    try:
        from src.intel.economic_calendar import next_event_summary
        label = await next_event_summary()
        return {"next_event": label}
    except Exception:
        return {"next_event": ""}


@app.get("/api/calendar/all")
async def get_calendar_all():
    """Return all upcoming high-impact events for the /calendar page."""
    try:
        from src.intel.economic_calendar import get_upcoming_events
        events = await get_upcoming_events()
        return {"events": events}
    except Exception as e:
        return {"events": [], "error": str(e)}


@app.get("/api/var")
async def get_var(request: Request, simulations: int = 10000, userId: Optional[str] = None):
    """Value at Risk — Monte Carlo + parametric, sourced from EquityPoint history."""
    from src.risk.var import monte_carlo_var, parametric_var
    clerk_user_id = await _resolve_request_user_id(request, userId)
    s = get_state(clerk_user_id) if clerk_user_id else None
    equity_vals: list[float] = []

    # Primary: read real equity history from EquityPoint table
    if clerk_user_id:
        try:
            import asyncpg
            db_url = os.getenv("DATABASE_URL", "")
            if db_url:
                conn = await asyncpg.connect(db_url, timeout=5, statement_cache_size=0)
                try:
                    rows = await conn.fetch(
                        'SELECT ep.equity FROM "EquityPoint" ep '
                        'JOIN "User" u ON u.id = ep."userId" '
                        'WHERE u."clerkId" = $1 ORDER BY ep."createdAt" DESC LIMIT 500',
                        clerk_user_id,
                    )
                    equity_vals = [float(r["equity"]) for r in rows]
                finally:
                    await conn.close()
        except Exception:
            pass

    # Fallback: in-memory account snapshot
    if not equity_vals and s and s.account:
        equity_vals = [float(s.account.get("equity", 0))]

    if not equity_vals or len(equity_vals) < 5:
        return {"error": "Not enough equity history yet — run the agent for a few ticks first"}

    mc   = monte_carlo_var(equity_vals, simulations=min(simulations, 10_000))
    para = parametric_var(equity_vals)
    return {"monte_carlo": mc, "parametric": para, "data_points": len(equity_vals)}


@app.get("/api/price/live")
async def get_price_live(
    request: Request,
    symbol: str,
    venue: str | None = None,
    userId: str | None = None,
):
    """Live mid-market price from the user's connected venue.

    Stream-replacement endpoint for the chart so forex/stocks users see
    the same price as their broker without needing to start the agent.
    Falls back to global state's venue if user_id is not provided.
    Always validates the internal token if PYTHON_INTERNAL_TOKEN is set.
    """
    userId = await _resolve_request_user_id(request, userId)

    # 1) Try the running agent's venue first (cheapest — already authenticated)
    s = get_state(userId) if userId else _state
    if s and getattr(s, "venue", None) and s.status in ("running", "stopping"):
        try:
            t = await s.venue.get_ticker(symbol)
            if t and getattr(t, "last", None):
                server_ts = int(time.time())
                return {
                    "price":             float(t.last),
                    "bid":               float(getattr(t, "bid",  0) or 0) or None,
                    "ask":               float(getattr(t, "ask",  0) or 0) or None,
                    "ts":                server_ts,
                    "exchange_ts":       None,
                    "symbol":            symbol,
                    "venue":             s.venue_name,
                    "source":            "agent",
                    "transport":         "polling",
                    "exchange_timezone": _exchange_timezone_for_venue(s.venue_name),
                }
        except Exception:
            pass

    # 2) Build a venue from the user's stored credentials and fetch ticker
    if userId and venue:
        v_key = venue.lower()
        try:
            bound = await _build_user_bound_venue(userId, v_key)
            if bound:
                v_obj, _match, _venue_registry_name, _venue_market = bound
                t = await v_obj.get_ticker(symbol)
                if t and getattr(t, "last", None):
                    server_ts = int(time.time())
                    return {
                        "price":             float(t.last),
                        "bid":               float(getattr(t, "bid",  0) or 0) or None,
                        "ask":               float(getattr(t, "ask",  0) or 0) or None,
                        "ts":                server_ts,
                        "exchange_ts":       None,
                        "symbol":            symbol,
                        "venue":             v_key,
                        "source":            "venue",
                        "transport":         "polling",
                        "exchange_timezone": _exchange_timezone_for_venue(v_key),
                    }
        except Exception as e:
            logger.warning("price/live venue fetch failed for %s: %s", venue, e)

    return {"error": "no live price available", "symbol": symbol}


@app.post("/api/backtest/run")
async def run_backtest(request: Request, req: BacktestRequest):
    """Run a strategy backtest and return equity curve + metrics."""
    try:
        from src.backtesting.engine import run_backtest_json
        user_id = await _resolve_request_user_id(request)
        # Resolve asset_class: use provided value or auto-detect from venue name
        v_key = req.venue.lower().split(":")[0]
        resolved_ac = req.asset_class or _ASSET_CLASS.get(v_key, "crypto_perp")
        ai_ctx = None
        if req.strategy == "llm" and user_id:
            ai_ctx = AIRequestContext(
                user_id=user_id,
                trace_id=new_trace_id(),
                plan=await _get_user_plan(user_id),
                action="backtest_commentary",
                provider="groq",
                model="",
                mode="paper",
                venue=req.venue,
                symbol=req.symbol,
                endpoint="/api/backtest/run",
            )
        result = await run_backtest_json(
            venue=req.venue,
            symbol=req.symbol,
            timeframe=req.timeframe,
            days=req.days,
            initial_capital=req.initial_capital,
            strategy=req.strategy,
            asset_class=resolved_ac,
            ai_context=ai_ctx,
        )
        return result
    except AIError as e:
        raise HTTPException(status_code=e.http_status, detail=safe_error_payload(e)["error"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_VALID_SIGNAL_ACTIONS = {"buy", "sell", "close"}

class SignalRequest(BaseModel):
    source:   str = "tradingview"
    action:   str                     # buy | sell | close
    symbol:   str
    size_usd: float = Field(default=0.0, ge=0.0, le=100_000.0)
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    venue_id: Optional[str]  = None
    user_id:  Optional[str]  = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v.lower() not in _VALID_SIGNAL_ACTIONS:
            raise ValueError(f"action must be one of {_VALID_SIGNAL_ACTIONS}")
        return v.lower()

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        clean = v.strip().upper()
        if not _SYMBOL_RE.match(clean):
            raise ValueError("symbol must be 1-20 uppercase alphanumeric characters / - _")
        return clean


@app.post("/api/agent/execute-signal")
async def execute_signal(request: Request, req: SignalRequest):
    """Execute an external signal (TradingView webhook) through the same
    RiskManager pipeline as autonomous agent decisions.

    Phase 8: Routes to the correct per-user state via user_id, then validates
    venue ownership if venue_id is supplied.
    """
    # HMAC signature check — enforced when TRADINGVIEW_WEBHOOK_SECRET is set.
    # WARNING: req.user_id comes from the untrusted webhook payload. We must
    # validate the HMAC signature before trusting it. If no secret is configured
    # and a user_id is supplied, we reject the request to prevent spoofing.
    secret = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
    body_bytes = await request.body()
    if secret:
        import hmac as _hmac, hashlib as _hashlib
        sig = request.headers.get("X-Signature", "")
        expected = _hmac.new(secret.encode(), body_bytes, _hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(sig, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        # Signature verified — user_id from payload is now trusted
    elif req.user_id:
        # No shared secret configured but caller is supplying a user_id.
        # Without signature verification we cannot trust the payload user_id —
        # reject to prevent an unauthenticated caller from routing to any user's agent.
        raise HTTPException(
            status_code=401,
            detail="TRADINGVIEW_WEBHOOK_SECRET is not configured; cannot trust user_id in unsigned payload",
        )

    # Resolve state: prefer per-user if user_id supplied (and verified above), else global
    s = get_state(req.user_id) if req.user_id else _state

    if req.action not in ("buy", "sell", "close"):
        raise HTTPException(status_code=400, detail="action must be buy | sell | close")

    if s.risk_mgr is None or s.venue is None:
        raise HTTPException(status_code=409, detail="Agent not running — start the agent first, or set user_id in the webhook payload")

    equity  = s.account.get("equity", 0.0)
    balance = s.account.get("balance", 0.0)

    trade = {
        "action":         req.action,
        "asset":          req.symbol,
        "allocation_usd": req.size_usd,
        "current_price":  s.price_cache.get(req.symbol.replace("/", ""), 0),
        "sl_price":       req.sl_price,
        "tp_price":       req.tp_price,
    }
    acc_state = {"total_value": equity, "balance": balance, "positions": s.positions}
    ok, reason, trade = s.risk_mgr.validate_trade(trade, acc_state, s.initial_equity or 0)

    if not ok:
        await _notifier.emit(TradingEvent(
            kind="circuit_breaker_tripped", venue="binance", symbol=req.symbol,
            message=f"[TV signal] Risk blocked {req.action.upper()} {req.symbol}: {reason}",
        ))
        return {"ok": False, "blocked": True, "reason": reason}

    price = trade["current_price"]
    if req.action == "close":
        try:
            await s.venue.close_position(req.symbol)
            s.log(f"[TV] CLOSE {req.symbol}")
            return {"ok": True, "action": "close", "symbol": req.symbol}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    if price <= 0:
        return {"ok": False, "error": f"Price unknown for {req.symbol}"}

    qty, exec_alloc = _resolve_execution_quantity(s, req.action, req.symbol, req.size_usd, price)
    if qty <= 0:
        return {"ok": False, "error": f"No spot holding available to sell for {req.symbol}"}
    try:
        await s.venue.place_order(
            symbol=req.symbol, side=req.action,
            quantity=qty, order_type="market",
            stop_loss=trade.get("sl_price"), take_profit=trade.get("tp_price"),
        )
        s.log(f"[TV signal] {req.action.upper()} {req.symbol} qty={qty:.6f} @ ~${price}")
        s.trade_log.append({"action": req.action, "price": price, "qty": qty, "source": "tradingview"})
        await _broadcast({
            "type": "trade_executed",
            "data": {"symbol": req.symbol, "action": req.action, "price": price, "qty": qty, "source": "tradingview"},
        })
        await _notifier.emit(TradingEvent(
            kind="trade_opened", venue=s.venue_name, symbol=req.symbol,
            message=f"[TradingView] {req.action.upper()} {qty:.6f} @ ${price:.4f}",
        ))
        if s.user_id:
            asyncio.create_task(_persist_trade(
                s.user_id, symbol=req.symbol, action=req.action, quantity=qty, price=price,
                allocation_usd=exec_alloc, source="tradingview",
                tp_price=req.tp_price, sl_price=trade.get("sl_price"),
            ))
        return {"ok": True, "action": req.action, "symbol": req.symbol, "qty": qty, "price": price}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Pending order (2-second undo window) ──────────────────────────────────────

class PendingOrderRequest(BaseModel):
    user_id:    Optional[str] = None
    action:     str
    symbol:     str
    size_usd:   float = Field(default=0.0, ge=0.0, le=100_000.0)
    tp_price:   Optional[float] = None
    sl_price:   Optional[float] = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v.lower() not in _VALID_SIGNAL_ACTIONS:
            raise ValueError("action must be buy | sell | close")
        return v.lower()

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        clean = v.strip().upper()
        if not _SYMBOL_RE.match(clean):
            raise ValueError("symbol must be 1-20 uppercase alphanumeric characters / - _")
        return clean


@app.post("/api/agent/pending-order")
async def create_pending_order(request: Request, req: PendingOrderRequest):
    """Stage a trade for 2 seconds. Client can DELETE /api/agent/pending-order/{id}
    within the window to cancel. After 2 s the order executes automatically."""
    import uuid as _uuid

    order_id = str(_uuid.uuid4())
    user_id = await _resolve_request_user_id(request, req.user_id)
    if req.user_id and not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    async def _execute_after_delay():
        await asyncio.sleep(2.0)
        if order_id not in _pending_orders:
            return
        try:
            s = get_state(user_id) if user_id else _state
            if s.venue is None or s.risk_mgr is None:
                return
            equity  = s.account.get("equity", 0.0)
            balance = s.account.get("balance", 0.0)
            trade   = {
                "action": req.action, "asset": req.symbol,
                "allocation_usd": req.size_usd,
                "current_price":  s.price_cache.get(req.symbol.replace("/", ""), 0),
                "sl_price": req.sl_price, "tp_price": req.tp_price,
            }
            ok, reason, trade = s.risk_mgr.validate_trade(
                trade, {"total_value": equity, "balance": balance, "positions": s.positions},
                s.initial_equity or 0,
            )
            if not ok:
                s.log(f"[PENDING] RISK BLOCKED {req.symbol}: {reason}")
                return
            price = trade["current_price"]
            if price <= 0:
                return
            qty, _exec_alloc = _resolve_execution_quantity(s, req.action, req.symbol, req.size_usd, price)
            if qty <= 0:
                return
            if req.action in ("buy", "sell"):
                await s.venue.place_order(
                    symbol=req.symbol, side=req.action,
                    quantity=qty, order_type="market",
                    stop_loss=trade.get("sl_price"), take_profit=trade.get("tp_price"),
                )
            else:
                await s.venue.close_position(req.symbol)
            s.log(f"[PENDING EXECUTED] {req.action.upper()} {req.symbol}")
            await _broadcast({"type": "trade_executed", "data": {
                "symbol": req.symbol, "action": req.action,
                "price": price, "qty": qty, "source": "pending",
            }}, user_id)
        except Exception as e:
            logger.error("Pending order execution failed: %s", e)
        finally:
            _pending_orders.pop(order_id, None)

    task = asyncio.create_task(_execute_after_delay())
    _pending_orders[order_id] = {"task": task, "symbol": req.symbol, "action": req.action, "user_id": user_id}
    return {"ok": True, "order_id": order_id, "cancel_within_seconds": 2}


@app.delete("/api/agent/pending-order/{order_id}")
async def cancel_pending_order(request: Request, order_id: str, userId: Optional[str] = None):
    """Cancel a pending order before it executes (within 2-second window)."""
    entry = _pending_orders.pop(order_id, None)
    if not entry:
        return {"ok": False, "error": "Order not found or already executed"}
    owner_user_id = entry.get("user_id")
    if owner_user_id:
        requester_user_id = await _require_request_user_id(request, userId)
        if requester_user_id != owner_user_id:
            _pending_orders[order_id] = entry
            raise HTTPException(status_code=404, detail="Order not found or already executed")
    entry["task"].cancel()
    return {"ok": True, "cancelled": order_id}


class KillSwitchRequest(BaseModel):
    confirm: bool = False
    ts: float = 0.0        # unix timestamp from client — must be within 10 seconds
    userId: Optional[str] = None


@app.post("/api/agent/killswitch")
async def kill_switch(request: Request, req: KillSwitchRequest):
    """Emergency: close ALL open positions immediately and stop the agent.

    C6: Requires explicit confirmation to prevent accidental activation.
    Client must send { confirm: true, ts: Date.now()/1000 } within 10 seconds.
    """
    import time as _time_mod
    if not req.confirm:
        return {"ok": False, "error": "Send { confirm: true, ts: <unix_seconds> } to activate kill switch."}
    if req.ts and abs(_time_mod.time() - req.ts) > 10:
        return {"ok": False, "error": "Kill switch timestamp expired (>10s). Re-confirm from the UI."}

    user_id = await _resolve_request_user_id(request, req.userId)
    if req.userId and not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    s = get_state(user_id) if user_id else _state
    closed = []
    errors = []

    if s.venue and s.positions and not s.is_paper:
        for pos in list(s.positions):
            sym = pos.get("symbol", "")
            qty = abs(float(pos.get("quantity", 0)))
            if qty > 0:
                try:
                    await s.venue.close_position(sym, qty)
                    closed.append(sym)
                except Exception as e:
                    errors.append(f"{sym}: {e}")

    s.status = "stopped"
    if s._loop_task:
        s._loop_task.cancel()
    await _broadcast({"type": "status_update", "status": "stopped", "reason": "kill_switch"}, s.user_id)
    await _notifier.emit(TradingEvent(
        kind="circuit_breaker_tripped", venue=s.venue_name,
        message=f"Kill switch activated. Closed: {closed}. Errors: {errors}",
    ))
    if s.user_id:
        try:
            from src.services.supabase_reader import upsert_agent_run
            await upsert_agent_run(
                s.user_id, s.venue_name, s.symbols, s.timeframe,
                s.is_paper, s.market, False,
            )
        except Exception:
            pass
        asyncio.create_task(_persist_audit(
            s.user_id, "kill_switch", None, None,
            {"venue": s.venue_name, "closed": closed, "errors": errors},
        ))
        asyncio.create_task(capture_posthog("kill_switch_triggered", {
            "user_id": s.user_id,
            "plan": await _get_user_plan(s.user_id),
            "mode": "paper" if s.is_paper else "live",
            "venue": s.venue_name,
            "persona": s.strategy_type or "",
            "provider": s.ai_agent.provider.name if s.ai_agent else "",
            "trace_id": new_trace_id(),
            "success": True,
            "reason_code": "kill_switch",
        }))
    return {"ok": True, "closed": closed, "errors": errors}


# ── WebSocket (JWT-gated) ─────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: Optional[str] = Query(default=None)):
    ws_token, accepted_protocol = _resolve_ws_auth(ws, token)
    allowed, ws_user_id = await _verify_ws_token(ws_token)
    if not allowed:
        await ws.close(code=4001)
        return

    await ws.accept(subprotocol=accepted_protocol)
    _ws_clients.add(ws)
    _ws_user_map[ws] = ws_user_id

    # Resolve which state to send based on the user's session
    s = get_state(ws_user_id) if ws_user_id else _state
    db_decisions = await _load_session_scoped_decisions(ws_user_id, s, 20)
    await ws.send_json({
        "type":      "init",
        "status":    s.status,
        "venue":     s.venue_name,
        "assets":    s.symbols,
        "timeframe": s.timeframe,
        "market":    s.market,
        "asset_class": _infer_asset_class(s.venue_name, s.market),
        "strategy_type": s.strategy_type or None,
        "account":   s.account,
        "positions": s.positions,
        "decisions": db_decisions,
        "prices":    s.price_cache,
        "paper":     s.is_paper,
    })
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=12)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat", "ts": int(time.time())})
                continue
            # Respond to client ping to keep the connection alive through proxies
            try:
                data = json.loads(msg)
                if data.get("type") == "ping":
                    await ws.send_json({"type": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)
        _ws_user_map.pop(ws, None)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "8000"))
    logger.info("Starting QuantatraderAI API server on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
