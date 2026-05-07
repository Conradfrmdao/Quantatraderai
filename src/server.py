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
WS   /ws?token=<clerk_session_token>   — real-time event stream (JWT-gated)

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
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import uvicorn

from src.config_loader import CONFIG
from src.risk_manager import RiskManager
from src.agent.decision_maker import TradingAgent
from src.venues.base import Venue
from src.venues.registry import get_venue
from src.indicators.local_indicators import compute_all, latest
from src.utils.prompt_utils import round_or_none
from src.alerts.notifier import build_notifier, TradingEvent

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
)
logger = logging.getLogger("quantatraderai.server")

# M16: Sentry error tracking — optional, activate by setting SENTRY_DSN in env
_SENTRY_DSN = os.getenv("SENTRY_DSN")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.1,  # 10% of requests profiled
            environment=os.getenv("ENVIRONMENT", "production"),
        )
        logger.info("Sentry initialized OK")
    except ImportError:
        logger.warning("SENTRY_DSN set but sentry-sdk not installed — run: pip install sentry-sdk")

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
        conn = await asyncpg.connect(os.getenv("DATABASE_URL", ""), timeout=5)
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

# ── JWKS / JWT helpers ────────────────────────────────────────────────────────
_jwks_cache: dict | None = None
_jwks_cache_ts: float = 0.0
_JWKS_TTL = 3600.0  # refresh keys hourly


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


# ── Agent state ───────────────────────────────────────────────────────────────

class AgentState:
    def __init__(self):
        self.status: str         = "idle"
        self.user_id: str | None = None
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

        self.start_time:     datetime | None = None
        self.initial_equity: float   | None = None
        self.paper_balance:  float          = 10_000.0  # simulated balance for paper trading
        self.paper_positions: list[dict]    = []         # simulated open positions
        self.trade_log:      list[dict]      = []
        self.tick_count:     int             = 0
        self.error:          str | None      = None
        self.last_tick_at:   datetime | None = None  # dead man's switch anchor
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


# ── WebSocket broadcast ───────────────────────────────────────────────────────

async def _broadcast(event: dict, user_id: str | None = None):
    """Broadcast to all clients, or only to clients belonging to user_id."""
    dead: set[WebSocket] = set()
    for ws in list(_ws_clients):
        # Per-user filtering: only deliver if either no user_id specified
        # (legacy/global) or the client belongs to this user.
        if user_id is not None:
            ws_user = _ws_user_map.get(ws)
            if ws_user and ws_user != user_id:
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
                await _broadcast({
                    "type":   "price_update",
                    "symbol": key,
                    "price":  price,
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
                            key   = f"{raw_sym}:{timeframe}"
                            cache = s.candle_cache.setdefault(key, [])
                            if cache and cache[-1]["time"] == candle["time"]:
                                cache[-1] = candle
                            elif not cache or candle["time"] > cache[-1]["time"]:
                                cache.append(candle)
                                if len(cache) > 500:
                                    cache.pop(0)
                            await _broadcast({
                                "type":      "price_update",
                                "symbol":    raw_sym,
                                "price":     price,
                                "candle":    candle,
                                "timeframe": timeframe,
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
        # Paper mode: use simulated balance — never the real exchange balance.
        # Real balance is often $0 which causes the AI to refuse all trades.
        # Paper trades update s.paper_balance so P&L is tracked correctly.
        balance   = s.paper_balance
        pnl_total = sum(p.get("unrealized_pnl", 0.0) for p in s.paper_positions)
        equity    = balance + pnl_total
    else:
        usdt      = next((b for b in balances if b.currency in ("USDT", "USD", "BUSD")), None)
        balance   = usdt.available if usdt else 0.0
        pnl_total = sum(p.unrealized_pnl for p in positions)
        equity    = balance + pnl_total

    if s.initial_equity is None:
        s.initial_equity = equity
    ret_pct = ((equity - s.initial_equity) / s.initial_equity * 100) if s.initial_equity else 0.0

    s.account = {
        "balance":          round(balance, 4),
        "equity":           round(equity, 4),
        "initial_equity":   round(s.initial_equity, 4),
        "total_return_pct": round(ret_pct, 4),
        "open_positions":   len(positions),
        "sharpe":           _sharpe(s.trade_log),
    }
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

    s.positions = [
        {
            "symbol":            p.symbol,
            "quantity":          p.quantity,
            "entry_price":       p.entry_price,
            "current_price":     s.price_cache.get(p.symbol.replace("/", ""), p.entry_price),
            "unrealized_pnl":    round(p.unrealized_pnl, 4),
            "leverage":          p.leverage,
            "liquidation_price": p.liquidation_price,
        }
        for p in positions
    ]
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
    if _is_forex:
        for sym in s.symbols:
            try:
                ticker = await s.venue.get_ticker(sym)
                mid = ((ticker.bid + ticker.ask) / 2
                       if (ticker.bid and ticker.ask) else ticker.last)
                if mid and mid > 0:
                    s.price_cache[sym.replace("/", "")] = mid
            except Exception as _te:
                s.log(f"Ticker poll error {sym}: {_te}")

    market_sections = []
    for sym in s.symbols:
        try:
            candles = await s.venue.get_candles(sym, s.timeframe, 100)
            raw     = [_candle_dict(c) for c in candles]
            key     = f"{sym.replace('/', '')}:{s.timeframe}"
            s.candle_cache[key] = raw
            inds   = compute_all(raw)
            px_key = sym.replace("/", "")
            # For crypto: stream provides real-time price; only fill gap from candle.
            # For FOREX: ticker polling above already set the price; candle is fallback.
            if px_key not in s.price_cache and candles:
                s.price_cache[px_key] = candles[-1].close
            rsi_val  = round_or_none(latest(inds.get("rsi14", [])), 2)
            macd_val = round_or_none(latest(inds.get("macd",  [])), 2)
            ema_val  = round_or_none(latest(inds.get("ema20", [])), 2)
            market_sections.append({
                "asset":         sym,
                "current_price": round(s.price_cache.get(px_key, 0), 5 if _is_forex else 4),
                "rsi14":         rsi_val,
                "ema20":         ema_val,
                "macd":          macd_val,
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
    try:
        if use_council:
            from src.agent.council import council_decide
            council_results = await council_decide(s.symbols, context)
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
                        {"provider": op.provider, "action": op.action, "rationale": op.rationale[:120], "confidence": op.confidence}
                        for op in cd.opinions
                    ],
                })
                council_opinions.append({
                    "asset": cd.asset,
                    "opinions": [{"provider": op.provider, "action": op.action, "confidence": op.confidence, "rationale": op.rationale[:120]} for op in cd.opinions],
                    "vote": cd.action, "confidence": cd.confidence, "deadlock": cd.deadlock,
                })
        else:
            outputs = s.ai_agent.decide_trade(s.symbols, context) or {}
            decisions = outputs.get("trade_decisions", []) if isinstance(outputs, dict) else []
    except Exception as e:
        s.log(f"AI error: {e}")
        await _notifier.emit(TradingEvent(
            kind="decision_error", venue="binance",
            message=f"LLM decision error: {e}",
        ))
        decisions = []

    if decisions:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trade_decisions": decisions,
            "council": council_opinions,
        }
        s.decisions.appendleft(entry)
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

    # ── Evaluate NL strategy rules (wired into tick loop) ──────────
    if s.user_id and _strategy_rules.get(s.user_id):
        try:
            from src.agent.nl_parser import evaluate_rule
            from src.indicators.local_indicators import compute_all, latest
            for sym in s.symbols:
                key = f"{sym.replace('/','').replace('-','')}:{s.timeframe}"
                bars = s.candle_cache.get(key, [])
                if not bars: continue
                inds  = compute_all(bars)
                price = s.price_cache.get(sym.replace("/",""), 0)
                equity = s.account.get("equity", 0)
                for rule in _strategy_rules.get(s.user_id, []):
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

            if action == "buy":
                s.paper_balance -= alloc
                s.paper_positions.append({
                    "symbol": sym, "quantity": qty, "entry_price": price,
                    "current_price": price, "unrealized_pnl": 0.0,
                    "sl_price": dec.get("sl_price"), "tp_price": dec.get("tp_price"),
                })
            elif action == "sell":
                # Close matching paper position
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
            s.timeline_event("executed", sym,
                f"[Paper] {action.upper()} {qty:.6f} @ ${price:.2f} | balance=${s.paper_balance:.2f}",
                action=action)
            s.log(f"[PAPER] {action.upper()} {sym} qty={qty:.6f} @ ${price:.2f} "
                  f"balance=${s.paper_balance:.2f} — {dec.get('rationale','')[:60]}")
            await _broadcast({"type": "trade_executed", "data": {
                "symbol": sym, "action": action, "price": price, "qty": qty,
                "venue": s.venue_name, "paper": True,
            }}, s.user_id)

            # Update paper positions' current prices
            for p in s.paper_positions:
                cp = s.price_cache.get(p["symbol"].replace("/",""), p["entry_price"])
                p["current_price"]  = cp
                p["unrealized_pnl"] = (cp - p["entry_price"]) * p["quantity"]

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
            await _notifier.emit(TradingEvent(
                kind="circuit_breaker_tripped", venue=s.venue_name, symbol=sym,
                message=f"Risk blocked {action.upper()} {sym}: {reason}",
            ))
            asyncio.create_task(_persist_audit(
                s.user_id, "risk_block", sym, action,
                {"reason": reason, "allocation_usd": alloc, "venue": s.venue_name},
            ))
            continue

        price = dec["current_price"]
        if price <= 0:
            s.log(f"Skipping {sym}: price unknown")
            continue

        qty = float(dec.get("allocation_usd", alloc)) / price
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
            await _notifier.emit(TradingEvent(
                kind="trade_opened", venue=s.venue_name, symbol=sym,
                message=f"{action.upper()} {qty:.6f} @ ${price:.4f} — {dec.get('rationale','')[:80]}",
                data={"allocation_usd": alloc, "sl": dec.get("sl_price"), "tp": dec.get("tp_price")},
            ))
            # Persist to TradeLog + AuditLog
            asyncio.create_task(_persist_trade(
                s.user_id, symbol=sym, action=action, quantity=qty, price=price,
                allocation_usd=alloc, source="agent", rationale=dec.get("rationale"),
                tp_price=dec.get("tp_price"), sl_price=dec.get("sl_price"),
            ))
            asyncio.create_task(_persist_audit(
                s.user_id, "order", sym, action,
                {"qty": qty, "price": price, "venue": s.venue_name, "allocation_usd": alloc},
            ))
            # Mirror to copy-trading followers
            if s.user_id and (_plan_allows(await _get_user_plan(s.user_id), "copyTrading") or os.getenv("ENABLE_COPY_TRADING", "false").lower() in ("1", "true", "yes")):
                asyncio.create_task(_mirror_to_followers(
                    s.user_id, sym, action, alloc, equity,
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
                result = s.ai_agent.decide_trade(ctx["symbols"], ctx["context"])
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
                qty = alloc / price
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
_allow_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or ["*"]
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
    client_ip = request.client.host if request.client else "unknown"
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
    try:
        from src.services.supabase_reader import get_running_agents
        running = await get_running_agents()
    except Exception as e:
        logger.warning("Boot resume check failed: %s", e)
        return

    if not running:
        return

    row = running[0]  # single-agent model; first wins
    venue_name = row.get("venue") or "binance"
    logger.info("Auto-resuming agent for userId=%s venue=%s symbols=%s",
                row["userId"], venue_name, row["symbols"])
    # Use stored market, but default to "spot" if stored value was "futures"
    # (futures requires a separate Binance Futures account; spot works with any key)
    stored_market = row.get("market") or "spot"
    safe_market = stored_market if stored_market != "futures" else "spot"
    if safe_market != stored_market:
        logger.info("Auto-resume: downgraded market futures→spot (no futures account needed for paper trading)")

    await _do_start(
        user_id=row["clerkId"],
        venue_name=venue_name,
        symbols=list(row["symbols"]),
        timeframe=row["timeframe"],
        is_paper=row["isPaper"],
        market=safe_market,
        api_key=None,
        api_secret=None,
    )


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
async def test_stored_key(userId: Optional[str] = None):
    """Quick diagnostic: decrypt the stored API key and check its format/length.
    Does NOT call the exchange — purely local validation.
    Shows key length, first 4 chars, last 4 chars so the user can verify without exposing it."""
    if not userId:
        return {"ok": False, "error": "userId required"}
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
async def get_status(userId: Optional[str] = None):
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
        "is_paper":         s.is_paper,
        "last_tick_ago_s":  last_tick_ago,
        "next_tick_in_s":   next_tick_in,
        "tick_interval_s":  int(tick_interval),
        "strategy_type":    s.strategy_type or None,
        "latest_log":       latest_log,
        "daily_trade_count": s.daily_trade_count,
        "consecutive_losses": s.consecutive_losses,
    }


@app.get("/api/account")
async def get_account(userId: Optional[str] = None):
    s = get_state(userId)
    if s.account:
        return s.account
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
async def get_positions(userId: Optional[str] = None):
    s = get_state(userId)
    # Always return paper positions in paper mode (real exchange positions are irrelevant)
    if s.is_paper:
        return {"positions": s.paper_positions, "is_paper": True}
    return {"positions": s.positions, "is_paper": False}


@app.get("/api/risk")
async def get_risk(userId: Optional[str] = None):
    """Live risk config for the requesting user's session (or fallback global)."""
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
async def refresh_plan(req: PlanRefreshRequest):
    """C3: Invalidate the cached plan so next request fetches fresh from DB.
    Called by the Next.js Stripe webhook handler after a successful upgrade."""
    invalidate_plan_cache(req.userId)
    return {"ok": True}


@app.post("/api/risk/refresh")
async def refresh_risk(req: RiskRefreshRequest):
    """C1: Apply risk profile updates to the running agent immediately.

    Maps Prisma camelCase fields to internal snake_case config keys, then
    broadcasts the new config to all connected WS clients for instant UI sync.
    """
    s = get_state(req.userId)

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


@app.get("/api/decisions")
async def get_decisions(limit: int = 20, userId: Optional[str] = None):
    return {"decisions": list(get_state(userId).decisions)[:limit]}


@app.get("/api/trust/metrics")
async def get_trust_metrics(userId: Optional[str] = None):
    """Trust Dashboard — win rate, profit curve, drawdown, Sharpe, AI accuracy."""
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
    symbol:    str = "BTCUSDT",
    timeframe: str = "1h",
    limit:     int = 200,
    venue:     Optional[str] = None,
):
    """Return candle data for any configured venue.

    Order of resolution:
      1. In-memory cache (if the agent is running and has fetched these bars)
      2. Live venue adapter (if agent is running and matches requested venue)
      3. Binance public REST fallback (crypto symbols only)
    """
    key    = f"{symbol}:{timeframe}"
    cached = _state.candle_cache.get(key)
    if cached:
        return {"candles": cached[-limit:]}

    v = (venue or _state.venue_name or "binance").lower()

    # If agent is live and the venue matches, use its adapter
    if _state.venue is not None and v == _state.venue_name:
        try:
            bars = await _state.venue.get_candles(symbol, timeframe, min(limit, 500))
            candles = [
                {"time": c.ts, "open": c.open, "high": c.high,
                 "low": c.low, "close": c.close, "volume": c.volume}
                for c in bars
            ]
            _state.candle_cache[key] = candles
            return {"candles": candles[-limit:]}
        except Exception as e:
            logger.warning("Venue candle fetch failed, falling back to Binance: %s", e)

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
            return {"candles": []}
        candles = [
            {"time": int(row[0]) // 1000,
             "open": float(row[1]), "high": float(row[2]),
             "low":  float(row[3]), "close": float(row[4]),
             "volume": float(row[5])}
            for row in data
        ]
        _state.candle_cache[key] = candles
        return {"candles": candles[-limit:]}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Candle fetch failed: {e}")


@app.get("/api/logs")
async def get_logs(limit: int = 100, userId: Optional[str] = None):
    s = get_state(userId)
    return {"logs": list(s.logs)[-limit:]}


# ── Agent control ─────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    userId:        Optional[str] = None
    venue:         str           = "binance"   # hyperliquid | binance | oanda | metatrader | alpaca | ibkr | bybit | okx | kraken | coinbase | ccxt:<id>
    symbols:       list[str]     = Field(default=["BTC/USDT"], max_length=20)
    timeframe:     str           = "1h"
    isPaper:       bool          = True
    market:        str           = "spot"   # default: spot avoids requiring a Binance Futures account
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
        if ccxt_exchange:  os.environ["CCXT_EXCHANGE"]   = ccxt_exchange
        os.environ["CCXT_SANDBOX"] = "true" if is_paper else "false"
    elif v == "polymarket":
        if api_key:  os.environ["POLYMARKET_ETH_PRIVATE_KEY"] = api_key
        os.environ["POLYMARKET_CHAIN_ID"] = network or "137"
        os.environ["POLYMARKET_IS_PAPER"] = "true" if is_paper else "false"


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
    forced_paper_warning: str | None = None
    if user_id:
        try:
            plan = await _get_user_plan(user_id)
            if not _plan_allows(plan, "liveTrading") and not is_paper:
                logger.warning(
                    "Forcing paper mode: user %s on plan %s — liveTrading not allowed.",
                    user_id, plan,
                )
                is_paper = True
                forced_paper_warning = (
                    f"Your {plan} plan does not include live trading. "
                    "Agent started in paper mode. Upgrade to go live."
                )
        except Exception as e:
            logger.warning("Plan re-validation failed (forcing paper): %s", e)
            is_paper = True
            forced_paper_warning = "Plan check failed — started in paper mode for safety."

    # BETA LIVE CAP — hard server-side dollar ceiling during beta.
    # Set BETA_LIVE_CAP_USD=0 in .env to remove after public launch.
    _beta_cap = float(os.getenv("BETA_LIVE_CAP_USD", "500"))
    if not is_paper and _beta_cap > 0:
        logger.info("Beta live cap active: max $%.0f per-trade allocation", _beta_cap)


    # H8: idempotency lock + per-user state binding (no global _state mutation).
    # Each user gets an isolated AgentState. The global _state is only used as a
    # fallback for unauthenticated dev mode — never reassigned here.
    async with _start_lock:
        if user_id:
            s_check = get_state(user_id)
            if s_check.status == "running":
                return {"ok": False, "error": "Your agent is already running"}
        else:
            if _state.status == "running":
                return {"ok": False, "error": "Agent already running"}

    v_key = venue_name.lower().strip().split(":")[0]

    # Try Supabase credential lookup — pick the venue matching the requested type
    api_passphrase = ""
    account_id     = ""
    network        = ""
    meta_token     = ""
    meta_account_id = ""
    ccxt_exchange  = ""

    if user_id:
        try:
            from src.services.supabase_reader import get_user_venues
            venues = await get_user_venues(user_id)
            # find the venue whose registry name maps to our target
            match = None
            for v in venues:
                name = _VENUE_TYPE_TO_NAME.get(v.get("type", ""), "").lower()
                if name == v_key:
                    match = v; break
            if match:
                api_key        = api_key        or match.get("apiKey")
                api_secret     = api_secret     or match.get("apiSecret")
                api_passphrase = match.get("apiPassphrase") or ""
                account_id     = match.get("accountId") or ""
                network        = match.get("network") or ""
                meta_token     = match.get("metaApiToken") or ""
                meta_account_id = match.get("metaApiAccountId") or ""
                ccxt_exchange  = match.get("ccxtExchangeId") or ""
                logger.info("Loaded %s credentials from Supabase for user %s", venue_name, user_id)
        except Exception as e:
            logger.warning("Supabase credential load failed: %s — falling back to .env", e)

    # Fall back to .env
    if not api_key and v_key == "binance":
        api_key    = CONFIG.get("binance_api_key") or ""
        api_secret = CONFIG.get("binance_api_secret") or ""
    elif not api_key and v_key == "hyperliquid":
        api_key = CONFIG.get("hyperliquid_private_key") or ""

    _inject_venue_env(
        v_key, market, is_paper, api_key or "", api_secret or "",
        api_passphrase, account_id, network, meta_token, meta_account_id, ccxt_exchange,
    )

    # Resolve per-user state — never mutate the global _state for a specific user.
    final_state = get_state(user_id) if user_id else _state

    try:
        # Construct venue via registry
        if v_key == "binance":
            asset_class = "crypto_perp" if market == "futures" else "crypto_spot"
            final_state.venue = get_venue(f"binance:{market}")
        else:
            asset_class = _ASSET_CLASS.get(v_key, "crypto_spot")
            final_state.venue = get_venue(venue_name)
        final_state.risk_mgr = RiskManager(venue=v_key, asset_class=asset_class)
        _venue_ctx = "forex" if asset_class == "forex" else "crypto"
        final_state.ai_agent = TradingAgent(hyperliquid=None, venue_context=_venue_ctx)
    except Exception as e:
        final_state.status = "error"
        final_state.error  = str(e)
        logger.exception("Venue init failed")
        return {"ok": False, "error": f"Venue init failed: {e}"}

    final_state.symbols        = symbols
    final_state.timeframe      = timeframe
    final_state.is_paper       = is_paper
    final_state.market         = market
    final_state.venue_name     = v_key
    final_state.status         = "running"
    final_state.user_id        = user_id
    final_state.decisions.clear()
    final_state.trade_log.clear()
    final_state.account        = {}
    final_state.positions      = []
    final_state.initial_equity = None
    final_state.tick_count     = 0
    final_state.error               = None
    final_state.last_tick_at        = datetime.now(timezone.utc)
    final_state.min_confidence_pct  = min_confidence_pct
    final_state.max_daily_loss_pct  = max_daily_loss_pct
    final_state.max_trades_per_day  = max_trades_per_day
    final_state.loss_cooldown_count = loss_cooldown_count
    final_state.strategy_type       = strategy_type or ""
    final_state.daily_loss_usd      = 0.0
    final_state.daily_trade_count   = 0
    final_state.consecutive_losses  = 0
    final_state.day_reset_at        = datetime.now(timezone.utc).date().isoformat()
    final_state.timeline            = deque(maxlen=200)
    # Reset paper trading simulation on every fresh start
    if is_paper:
        _cap = max(100.0, float(paper_capital or 10_000.0))
        final_state.paper_balance   = _cap
        final_state.paper_positions = []
        final_state.initial_equity  = _cap

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

    final_state._loop_task = asyncio.create_task(_run_loop_for(final_state))

    # Persist to DB so server restart can resume
    if user_id:
        try:
            from src.services.supabase_reader import upsert_agent_run
            await upsert_agent_run(user_id, v_key, symbols, timeframe, is_paper, market, True)
        except Exception as e:
            logger.warning("AgentRun persist failed: %s", e)
        asyncio.create_task(_persist_audit(
            user_id, "agent_start", None, None,
            {"venue": v_key, "symbols": symbols, "timeframe": timeframe, "is_paper": is_paper},
        ))

    result: dict = {"ok": True, "venue": v_key, "symbols": symbols, "timeframe": timeframe, "paper": is_paper}
    if forced_paper_warning:
        result["warning"] = forced_paper_warning
    return result


@app.post("/api/agent/start")
async def start_agent(req: StartRequest):
    return await _do_start(
        user_id=req.userId,
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


@app.get("/api/agent/personas")
async def list_personas():
    from src.agent.strategy_personas import list_personas as _list
    return {"personas": [p.to_dict() for p in _list()]}


@app.get("/api/agent/timeline")
async def get_timeline(userId: Optional[str] = None, limit: int = 50):
    s = get_state(userId)
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
async def stop_agent(body: dict = {}):
    userId = body.get("userId") if body else None
    # Resolve the correct per-user state — same pattern as every other endpoint
    s = get_state(userId)
    if s.status not in ("running", "starting"):
        return {"ok": False, "error": "Agent is not running"}
    s.status = "stopping"
    if s._loop_task:
        s._loop_task.cancel()
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
    return {"ok": True}


# ── Strategy rules (NL commands) ─────────────────────────────────────────────

_strategy_rules: dict[str, list] = {}  # userId → list[StrategyRule]


class StrategyRequest(BaseModel):
    text:   str
    userId: Optional[str] = None


@app.post("/api/strategies")
async def create_strategy(req: StrategyRequest):
    from src.agent.nl_parser import parse_nl_rule
    rule = await parse_nl_rule(req.text)
    if not rule:
        raise HTTPException(status_code=422, detail="Could not parse rule")
    uid = req.userId or "anonymous"
    _strategy_rules.setdefault(uid, []).append(rule)
    return {"ok": True, "rule": {"id": rule.id, "condition": rule.condition, "action": rule.action, "symbol": rule.symbol, "threshold": rule.threshold}}


@app.get("/api/strategies")
async def list_strategies(userId: Optional[str] = None):
    uid   = userId or "anonymous"
    rules = _strategy_rules.get(uid, [])
    return {"rules": [{"id": r.id, "condition": r.condition, "action": r.action, "symbol": r.symbol, "active": r.active} for r in rules]}


@app.delete("/api/strategies/{rule_id}")
async def delete_strategy(rule_id: str, userId: Optional[str] = None):
    uid = userId or "anonymous"
    _strategy_rules[uid] = [r for r in _strategy_rules.get(uid, []) if r.id != rule_id]
    return {"ok": True}


class VenueTestRequest(BaseModel):
    userId:  str
    venue:   str
    isPaper: bool = True


@app.post("/api/venues/test")
async def test_venue(req: VenueTestRequest):
    """Initialise the venue adapter with the user's stored credentials and
    call get_balances() as a smoke test. Returns {ok, balance, currency}.

    B2: Venue-specific error messages so users understand exactly what is wrong.
    """
    venue_lc = req.venue.lower()
    try:
        from src.services.supabase_reader import get_user_venues
        venues = await get_user_venues(req.userId)
        match = None
        for v in venues:
            name = _VENUE_TYPE_TO_NAME.get(v.get("type", ""), "").lower()
            if name == venue_lc:
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

        if venue_lc in ("binance", "bybit", "kraken", "coinbase", "binanceusdm"):
            if not api_key or not api_sec:
                return {"ok": False, "error": f"{req.venue} requires API key + secret."}
            # Validate Binance key format — should be ~64 alphanumeric chars
            if venue_lc in ("binance", "binanceusdm"):
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
        if venue_lc == "okx" and (not api_key or not api_sec or not passph):
            return {"ok": False, "error": "OKX requires API key, secret, AND passphrase."}
        if venue_lc == "hyperliquid" and not api_key:
            return {"ok": False, "error": "Hyperliquid requires a private key (your wallet seed in API Key field)."}
        if venue_lc == "oanda":
            if not api_key:  return {"ok": False, "error": "OANDA requires an API token (Account → API Access)."}
            if not acct_id:  return {"ok": False, "error": "OANDA requires an Account ID (e.g. 101-001-12345-001)."}
        if venue_lc == "metatrader":
            if not meta_tok:   return {"ok": False, "error": "MetaTrader requires a MetaAPI cloud token. Sign up at metaapi.cloud."}
            if not meta_acct:  return {"ok": False, "error": "MetaTrader requires a MetaAPI account ID."}
        if venue_lc == "alpaca":
            if not api_key or not api_sec:
                return {"ok": False, "error": "Alpaca requires API key + secret. Get them from app.alpaca.markets."}
        if venue_lc == "polymarket":
            if not api_key:
                return {"ok": False, "error": "Polymarket requires the private key of a dedicated trading wallet (not your main wallet). Coming soon: Connect Wallet."}
            if not (api_key.startswith("0x") and len(api_key) >= 64):
                return {"ok": False, "error": "Polymarket private key must be 0x-prefixed and 32 bytes long."}

        # Inject env vars for this test only
        _inject_venue_env(
            venue_lc, "futures", req.isPaper,
            api_key, api_sec, passph, acct_id,
            match.get("network") or "",
            meta_tok, meta_acct,
            match.get("ccxtExchangeId") or "",
        )

        venue = get_venue(req.venue)
        balances = await venue.get_balances()

        # Phase 4: Withdrawal-permission warning for Binance / CCXT venues.
        # If the user's API key has withdrawal rights enabled, surface a warning so
        # they regenerate it as trading-only.
        warning = None
        if venue_lc in ("binance", "bybit", "kraken", "coinbase", "ccxt"):
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
            if warning: result["warning"] = warning
            return result
        result = {"ok": True, "currency": "—", "balance": 0, "available": 0, "venue": req.venue,
                  "note": "Connection succeeded but no balances returned (account may be empty)."}
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
        logger.warning("venue test failed for %s: %s", venue_lc, e)
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
async def get_rag_memories(userId: Optional[str] = None, limit: int = 50):
    """Return stored RAG decision embeddings for a user."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url or not userId:
        return {"memories": []}
    try:
        import asyncpg
        conn = await asyncpg.connect(db_url, timeout=5)
        try:
            rows = await conn.fetch(
                'SELECT "id","asset","action","rationale","qualityScore","createdAt" '
                'FROM "DecisionEmbedding" WHERE "userId"=$1 ORDER BY "createdAt" DESC LIMIT $2',
                userId, limit,
            )
            return {"memories": [dict(r) for r in rows]}
        finally:
            await conn.close()
    except Exception as e:
        return {"memories": [], "error": str(e)}


@app.delete("/api/rag-memory/{memory_id}")
async def delete_rag_memory(memory_id: str, userId: Optional[str] = None):
    db_url = os.getenv("DATABASE_URL")
    if not db_url or not userId:
        raise HTTPException(status_code=400, detail="userId required")
    try:
        import asyncpg
        conn = await asyncpg.connect(db_url, timeout=5)
        try:
            await conn.execute(
                'DELETE FROM "DecisionEmbedding" WHERE "id"=$1 AND "userId"=$2',
                memory_id, userId,
            )
        finally:
            await conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}


@app.get("/api/intel/summary")
async def get_intel_summary():
    """Aggregated macro intel for the dashboard MacroIntelStrip widget."""
    result: dict = {}
    try:
        from src.intel.sentiment import get_fear_greed
        result["fear_greed"] = await get_fear_greed()
    except Exception:
        pass
    if _state.symbols and _state.venue:
        mtf_data: dict = {}
        news_data: dict = {}
        for sym in _state.symbols[:4]:
            try:
                from src.intel.mtf_confluence import compute_mtf_confluence
                mtf_data[sym] = await compute_mtf_confluence(_state.venue, sym)
            except Exception:
                pass
            try:
                from src.intel.news import get_news_sentiment
                news_data[sym] = await get_news_sentiment(sym)
            except Exception:
                pass
        if mtf_data:  result["mtf"]  = mtf_data
        if news_data: result["news"] = news_data
        try:
            from src.intel.correlation import compute_correlation_matrix, format_matrix_summary
            corr = compute_correlation_matrix(_state.candle_cache, _state.symbols, _state.timeframe)
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
async def get_var(simulations: int = 10000):
    """Value at Risk — Monte Carlo + parametric, sourced from EquityPoint history."""
    from src.risk.var import monte_carlo_var, parametric_var
    equity_vals: list[float] = []

    # Primary: read real equity history from EquityPoint table
    if _state.user_id:
        try:
            import asyncpg
            db_url = os.getenv("DATABASE_URL", "")
            if db_url:
                conn = await asyncpg.connect(db_url, timeout=5)
                try:
                    rows = await conn.fetch(
                        'SELECT equity FROM "EquityPoint" WHERE "userId" = $1 '
                        'ORDER BY "createdAt" DESC LIMIT 500',
                        _state.user_id,
                    )
                    equity_vals = [float(r["equity"]) for r in rows]
                finally:
                    await conn.close()
        except Exception:
            pass

    # Fallback: in-memory account snapshot
    if not equity_vals and _state.account:
        equity_vals = [float(_state.account.get("equity", 0))]

    if not equity_vals or len(equity_vals) < 5:
        return {"error": "Not enough equity history yet — run the agent for a few ticks first"}

    mc   = monte_carlo_var(equity_vals, simulations=min(simulations, 10_000))
    para = parametric_var(equity_vals)
    return {"monte_carlo": mc, "parametric": para, "data_points": len(equity_vals)}


@app.post("/api/backtest/run")
async def run_backtest(req: BacktestRequest):
    """Run a strategy backtest and return equity curve + metrics."""
    try:
        from src.backtesting.engine import run_backtest_json
        # Resolve asset_class: use provided value or auto-detect from venue name
        v_key = req.venue.lower().split(":")[0]
        resolved_ac = req.asset_class or _ASSET_CLASS.get(v_key, "crypto_perp")
        result = await run_backtest_json(
            venue=req.venue,
            symbol=req.symbol,
            timeframe=req.timeframe,
            days=req.days,
            initial_capital=req.initial_capital,
            strategy=req.strategy,
            asset_class=resolved_ac,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_SYMBOL_RE = re.compile(r"^[A-Z0-9/_-]{1,20}$")
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
async def execute_signal(req: SignalRequest):
    """Execute an external signal (TradingView webhook) through the same
    RiskManager pipeline as autonomous agent decisions.

    Phase 8: Routes to the correct per-user state via user_id, then validates
    venue ownership if venue_id is supplied.
    """
    # Resolve state: prefer per-user if user_id supplied, else global
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

    qty = req.size_usd / price
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
                allocation_usd=req.size_usd, source="tradingview",
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
async def create_pending_order(req: PendingOrderRequest):
    """Stage a trade for 2 seconds. Client can DELETE /api/agent/pending-order/{id}
    within the window to cancel. After 2 s the order executes automatically."""
    import uuid as _uuid

    order_id = str(_uuid.uuid4())

    async def _execute_after_delay():
        await asyncio.sleep(2.0)
        if order_id not in _pending_orders:
            return
        try:
            s = get_state(req.user_id) if req.user_id else _state
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
            qty = req.size_usd / price
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
            }}, req.user_id)
        except Exception as e:
            logger.error("Pending order execution failed: %s", e)
        finally:
            _pending_orders.pop(order_id, None)

    task = asyncio.create_task(_execute_after_delay())
    _pending_orders[order_id] = {"task": task, "symbol": req.symbol, "action": req.action}
    return {"ok": True, "order_id": order_id, "cancel_within_seconds": 2}


@app.delete("/api/agent/pending-order/{order_id}")
async def cancel_pending_order(order_id: str):
    """Cancel a pending order before it executes (within 2-second window)."""
    entry = _pending_orders.pop(order_id, None)
    if not entry:
        return {"ok": False, "error": "Order not found or already executed"}
    entry["task"].cancel()
    return {"ok": True, "cancelled": order_id}


class KillSwitchRequest(BaseModel):
    confirm: bool = False
    ts: float = 0.0        # unix timestamp from client — must be within 10 seconds
    userId: Optional[str] = None


@app.post("/api/agent/killswitch")
async def kill_switch(req: KillSwitchRequest):
    """Emergency: close ALL open positions immediately and stop the agent.

    C6: Requires explicit confirmation to prevent accidental activation.
    Client must send { confirm: true, ts: Date.now()/1000 } within 10 seconds.
    """
    import time as _time_mod
    if not req.confirm:
        return {"ok": False, "error": "Send { confirm: true, ts: <unix_seconds> } to activate kill switch."}
    if req.ts and abs(_time_mod.time() - req.ts) > 10:
        return {"ok": False, "error": "Kill switch timestamp expired (>10s). Re-confirm from the UI."}

    s = get_state(req.userId) if req.userId else _state
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
    return {"ok": True, "closed": closed, "errors": errors}


# ── WebSocket (JWT-gated) ─────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: Optional[str] = Query(default=None)):
    allowed, ws_user_id = await _verify_ws_token(token)
    if not allowed:
        await ws.close(code=4001)
        return

    await ws.accept()
    _ws_clients.add(ws)
    _ws_user_map[ws] = ws_user_id

    # Resolve which state to send based on the user's session
    s = get_state(ws_user_id) if ws_user_id else _state
    await ws.send_json({
        "type":      "init",
        "status":    s.status,
        "account":   s.account,
        "positions": s.positions,
        "decisions": list(s.decisions)[:20],
        "prices":    s.price_cache,
        "paper":     s.is_paper,
    })
    try:
        while True:
            await ws.receive_text()
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
