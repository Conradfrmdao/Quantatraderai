# QuntaTradeAI — State of the System & Road to World-Class

> A single durable reference that fuses what's actually in the repo today with the strategic framing from `qunta_godmode_warroom.html`.
> **17 features complete · 4 critical gaps · 31 world-class additions · 14 new venues to add**

---

## 1. Executive Summary

**QuntaTradeAI** is a Claude/Groq-powered, multi-venue autonomous AI trading agent with a production-grade Next.js dashboard. The Python backend runs an OODA-style tick loop that fetches market data, computes local technical indicators, asks an LLM for buy/sell/hold decisions, enforces hard-coded risk rules, and executes trades through pluggable venue adapters. The frontend gives users Clerk-authenticated onboarding, encrypted credential storage (AES-256-GCM), live dashboards (WebSocket + polling), and per-venue risk configuration.

The architecture is **sound and modular** — adding a new exchange is an interface implementation, not a rewrite. The gap between today and world-class is not foundational; it's finishing the last mile on alerts/persistence, unlocking MetaTrader + IBKR, turning on multi-LLM consensus with RAG memory, and wiring Stripe/mobile/observability for scale.

---

## 2. System Architecture — The Big Picture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          BROWSER (React 19)                          │
│  Next.js 16 App Router · Clerk · Tailwind v4 · Framer Motion         │
│  TradingChart (lightweight-charts) · EquityChart (recharts)          │
└────────────────────────┬─────────────────────────────────────────────┘
                         │ HTTPS + WS
┌────────────────────────▼─────────────────────────────────────────────┐
│              NEXT.JS API ROUTES  (ui/app/api/*)                      │
│  /venues (CRUD, AES-GCM encrypt)   /user/settings                    │
│  /agent/[...path]  (proxy → PYTHON_API_URL, injects userId)          │
│  /webhooks/clerk   (Svix-verified → Prisma sync)                     │
│  /health                                                             │
└────────────────────────┬─────────────────────────────────────────────┘
                         │ HTTP + WS
┌────────────────────────▼─────────────────────────────────────────────┐
│         PYTHON BACKEND  (FastAPI + aiohttp, port 8000)               │
│  src/server.py   REST + /ws  + Binance price stream                  │
│  src/main.py     aiohttp loop + diary/status endpoints               │
│                                                                      │
│    ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│    │ TradingAgent │→ │  LLM factory │→ │ Anthropic / Groq / Gemini│  │
│    │ decide_trade │  │              │  │ Ollama / OpenRouter      │  │
│    └──────┬───────┘  └──────────────┘  └──────────────────────────┘  │
│           ▼                                                          │
│    ┌──────────────┐      ┌─────────────────────────────────────────┐ │
│    │ RiskManager  │────▶ │ Venue adapter (Hyperliquid / CCXT /     │ │
│    │ validate_... │      │ Binance / OANDA)                        │ │
│    └──────┬───────┘      └──────────────────┬──────────────────────┘ │
│           ▼                                 ▼                        │
│      diary.jsonl                      Exchange APIs                  │
│      decisions.jsonl                                                 │
│      llm_requests.log                                                │
└──────────────────────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────────┐
│     POSTGRES (Supabase)  — User · Venue · RiskProfile · Settings     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Current State — Backend (Python)

### 3.1 Entry points

| File | Role |
|---|---|
| [src/main.py](src/main.py) | 754-line async trading loop. CLI: `--venue`, `--assets`, `--interval`. aiohttp endpoints: `/diary`, `/logs`, `/api/status`, `/api/account`, `/api/positions`, `/api/risk`, `/api/decisions`. |
| [src/server.py](src/server.py) | 582-line FastAPI + WebSocket server (port 8000). REST endpoints, `/ws` event stream (price/account/positions/decisions/trade/status), `POST /api/agent/start\|stop` with Supabase credential lookup, Binance kline WS for live prices. |

### 3.2 Configuration & risk

| File | Role |
|---|---|
| [src/config_loader.py](src/config_loader.py) | Centralised `CONFIG` dict. Env vars → defaults fallback. Venue selection, assets, interval, LLM provider/model, risk thresholds. |
| [src/risk_manager.py](src/risk_manager.py) | 315-line `RiskManager` — `validate_trade()`, `check_position_size()`, `check_total_exposure()`, `check_leverage()`, `check_daily_drawdown()` (circuit breaker), `check_concurrent_positions()`, `check_balance_reserve()`, `enforce_stop_loss()`, `check_losing_positions()`. **All hard-coded in Python — not LLM-trusted.** |
| `risk.yaml` | Per-(venue, asset_class) overrides. Hierarchy: yaml → env → built-in defaults. |

**Default risk limits** (conservative): `MAX_POSITION_PCT=3%`, `MAX_LEVERAGE=2x`, `MANDATORY_SL_PCT=2.5%`, `MAX_LOSS_PER_POSITION_PCT=8%`, `DAILY_LOSS_CIRCUIT_BREAKER_PCT=4%`, `MAX_TOTAL_EXPOSURE_PCT=20%`, `MAX_CONCURRENT_POSITIONS=5`, `MIN_BALANCE_RESERVE_PCT=30%`.

### 3.3 Decision engine & LLM providers

[src/agent/decision_maker.py](src/agent/decision_maker.py) — `TradingAgent.decide_trade(assets, context)`. ~450-line system prompt covering risk-adjusted returns, position awareness, exit plans, hysteresis/cooldowns, funding-rate caveats, leverage policy. Supports Claude **tool calling** (`fetch_indicator` for ema/sma/rsi/macd/bbands/atr/adx/obv/vwap/stoch_rsi) and **extended thinking**. Fallback JSON sanitizer (cheap Claude Haiku) normalises malformed outputs.

LLM provider abstraction in [src/agent/providers/](src/agent/providers/):

| Provider | File | Cost | Tool calls | Default model |
|---|---|---|---|---|
| Anthropic | `anthropic_provider.py` | paid | ✅ | `claude-sonnet-4-6` |
| Groq | `groq_provider.py` | **free** | ✅ | Llama 3.3 70B |
| Gemini | `gemini_provider.py` | **free** | ❌ | Gemini 2.0 Flash |
| Ollama | `ollama_provider.py` | free/local | ❌ | llama3.2 |
| OpenRouter | `openrouter_provider.py` | free tier | ❌ | DeepSeek-R1 |

Factory in [src/agent/providers/factory.py](src/agent/providers/factory.py) resolves `LLM_PROVIDER` env.

**Output contract:**
```json
{
  "reasoning": "long-form analysis",
  "trade_decisions": [{
    "asset": "BTC", "action": "buy|sell|hold",
    "allocation_usd": 1500, "order_type": "market|limit",
    "limit_price": null, "tp_price": 52000, "sl_price": 48000,
    "exit_plan": "close if 4h close > EMA50 or cooldown_bars:3",
    "rationale": "..."
  }]
}
```

### 3.4 Venue adapters

Abstract interface — [src/venues/base.py](src/venues/base.py):

```python
class Venue(ABC):
    async def get_balances()      -> list[Balance]
    async def get_positions()     -> list[Position]
    async def get_ticker(symbol)  -> Ticker
    async def get_candles(...)    -> list[Candle]
    async def get_symbol_info(...) -> SymbolMeta
    async def place_order(...)    -> Order
    async def cancel_order(...)   -> bool
    async def close_position(...) -> Order | None
```

Models in [src/venues/models.py](src/venues/models.py). Registry dispatcher in [src/venues/registry.py](src/venues/registry.py) handles `"hyperliquid"`, `"ccxt:<exchange>"`, `"oanda"`, `"binance:spot|futures"`.

| Adapter | File | Asset class |
|---|---|---|
| Hyperliquid | [src/venues/crypto/hyperliquid.py](src/venues/crypto/hyperliquid.py) + [src/trading/hyperliquid_api.py](src/trading/hyperliquid_api.py) (542 lines) | crypto_perp, HIP-3 DEX support |
| CCXT | [src/venues/crypto/ccxt_adapter.py](src/venues/crypto/ccxt_adapter.py) | 100+ exchanges (Binance, Bybit, Coinbase, Kraken, OKX, KuCoin…) |
| Binance native | [src/venues/crypto/binance.py](src/venues/crypto/binance.py) | spot or USDM futures |
| OANDA | [src/venues/forex/oanda.py](src/venues/forex/oanda.py) | forex (v20 REST) |

### 3.5 Indicators

[src/indicators/local_indicators.py](src/indicators/local_indicators.py) — all computed locally from OHLCV, no external TA API. `compute_all(candles) → {ema20, ema50, rsi7, rsi14, macd, macd_signal, macd_histogram, bbands_*, atr3, atr14, adx, obv, vwap, stoch_rsi, ...}`.

### 3.6 Backtesting

| File | Role |
|---|---|
| [src/backtesting/engine.py](src/backtesting/engine.py) | CLI engine. Replays historical bars through the **same** `RiskManager` + `TradingAgent` as live. Default RSI(14) smoke-test strategy. |
| [src/backtesting/mock_venue.py](src/backtesting/mock_venue.py) | In-memory `MockVenue(Venue)` — PnL mark-to-market, taker fee modelling (5 bps default), equity curve. |
| [src/backtesting/data_loader.py](src/backtesting/data_loader.py) | Fetches + disk-caches candles (`.backtest_cache/<hash>.json`). |
| [src/backtesting/report.py](src/backtesting/report.py) | Metrics: total return %, max drawdown, win rate, Sharpe. |

### 3.7 Alerts & services

- [src/alerts/notifier.py](src/alerts/notifier.py) — `Notifier` with `ConsoleBackend` + `TelegramBackend`. Event kinds: `trade_opened`, `trade_closed`, `stop_loss_hit`, `circuit_breaker_tripped`, `decision_error`, `info`. **Class exists but is never instantiated in the live loop — see §6.**
- [src/services/](src/services/) — `encryption.py` (AES-256-GCM), `supabase_reader.py` (fetch user venues from DB).

### 3.8 Logging & persistence

| File | Contents |
|---|---|
| `diary.jsonl` | Per-trade JSONL (timestamp, asset, action, allocation, entry, tp/sl, exit_plan, rationale, fill result) |
| `decisions.jsonl` | Per-cycle LLM decision summary (cycle #, reasoning, decisions, account_value, positions_count) |
| `llm_requests.log` | Model name, message count, token usage, stop reason |
| `prompts.log` | Full context payloads (debug) |

### 3.9 Tick data flow

```
1. Gather         Venue.get_balances / get_positions / get_candles / get_current_price / get_funding_rate
2. Build context  JSON: account + market + indicators + risk limits + active trades + recent fills
3. Decide         TradingAgent.decide_trade() → LLM.complete() → (tool loop) → parsed JSON
4. Risk gate      RiskManager.validate_trade() per decision → allowed / rejected / adjusted
5. Execute        Venue.place_order() + TP/SL → log to diary.jsonl
6. Reconcile      Fetch fills/positions, match vs local intent, force-close losers
7. Sleep          INTERVAL → repeat
```

---

## 4. Current State — Frontend (Next.js)

### 4.1 Stack

- **Framework:** Next.js 16.2.4 (App Router), React 19.2.4, TypeScript strict
- **Styling:** Tailwind v4, CSS variables, dark-only, glassmorphism `.card`
- **Animation:** Framer Motion 12, Aceternity spotlight, R3F + Three.js neural background
- **Charting:** `lightweight-charts` 5 (TradingView candles) + `recharts` 3 (equity curve)
- **Auth:** Clerk 7.2 (`@clerk/nextjs`) + Svix webhook verification
- **DB:** Prisma 7.7 with `@prisma/adapter-pg` (PrismaPg) → Postgres / Supabase

### 4.2 Auth flow

- [ui/middleware.ts](ui/middleware.ts) enforces Clerk auth. Public: `/`, `/sign-in`, `/sign-up`, `/terms`, `/docs`, `/api/webhooks`, `/api/health`. Private: `/(protected)/*`.
- [ui/lib/auth.ts](ui/lib/auth.ts) — `getAuthenticatedUser()` with 60-second in-memory cache to reduce DB hits.
- [ui/app/api/webhooks/clerk/route.ts](ui/app/api/webhooks/clerk/route.ts) — Svix-signed (`CLERK_WEBHOOK_SECRET`) handler: `user.created` → Prisma insert; `user.updated` → update + cache invalidate; `user.deleted` → cascade delete.

### 4.3 Database schema — [ui/prisma/schema.prisma](ui/prisma/schema.prisma)

| Model | Key fields |
|---|---|
| `User` | `clerkId` (unique), `email`, `name`, relations `venues[]`, `settings?` |
| `Venue` | `type` enum (HYPERLIQUID\|BINANCE\|OANDA\|POLYMARKET\|CCXT), **encrypted** `apiKey`, `apiSecret`, `apiPassphrase`, `accountId` (OANDA), `ccxtExchangeId`, `network` (testnet/mainnet), `isPaper`, `isActive`, `riskProfile?` |
| `RiskProfile` | 1:1 with Venue. `maxPositionPct` (3), `maxLeverage` (2), `mandatorySlPct` (2.5), `maxLossPerPositionPct` (8), `dailyLossCircuitBreaker` (4), `maxTotalExposurePct` (30), `maxConcurrentPositions` (5) |
| `UserSettings` | `telegramToken`, `telegramChatId`, `emailNotifications`, `timezone` |

### 4.4 Encryption — [ui/lib/encryption.ts](ui/lib/encryption.ts)

AES-256-GCM. 12-byte random nonce, 16-byte auth tag, base64url-encoded `nonce||ciphertext||tag`. Key derived from `ENCRYPTION_KEY` env (base64url 256-bit). Encryption/decryption server-side only — plaintext never leaves the API route.

### 4.5 Pages

| Route | File | Auth | Purpose |
|---|---|---|---|
| `/` | [ui/app/page.tsx](ui/app/page.tsx) | public | Landing / hero / pricing |
| `/sign-in` / `/sign-up` | `app/sign-{in,up}/[[...]]` | public | Clerk widgets |
| `/onboarding` | [ui/app/onboarding/](ui/app/onboarding/) | private | Collect name |
| `/dashboard` | [ui/app/(protected)/dashboard/page.tsx](ui/app/(protected)/dashboard/page.tsx) | private | Live trading dashboard |
| `/settings` | [ui/app/(protected)/settings/page.tsx](ui/app/(protected)/settings/page.tsx) | private | 5-tab config (Profile, Venues, Risk, Alerts, Security) |
| `/docs` · `/terms` | [ui/app/docs/](ui/app/docs/), [ui/app/terms/](ui/app/terms/) | public | Knowledge base + legal |

### 4.6 Dashboard

~330 lines. Uses custom `usePolled<T>(path, interval)` + `useWebSocket(url)`:

- `/api/account` every **8s**
- `/api/positions` every **8s**
- `/api/status` every **15s**
- `/api/risk` every **60s**
- `/api/decisions` every **10s**
- `ws://localhost:8000/ws` → `price_update`, `account_update`, `positions_update`, `decision` (auto-reconnect 3s backoff)

Components rendered: `StatCard` ×4 (Equity, Unrealized PnL, Open Positions, Sharpe), `TradingChart` (Binance kline WS, SSR-disabled), `EquityChart` (last 40 ticks), `PositionsTable`, `RiskPanel`, `DecisionsFeed` (last 12 unique), `StatusBar`.

### 4.7 API routes — [ui/app/api/](ui/app/api/)

| Method | Route | Purpose |
|---|---|---|
| GET/POST | `/api/venues` | list / create (encrypts creds) |
| PATCH/DELETE | `/api/venues/[id]` | update / remove |
| GET/PATCH | `/api/venues/[id]/risk` | per-venue risk profile |
| GET/PATCH | `/api/user/settings` | notifications + timezone |
| `*` | `/api/agent/[...path]` | **Proxy** to `PYTHON_API_URL`, injects `userId` |
| POST | `/api/webhooks/clerk` | Svix sync |
| GET | `/api/health` | DB liveness |

### 4.8 Custom hooks — [ui/hooks/](ui/hooks/)

- `useWebSocket(url)` — auto-reconnect, JSON parse, unmount guard
- `useIsMobile(bp=768)` — resize-observer responsive breakpoint

---

## 5. What's Working Today (the "17 complete")

- ✅ **Clerk auth + onboarding** — OAuth, email/password, webhook sync, protected route middleware
- ✅ **Live dashboard** — Binance WS candles, equity/PnL cards, decisions feed, positions table, status bar
- ✅ **Python agent loop** — FastAPI, 5-min tick cycle, RSI/EMA/MACD/ATR/BB/ADX/OBV/VWAP indicators, Groq Llama 3.3 70B decisions, risk validation, paper/live toggle
- ✅ **Credential encryption** — AES-256-GCM server-side before Postgres write, zero plaintext at rest
- ✅ **Venue adapter architecture** — abstract `Venue` ABC + registry, 4 concrete implementations
- ✅ **RiskManager enforcement** — all limits hard-coded in Python, not LLM-trusted
- ✅ **Backtesting engine** — reuses same RiskManager + TradingAgent code path as live
- ✅ **Multi-LLM providers** — 5 backends wired behind `LLMProvider` interface
- ✅ **Reconciliation + state consistency** — fill matching, stale trade cleanup, force-close losers
- ✅ **Per-venue risk profiles** — UI + DB + backend hierarchy (yaml > env > defaults)
- ✅ **Settings UI** — 5-tab config incl. Clerk UserProfile embed
- ✅ **Landing page** — hero, pricing tiers, neural background, spotlight animation
- ✅ **Dark design system** — CSS variables, glassmorphism, Framer Motion entrances
- ✅ **Proxy layer** — Next.js catch-all route injects userId before forwarding to Python
- ✅ **Diary + decisions + LLM request logs** — JSONL append-only trails
- ✅ **Supabase credential lookup** — `POST /api/agent/start` can fetch user's encrypted venue
- ✅ **Responsive mobile/desktop layouts** — 1-column mobile, 2-column desktop dashboard

---

## 6. Critical Gaps (the "4 missing / partial")

### 🔴 Telegram alerts — **missing**
`TelegramBackend` exists in [src/alerts/notifier.py](src/alerts/notifier.py) but is **never instantiated in the trading loop**. No event hooks call `notifier.emit()`. Users save `telegramToken` + `telegramChatId` in Settings — and nothing happens. Critical for production: silent failure modes kill capital.

### 🔴 Backtesting UI — **missing**
Backend scaffold exists ([src/backtesting/engine.py](src/backtesting/engine.py) + CLI). No frontend page. Users cannot validate strategies before going live.

### 🔴 Agent persistence — **missing**
Server restart silently kills the running agent. No `agent_running=true` check in Supabase on boot. No auto-resume. No user alert. When PM2/systemd bounces the server at 3am, the agent is just gone.

### 🔴 Stripe / payments — **missing**
Pricing tiers (Free / Starter / Pro / Enterprise) shown on landing page. No Stripe webhook. No plan-limit enforcement in backend. Anyone can use Pro features on Free.

### 🟡 Multi-AI council — **partial**
Groq fires every tick. Anthropic + Gemini SDKs installed and provider classes built, but they're dormant. No consensus voting logic (`2-of-3` agreement gate).

### 🟡 Live order execution — **needs keys, not code**
Code path fully implemented end-to-end. Blocked only by missing Hyperliquid `PRIVATE_KEY` in `.env`. Paper mode works.

---

## 7. Architecture Debt

| # | Severity | Issue | Fix |
|---|---|---|---|
| 1 | 🔴 critical | Shared `ENCRYPTION_KEY` in both Next.js and Python `.env` — single point of failure; leak → every user's creds compromised | Migrate to **AWS KMS** or **Supabase Vault**. Per-user keys, rotatable. |
| 2 | 🔴 critical | WebSocket handshake has **no auth** — any client connects to `ws://localhost:8000` and receives all decisions + account data | Validate Clerk JWT on WS upgrade request |
| 3 | 🟡 high | `psycopg2` sync calls inside async FastAPI block the event loop; under load, all WS updates freeze | Replace with `asyncpg` or `encode/databases`. ~10× throughput. |
| 4 | 🟡 high | No Binance WS reconnect loop — Binance forcibly closes every 24h; agent silently stops receiving data | Exponential backoff, 5 retries, Telegram alert on fail |
| 5 | 🟡 high | Decisions feed array unbounded in Python memory — after 12h+, process memory balloons | Cap in-memory buffer at 100; persist all to Supabase `decisions` table async |
| 6 | 🔵 medium | **Zero test suite** — no pytest, no regression detection. RiskManager / IndicatorEngine bugs invisible until they cost real money | pytest: RiskManager edge cases, IndicatorEngine (known OHLCV → known values), Venue adapter mocks |
| 7 | 🔵 medium | No CDN / edge caching — all requests hit origin; 1000+ concurrent users will see slow API routes | Vercel Edge (built-in) + Cloudflare for Python API + Redis indicator cache |
| 8 | 🔵 medium | No observability — no Sentry, structured logs, or Prometheus metrics; 3am crash = you'll never know why | Sentry (Next.js + Python) + structured JSON + Prometheus + Grafana for tick/LLM/order latency |

---

## 8. MetaTrader 4/5 Integration — Dedicated Plan

The MetaTrader ecosystem is **9 million+ retail traders worldwide** using MT4/MT5 through 600+ brokers. This is the largest single unlock on the roadmap.

### Three integration paths

| Option | Approach | Pros | Cons | Recommendation |
|---|---|---|---|---|
| **1. MetaAPI cloud SDK** | REST + WebSocket bridge hosted by MetaAPI | Works on Linux (keeps current deploy), no EA coding, streaming quotes + orders + account data, 600+ brokers | ~$30/mo in prod (free dev tier) | **✅ Start here** |
| **2. DWX Connect** | MQL4/5 EA + ZeroMQ Python subscriber | Open-source, self-hosted, free forever | Requires Windows MT4/MT5 instance running; broker-specific setup | Use for power users who want zero recurring cost |
| **3. MT5 native Python (`MetaTrader5` pip pkg)** | Direct C++ bindings | Fastest execution | **Windows-only** — breaks Linux server setup | Skip unless going Windows-native |

### `MetaTraderVenue` adapter — fits existing [src/venues/base.py](src/venues/base.py) interface

```python
class MetaTraderVenue(Venue):
    """Drop-in replacement for CcxtVenue, wraps MetaAPI SDK."""

    def __init__(self, metaapi_token: str, account_id: str, paper: bool = True):
        self.api = MetaApi(metaapi_token)
        self.account_id = account_id
        self.paper = paper

    async def get_balances(self) -> list[Balance]:
        conn = await self._get_connection()
        info = await conn.get_account_information()
        return [Balance(currency=info["currency"], total=info["balance"], available=info["freeMargin"])]

    async def get_positions(self) -> list[Position]:
        conn = await self._get_connection()
        return [self._normalise(p) for p in await conn.get_positions()]

    async def place_order(self, symbol, side, quantity, order_type, price=None,
                          stop_loss=None, take_profit=None, leverage=None) -> Order:
        if self.paper:
            return Order(...status="paper"...)
        conn = await self._get_connection()
        fn = conn.create_market_buy_order if side == "buy" else conn.create_market_sell_order
        result = await fn(symbol, quantity, sl=stop_loss, tp=take_profit)
        return self._normalise_order(result)

    async def stream_prices(self, symbol: str, callback):
        conn = await self._get_streaming_connection()
        await conn.subscribe_to_market_data(symbol)
        conn.add_synchronization_listener(PriceListener(callback))
```

Register in [src/venues/registry.py](src/venues/registry.py) under `"metatrader"` (or `"mt4"`/`"mt5"`). Add `METATRADER` to the Prisma `VenueType` enum. Surface new fields in Settings: `metaApiToken`, `metaApiAccountId`.

### Instruments this unlocks

EURUSD · GBPUSD · USDJPY · USDCHF · AUDUSD · USDCAD · NZDUSD · EURGBP · EURJPY · GBPJPY · **XAUUSD** (Gold) · **XAGUSD** (Silver) · **US30** · **SPX500** · **NAS100** · **DE40** · **UK100** · all crosses — effectively every symbol the broker carries.

---

## 9. Roadmap — 8 Weeks to World-Class (OODA)

### Week 1 — close critical gaps 🔴 *now*
- Wire `Notifier` in Python loop: `on_fill`, `on_sl_trigger`, `on_risk_block`, `on_agent_crash` event hooks
- Add **JWT auth to WebSocket handshake** — validate Clerk token on upgrade
- **Agent persistence**: check Supabase `agent_running=true` on server boot, auto-resume
- **Dead man's switch**: if no tick for 30min, close all positions + alert user
- `psycopg2` → `asyncpg`, Binance WS reconnect loop, cap decisions buffer at 100

### Week 2 — MetaTrader + new venues 🟡 *high priority*
- Build `MetaTraderVenue` via MetaAPI SDK; test EURUSD paper trading
- Add `METATRADER` venue type in Settings UI (token + account ID fields)
- Enable Bybit, OKX, Kraken — already in CCXT, just add to venue dropdown
- TwelveData economic calendar: **auto-pause agent 5min before high-impact events** (NFP, CPI, FOMC)
- Alternative.me fear/greed index → inject into LLM context (free, 1 line)

### Week 3 — TradingView webhooks + backtesting UI 🟡 *high priority*
- `POST /api/webhook/tradingview` — validate signature, execute order from Pine Script alert
- Backtesting page: date range picker + symbol selector + results display
- Metrics: equity curve, win rate, max DD, Sharpe, Calmar, trade count
- Trade journal page with filter/export CSV (tax prep)
- Equity curve persistence to Supabase every tick (not just in-memory)

### Week 4 — AI council + RAG memory 🟡 *high priority*
- Parallel LLM query: Groq + Claude + Gemini per tick. **2/3 vote required** to execute
- Show all 3 opinions + confidence breakdown in AI Decisions feed
- Add `pgvector` extension to Supabase; store every decision + outcome as embedding
- **RAG retrieval**: top-5 similar past decisions injected into LLM context pre-call
- Reinforcement signal: closed-trade PnL updates quality score in vector DB

### Week 5 — intelligence engine 🔵 *medium*
- Multi-timeframe confluence: compute indicators on 1h + 4h + 1D, all must agree
- News sentiment: CryptoCompare news API → summarise → inject into prompt
- Correlation matrix: rolling 30d, block trade if too correlated with existing position
- Funding rate monitor: auto-reduce or flip on extreme +/- funding
- On-chain: exchange netflow from Glassnode → large inflows = sell pressure signal

### Week 6 — platform growth 🔵 *medium*
- **Natural language commands**: "when BTC RSI 30 buy 5%" → parsed to strategy rule
- Strategy marketplace MVP: publish config, set price, Stripe revenue split
- Public leaderboard: anonymous Sharpe ranking, platform-verified (not self-reported)
- Interactive Brokers adapter (`ibapi` wrapper) — stocks + options + futures
- Alpaca adapter — US stocks/options

### Week 7 — Stripe + mobile 🔵 *medium*
- Stripe webhook → update plan in Supabase → enforce limits in backend
- **Free:** paper only, 1 venue, 1 asset · **Starter:** 2 venues, 3 assets · **Pro:** unlimited · **Enterprise:** white-label
- React Native / Expo mobile app: start/stop, live PnL, Expo Push notifications
- VaR calculations: 95%/99% Monte Carlo 10k sims in Risk tab
- Tax reporting: FIFO cost basis, realized PnL export, PDF summary for CPA

### Week 8 — observability + institutional 🟣 *enterprise*
- Sentry (Next.js + Python), structured JSON logs, PagerDuty for criticals
- Prometheus metrics: tick latency, LLM response time, order fill time, WS uptime
- Migrate `ENCRYPTION_KEY` → AWS KMS / Supabase Vault. Per-user rotation.
- Copy trading: follow any public agent, auto-mirror positions proportionally
- White-label API: enterprise subdomain, custom logo, API access

---

## 10. Feature Gap Tiers (the "31 world-class additions")

### Tier 1 — Intelligence engine (highest alpha)
- 🔴 **Order flow / DOM** — Level 2 depth, tape reading, bid/ask imbalance. Where institutional traders live.
- 🔴 **Economic calendar auto-pause** — skip NFP/CPI/FOMC. News destroys algos that ignore them.
- 🟡 News sentiment NLP — real-time headline analysis into LLM context
- 🟡 On-chain analytics — exchange flows, whale wallets, funding (Glassnode/Nansen)
- 🟡 Correlation matrix — avoid stacking correlated positions
- 🟡 MTF confluence — 1h + 4h + 1D must align
- 🔵 Fear/greed index — crypto F&G, VIX, put/call
- 🔵 Funding rate monitor — extreme funding = squeeze risk

### Tier 2 — AI architecture (the real moat)
- 🔴 **RAG trade memory** — vector DB stores every decision + outcome. True learning loop.
- 🔴 **Council consensus** — Groq + Claude + Gemini vote 2/3. Eliminates single-LLM hallucination.
- 🟡 RL feedback loop — reward from actual PnL updates prompt weights
- 🟡 Natural language commands — "buy BTC when RSI < 30" from chat, no code
- 🔵 Explainable AI — visual confidence breakdown, indicator weights, "why this BUY?"
- 🔵 ML backtest optimizer — walk-forward, Bayesian parameter search

### Tier 3 — Execution quality
- 🔴 **TradingView webhooks** — every retail trader already uses TV
- 🟡 Smart order routing — VWAP/TWAP, iceberg for institutional size
- 🔵 MEV protection — Flashbots/MEV Blocker for on-chain orders
- 🔵 Order book heatmap — spot walls, spoofing, large limit orders

### Tier 4 — Platform (the moat that compounds)
- 🟡 Copy / social trading — revenue split, virality engine
- 🟡 Strategy marketplace — verified returns, monthly subs, 30% platform cut
- 🟡 Mobile app — React Native, push, App Store credibility
- 🔵 Portfolio optimizer — Kelly Criterion, MPT, Sharpe-max allocation
- 🔵 Tax reporting — FIFO/LIFO, realized PnL, HMRC/IRS CSV
- 🔵 Public leaderboard — top 100 by Sharpe, bragging rights = organic growth

### Tier 5 — Risk & compliance (institutional grade)
- 🟡 VaR calculations — 95%/99%, Monte Carlo, unlocks hedge fund clients
- 🟡 Kill switch + dead man's switch — one-click close all; auto-close if silent 30min
- 🔵 Compliance audit trail — immutable log of every decision, order, rejection

---

## 11. New Venues Roadmap (the "14")

### Forex / CFDs / stocks — MetaTrader ecosystem
| Venue | Via | Priority |
|---|---|---|
| **MetaTrader 4/5** | MetaAPI SDK | 🔴 critical |
| **Interactive Brokers** | IBKR TWS API / `ibapi` | 🔴 critical |
| Alpaca | `alpaca-trade-api` | 🟡 high |
| FXCM | `fxcmpy` SDK | 🟡 high |

### Crypto — perps + spot
| Venue | Via | Priority |
|---|---|---|
| Bybit · OKX · Kraken · Coinbase Advanced | **CCXT (already supported)** — just wire UI | 🟡 high |
| dYdX v4 | `dydx-v4-client` SDK | 🟡 high |
| GMX (Arbitrum DEX perps) | Web3.py + GMX SDK | 🟡 high |

### Data-only feeds (make the LLM smarter)
| Feed | Purpose |
|---|---|
| Glassnode | On-chain analytics |
| CryptoCompare | News + social sentiment |
| TwelveData | Stocks + forex + **economic calendar** |
| Alternative.me | Fear/greed index (free) |

---

## 12. Where We Want to Be — The World-Class Definition

After the 8-week plan executes: **a multi-venue AI trading platform covering crypto, forex, stocks, and DeFi** — with MetaTrader support for the 9 million MT4/MT5 traders worldwide. RAG memory that learns from every trade. A council of 3 LLMs that must agree before touching real money. TradingView webhook execution that every retail trader already knows how to use. Social copy trading for viral growth. And the institutional-grade risk and observability layer that hedge funds require.

That's not a hobby project. That's a company.

---

## Appendix — Running the system

```bash
# Backend — live loop (aiohttp)
poetry run qunta --venue hyperliquid --assets "BTC ETH SOL" --interval 5m

# Backend — FastAPI + WebSocket (for UI)
poetry run python src/server.py

# Backtest
poetry run python -m src.backtesting.engine --venue hyperliquid --symbol BTC --timeframe 1h --days 30

# Status CLI
poetry run python -m src.dashboard.status --venue hyperliquid

# Frontend
cd ui && pnpm install && pnpm dev    # :3000
```

### Env vars

**Python backend (`.env`):**
`LLM_PROVIDER` · `LLM_MODEL` · `ANTHROPIC_API_KEY` · `GROQ_API_KEY` · `GEMINI_API_KEY` · `HYPERLIQUID_PRIVATE_KEY` · `HYPERLIQUID_NETWORK` · `CCXT_EXCHANGE` · `CCXT_API_KEY` · `CCXT_SECRET` · `OANDA_API_KEY` · `OANDA_ACCOUNT_ID` · `OANDA_ENV` · `BINANCE_API_KEY` · `BINANCE_SECRET` · `BINANCE_MARKET` · `TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID` · `ENCRYPTION_KEY` · `SUPABASE_URL` · `SUPABASE_KEY` · all risk thresholds

**Frontend (`ui/.env.local`):**
`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` · `CLERK_SECRET_KEY` · `CLERK_WEBHOOK_SECRET` · `DATABASE_URL` · `ENCRYPTION_KEY` · `NEXT_PUBLIC_API_URL` · `NEXT_PUBLIC_WS_URL` · `PYTHON_API_URL`
