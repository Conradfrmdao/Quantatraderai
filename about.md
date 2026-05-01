# QuntaTradeAI — Complete Technical Reference & Vision Document

> This document is a full, agent-ready briefing of the QuntaTradeAI codebase: every file, every system, every known gap, and the long-term vision. Paste this into any AI agent to get full context instantly.

---

## 1. What Is QuntaTradeAI?

QuntaTradeAI is an **autonomous, multi-venue AI trading platform** powered by Claude (Anthropic), Groq, Gemini, and Ollama. It trades crypto perpetuals, crypto spot, forex, and US equities across 10+ exchanges. The system runs 24/7 without human intervention, using LLMs to make fully reasoned trade decisions within hard-coded risk guardrails.

It is **not** a signal bot. It is **not** a simple algo. It is a full-stack, production-grade AI agent with its own reasoning loop, risk management, memory, backtesting engine, copy trading, strategy marketplace, and natural-language command bar.

**Stack summary:**
- Backend: Python 3.12 + FastAPI + asyncio
- Frontend: Next.js 16 (App Router) + React 19 + TypeScript + Tailwind v4
- Database: PostgreSQL (Supabase) + Prisma ORM + pgvector (RAG)
- Auth: Clerk (JWT, webhook sync)
- Payments: Stripe
- LLMs: Anthropic Claude, Groq, Gemini, Ollama, OpenRouter
- Exchanges: Hyperliquid, Binance, OANDA, MetaTrader, Alpaca, IBKR, CCXT (100+ exchanges)
- Charting: TradingView lightweight-charts + recharts
- Observability: Sentry + structlog + Prometheus

---

## 2. Repository Layout

```
QuntaTradeAI/
├── src/                        # Python backend
│   ├── main.py                 # CLI entry point + legacy trading loop
│   ├── server.py               # FastAPI production server
│   ├── config_loader.py        # All env-based config (100+ keys)
│   ├── risk_manager.py         # Hard risk guards (all trades must pass)
│   ├── risk.yaml               # Per-venue/asset override rules
│   ├── agent/
│   │   ├── decision_maker.py   # Core LLM trading brain
│   │   ├── council.py          # Multi-LLM voting council (built, not wired)
│   │   ├── multi_leg.py        # Multi-leg order strategies
│   │   ├── nl_parser.py        # NL → trade intent parser
│   │   └── providers/
│   │       ├── factory.py      # Provider factory (resolve LLM_PROVIDER)
│   │       ├── anthropic_provider.py
│   │       ├── groq_provider.py
│   │       ├── gemini_provider.py
│   │       ├── ollama_provider.py
│   │       └── openrouter_provider.py
│   ├── venues/
│   │   ├── base.py             # Abstract Venue interface
│   │   ├── models.py           # Candle, Ticker, Balance, Position, Order, SymbolMeta
│   │   ├── registry.py         # Name → Venue adapter dispatcher
│   │   ├── crypto/
│   │   │   ├── hyperliquid.py  # Hyperliquid perps adapter
│   │   │   ├── binance.py      # Binance spot + futures adapter
│   │   │   └── ccxt_adapter.py # Generic CCXT (Bybit, OKX, Kraken, Coinbase, …)
│   │   ├── forex/
│   │   │   ├── oanda.py        # OANDA v20 REST adapter
│   │   │   └── metatrader.py   # MetaAPI (MT4/MT5) adapter
│   │   └── stocks/
│   │       ├── alpaca.py       # Alpaca (US stocks/options)
│   │       └── ibkr.py         # Interactive Brokers (IB Gateway/TWS)
│   ├── indicators/
│   │   ├── local_indicators.py # EMA, SMA, RSI, MACD, BBands, ATR, ADX, OBV, VWAP, StochRSI
│   │   └── taapi_client.py     # Legacy TAAPI wrapper (fallback)
│   ├── backtesting/
│   │   ├── engine.py           # Backtesting engine (same risk + LLM as live)
│   │   ├── mock_venue.py       # In-memory exchange simulator
│   │   ├── data_loader.py      # Historical candle fetcher + disk cache
│   │   └── report.py           # Metrics: return, drawdown, Sharpe, win rate
│   ├── alerts/
│   │   └── notifier.py         # Telegram + console alert backends
│   ├── memory/
│   │   └── rag.py              # pgvector RAG: store, retrieve, quality-weight decisions
│   ├── intel/
│   │   ├── mtf_confluence.py   # Multi-timeframe (1h/4h/1d) technical confluence
│   │   ├── economic_calendar.py # High-impact event detection (NFP, CPI, FOMC…)
│   │   ├── sentiment.py        # Fear & Greed index (Alternative.me)
│   │   ├── news.py             # News sentiment (CryptoCompare)
│   │   └── correlation.py      # Asset correlation matrix
│   ├── risk/
│   │   ├── adaptive.py         # ATR-based adaptive position sizing
│   │   ├── var.py              # Value-at-Risk calculation
│   │   ├── slippage.py         # Expected slippage model
│   │   └── correlation_hedge.py # Reduce allocation if correlated position open
│   ├── copy_trading/
│   │   ├── mirror.py           # Leader→follower trade mirroring (proportional)
│   │   └── symbol_map.py       # Cross-venue symbol translation + asset family detect
│   ├── services/
│   │   ├── encryption.py       # AES-256-GCM encrypt/decrypt for credentials
│   │   ├── supabase_reader.py  # Fetch encrypted venue credentials from DB
│   │   └── persistence.py      # Save/load agent state across restarts
│   ├── observability/
│   │   └── setup.py            # Sentry init, structlog JSON, Prometheus metrics
│   ├── trading/
│   │   └── hyperliquid_api.py  # Legacy Hyperliquid client (542 lines, pre-adapter)
│   ├── dashboard/
│   │   └── status.py           # CLI status viewer
│   └── utils/
│       ├── formatting.py
│       └── prompt_utils.py
├── ui/                         # Next.js frontend
│   ├── app/
│   │   ├── layout.tsx          # Root layout (Clerk provider, Framer Motion)
│   │   ├── page.tsx            # Landing page
│   │   ├── globals.css         # Tailwind v4 dark theme
│   │   ├── (protected)/        # Auth-gated routes
│   │   │   ├── dashboard/      # Main trading dashboard
│   │   │   ├── settings/       # Venue + API key management
│   │   │   ├── backtest/       # Backtesting runner
│   │   │   ├── journal/        # Trade history (CSV export)
│   │   │   ├── audit/          # Compliance audit log
│   │   │   ├── copy-trading/   # Mirror leader trades
│   │   │   ├── rag-memory/     # RAG memory inspector
│   │   │   ├── marketplace/    # Strategy marketplace
│   │   │   ├── billing/        # Plan info + Stripe portal
│   │   │   └── calendar/       # Economic events calendar
│   │   ├── api/
│   │   │   ├── venues/         # CRUD venues + test connection + risk profile
│   │   │   ├── agent/          # Start/stop/killswitch (proxied to Python)
│   │   │   ├── equity/         # Equity curve persistence
│   │   │   ├── trades/         # Trade journal CRUD
│   │   │   ├── audit/          # Audit log CRUD
│   │   │   ├── backtest/run/   # Backtest proxy
│   │   │   ├── strategies/     # Strategy marketplace
│   │   │   ├── marketplace/    # Strategy listing + subscribe
│   │   │   ├── copy/           # Copy trading relationships
│   │   │   ├── user/settings/  # User settings CRUD
│   │   │   ├── billing/        # Stripe plan management
│   │   │   ├── price/          # Live candle data (Binance public)
│   │   │   ├── chart/          # Chart candle proxy
│   │   │   ├── leaderboard/    # Top traders by return %
│   │   │   ├── rag-memory/     # RAG memory entries
│   │   │   ├── health/         # Liveness probe
│   │   │   └── webhooks/
│   │   │       ├── clerk/      # Clerk user sync (Svix-signed)
│   │   │       ├── stripe/     # Stripe subscription updates
│   │   │       └── tradingview/ # TradingView alert → trade exec
│   │   ├── sign-in/, sign-up/  # Clerk auth pages
│   │   ├── onboarding/         # First-run venue setup wizard
│   │   ├── leaderboard/        # Public leaderboard page
│   │   ├── docs/               # API documentation
│   │   └── terms/              # Terms of service
│   ├── components/
│   │   ├── TradingChart.tsx     # TradingView lightweight-charts candlestick
│   │   ├── EquityChart.tsx      # recharts equity curve
│   │   ├── DecisionsFeed.tsx    # LLM decision stream
│   │   ├── RiskPanel.tsx        # Risk limits display
│   │   ├── StatCard.tsx         # Metric card (balance, PnL, Sharpe, etc.)
│   │   ├── StatusBar.tsx        # Top bar: venue, model, uptime, tick count
│   │   ├── NLCommandBar.tsx     # Natural language trade command input
│   │   ├── MacroIntelStrip.tsx  # Fear & greed, correlation, events
│   │   ├── MarketPicker.tsx     # Asset selector
│   │   ├── UpgradePrompt.tsx    # Plan limit banner
│   │   ├── SignOutGuard.tsx     # Logout handler
│   │   ├── ErrorBoundary.tsx    # React error boundary
│   │   ├── Logo.tsx             # Brand logo
│   │   ├── Toast.tsx            # Notification toasts
│   │   └── ui/
│   │       ├── button.tsx, card.tsx, dark-select.tsx
│   │       ├── neural-background.tsx  # Three.js particle animation
│   │       ├── spotlight.tsx          # Aceternity spotlight effect
│   │       ├── canvas-reveal-effect.tsx
│   │       ├── infinite-slider.tsx
│   │       ├── progressive-blur.tsx
│   │       └── splite.tsx
│   ├── hooks/
│   │   ├── useWebSocket.ts     # WS connection to Python /ws (Clerk JWT)
│   │   ├── useVenues.ts        # Fetch user venues
│   │   └── useIsMobile.ts      # Mobile viewport detection
│   ├── lib/
│   │   ├── prisma.ts           # Prisma client (PrismaPg adapter)
│   │   ├── auth.ts             # Clerk session + DB user lookup (60s cache)
│   │   ├── encryption.ts       # AES-256-GCM (matches Python)
│   │   ├── plan-limits.ts      # Plan tier feature matrix
│   │   ├── rate-limit.ts       # In-memory rate limiter
│   │   └── payments/
│   │       ├── stripe.ts       # Stripe customer portal + sessions
│   │       └── index.ts        # Payment provider factory
│   ├── prisma/
│   │   ├── schema.prisma       # Full DB schema (see Section 4)
│   │   └── migrations/         # Prisma migration history
│   ├── middleware.ts            # Clerk auth middleware
│   ├── proxy.ts                # HTTP proxy config (→ Python backend)
│   ├── next.config.ts          # Next.js + Sentry config
│   └── prisma.config.ts        # Prisma adapter config
├── mobile/                     # Expo/React Native (stub, ~5% complete)
│   ├── app.config.ts
│   ├── app/(app)/dashboard.tsx  # 4 stat cards + start/stop button
│   └── app/(auth)/sign-in.tsx   # Clerk sign-in screen
├── tests/
│   ├── conftest.py
│   ├── test_risk_manager.py    # RiskManager unit tests
│   ├── test_indicators.py      # Indicator output tests
│   └── test_server_integration.py # FastAPI endpoint integration tests
├── Dockerfile                  # Multi-stage builder + runtime image
├── pyproject.toml              # Python 3.12+, Poetry, all deps
├── .env.example                # Reference for 100+ env vars
└── risk.yaml                   # Per-venue/asset risk overrides
```

---

## 3. Core Python Backend — Deep Dive

### 3.1 Entry Points

#### `src/main.py` — CLI Trading Loop
The original entry point. CLI: `poetry run qunta --venue hyperliquid --assets "BTC ETH" --interval 5m`

- **`run_loop()`**: Async event loop. Every `interval` seconds:
  1. Fetch balances, positions, candles, tickers
  2. Compute local indicators
  3. Build JSON context
  4. Call `TradingAgent.decide()`
  5. Pass decisions through `RiskManager.validate_trade()`
  6. Execute via `Venue.place_order()`
  7. Log to `diary.jsonl` + `decisions.jsonl`
  8. Force-close any position that exceeds -8% loss
  9. Emit aiohttp events on `/diary`, `/api/status`, `/api/positions`

- Cap: decisions buffer capped at 60 seconds to prevent context overflow
- Reconciliation: after each tick, reconcile intended vs actual exchange positions

#### `src/server.py` — FastAPI Production Server
The production-grade server. Port 8000 (configurable via `API_PORT`).

**REST endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Agent status + uptime |
| GET | `/api/account` | Account balances |
| GET | `/api/positions` | Open positions |
| GET | `/api/decisions` | Recent LLM decisions |
| GET | `/api/risk` | Current risk metrics |
| POST | `/api/agent/start` | Start agent (venue, assets, interval) |
| POST | `/api/agent/stop` | Stop agent gracefully |
| POST | `/api/agent/killswitch` | Emergency: close all positions immediately |
| GET | `/metrics` | Prometheus metrics |

**WebSocket:**
- `/ws?token=<clerk_jwt>`: JWT-gated real-time stream
- Validates JWT via Clerk JWKS endpoint
- Pushes: price ticks, position updates, decisions, status events

**Plan enforcement:**
- `_get_user_plan()`: checks DB for user plan, 30-second cache
- FREE: blocks live trading (paper only), 1 asset max
- STARTER: live trading, 2 venues, 2 assets
- PRO: full feature set, council, RAG, copy trading
- ENTERPRISE: unlimited

**Integrations:**
- Sentry error tracking (optional, via `SENTRY_DSN`)
- Structured JSON logging via structlog
- Prometheus metrics at `:9090/metrics`

---

### 3.2 Config & Risk

#### `src/config_loader.py` — Centralized Config
Single `CONFIG` dict from 100+ environment variables. Grouped into:
- Venue selection (`VENUE`, `ASSETS`, `INTERVAL`)
- All LLM providers (keys, models, temperature, thinking budget)
- All exchange credentials (API keys, secrets, sandbox flags)
- Risk thresholds (position %, leverage, drawdown %, reserve %)
- Feature flags (tool calling, extended thinking, council mode, RAG, copy trading)
- Observability (Sentry DSN, Prometheus port, log level)
- Alerts (Telegram token + chat ID)

#### `src/risk_manager.py` — The Safety Gate
**Every single trade must pass `validate_trade()` before execution.** No exceptions.

Guards (all configurable via env + risk.yaml):
| Guard | Default | Description |
|-------|---------|-------------|
| Position size | ≤ 3% account | Max single trade allocation |
| Total exposure | ≤ 20% account | Sum of all open positions |
| Leverage | ≤ 2x | Max effective leverage |
| Daily drawdown | -4% circuit breaker | Stops trading for the day |
| Concurrent positions | ≤ 5 | Max simultaneous open trades |
| Balance reserve | 30% minimum | Must always hold 30% in reserve |
| Stop-loss | Mandatory 2.5% | Injected if trade has no SL |
| Max loss per position | -8% force-close | Auto-exit when exceeded |

Per-venue/asset-class overrides are loaded from `risk.yaml`.

#### `risk.yaml` — Override Rules
YAML structure:
```yaml
default:
  max_position_pct: 0.03
  max_leverage: 2.0
  ...
overrides:
  - venue: binance
    asset_class: crypto_spot
    max_position_pct: 0.05
```

---

### 3.3 LLM Decision Engine

#### `src/agent/decision_maker.py` — The Brain
`TradingAgent` class. The core reasoning engine.

**System prompt (450+ lines):** Covers risk-adjusted returns, position hysteresis, cooldown periods, exit planning, multi-asset coordination, funding rate awareness, correlation-adjusted sizing.

**Tool calling** (when `ENABLE_TOOL_CALLING=true`):
- Tool: `fetch_indicator(indicator, asset, interval)`
- Indicators: ema, sma, rsi, macd, bbands, atr, adx, obv, vwap, stoch_rsi
- Model calls tool mid-reasoning to pull fresh indicator values

**Extended thinking** (when `ENABLE_THINKING=true`):
- Budget: 10,000 tokens of internal reasoning before output
- Only works with Anthropic claude-sonnet-4-6 or claude-opus-4-7

**Output contract** (JSON):
```json
{
  "reasoning": "multi-paragraph explanation of current market read",
  "trade_decisions": [
    {
      "asset": "BTC",
      "action": "buy | sell | hold | close",
      "allocation_usd": 500,
      "order_type": "market | limit | stop_limit",
      "limit_price": 65000,
      "tp_price": 68000,
      "sl_price": 63500,
      "exit_plan": "exit on RSI overbought or -3% adverse move",
      "rationale": "EMA crossover, RSI momentum, aligned with 4h trend"
    }
  ]
}
```

**Fallback chain:** Primary LLM → Anthropic (if key set) → Groq → Gemini
**Malformed JSON sanitizer:** Cheap Haiku call (`claude-haiku-4-5-20251001`) to coerce broken LLM output

#### `src/agent/council.py` — Multi-LLM Voting (built, not yet wired)
Multiple LLMs (Claude + Groq + Gemini) each make independent decisions. Decisions are aggregated by 2/3 majority vote. Reduces single-model error risk. Plan: wire this in for PRO+ plans.

#### `src/agent/nl_parser.py` — NL Command Parser
Parses natural language commands from the `NLCommandBar` component:
- Input: "Buy 100 BTC at limit 65000 with SL at 63000"
- Output: structured `TradeIntent` dict with asset, action, size, price, sl, tp

#### LLM Providers (`src/agent/providers/`)
| Provider | Default Model | Notes |
|----------|--------------|-------|
| Anthropic | claude-sonnet-4-6 | Tool calling + extended thinking |
| Groq | llama-3.3-70b | Free tier, fast |
| Gemini | gemini-2.0-flash | Free tier |
| Ollama | llama3.2 | Local, air-gapped |
| OpenRouter | deepseek-r1 | Free models available |

`factory.py` resolves `LLM_PROVIDER` env → instantiates correct class.

---

### 3.4 Venue Adapters

#### `src/venues/base.py` — Abstract Interface
All exchanges implement 10 methods:
```python
get_balances() → list[Balance]
get_positions() → list[Position]
get_ticker(symbol) → Ticker
get_candles(symbol, timeframe, lookback) → list[Candle]
get_symbol_info(symbol) → SymbolMeta
place_order(symbol, side, qty, order_type, price, sl, tp, leverage) → Order
cancel_order(symbol, order_id) → bool
close_position(symbol, quantity) → Order | None
```

#### `src/venues/models.py` — Shared Data Models
```python
@dataclass Candle: ts, open, high, low, close, volume
@dataclass Ticker: bid, ask, last, volume_24h
@dataclass Balance: asset, free, locked, total
@dataclass Position: symbol, side, qty, entry_price, liquidation_price, unrealized_pnl, leverage
@dataclass Order: id, symbol, side, qty, price, status, filled_qty, fee
@dataclass SymbolMeta: min_qty, qty_step, min_notional, price_step, asset_class
```

`AssetClass`: `"crypto_perp" | "crypto_spot" | "forex" | "stocks"`

#### `src/venues/registry.py` — Router
| Name | Adapter |
|------|---------|
| `hyperliquid` | HyperliquidVenue |
| `binance`, `binance:spot`, `binance:futures` | BinanceVenue |
| `bybit`, `okx`, `kraken`, `coinbase` | CcxtVenue shortcut |
| `ccxt`, `ccxt:<exchange>` | CcxtVenue (100+ exchanges) |
| `oanda` | OandaVenue |
| `metatrader`, `mt4`, `mt5` | MetaTraderVenue (MetaAPI) |
| `alpaca` | AlpacaVenue |
| `ibkr` | IBKRVenue |

---

### 3.5 Indicators

#### `src/indicators/local_indicators.py`
All computed locally from OHLCV — no external API required:
- `ema(candles, period)` — Exponential Moving Average
- `sma(candles, period)` — Simple Moving Average
- `rsi(candles, period)` — Relative Strength Index
- `macd(candles)` — MACD line + signal + histogram
- `bbands(candles, period, std_dev)` — Bollinger Bands (upper, mid, lower)
- `atr(candles, period)` — Average True Range
- `adx(candles, period)` — Average Directional Index
- `obv(candles)` — On-Balance Volume
- `vwap(candles)` — Volume Weighted Average Price
- `stoch_rsi(candles, period)` — Stochastic RSI

`compute_all(candles) → dict` returns all indicators pre-keyed for LLM context injection.

---

### 3.6 Backtesting

#### `src/backtesting/engine.py`
CLI: `poetry run python -m src.backtesting.engine --venue hyperliquid --symbol BTC --timeframe 1h --days 30`

- Loads historical candles from `data_loader.py` (cached to `.backtest_cache/`)
- Replays bars through **same** `RiskManager` + `TradingAgent` as live
- Default strategy: RSI(14) crossover (>70 sell, <30 buy) or LLM strategy (slower, costs tokens)
- Output: metrics dict + equity curve array

#### `src/backtesting/mock_venue.py`
In-memory exchange: tracks equity curve, marks positions to market each bar, applies 5bps taker fee.

#### `src/backtesting/report.py`
Computes: total return %, max drawdown %, win rate %, Sharpe ratio, trade count, avg PnL per trade.

---

### 3.7 Intelligence Modules

#### `src/intel/mtf_confluence.py`
Fetches candles on 1h, 4h, 1d. Computes RSI, MACD, EMA on each. Returns `mtf_alignment_score` (0–1) — buy/sell only if ≥2 of 3 timeframes agree.

#### `src/intel/economic_calendar.py`
Fetches next 24h high-impact events from TwelveData: NFP, CPI, FOMC, ECB, BoE. Agent should pause (return HOLD) within 5 min of event.

#### `src/intel/sentiment.py`
Fear & Greed Index from Alternative.me (free API). Returns numeric score + label (Extreme Fear → Extreme Greed).

#### `src/intel/news.py`
News sentiment from CryptoCompare API. Positive/negative tone per asset.

#### `src/intel/correlation.py`
Computes Pearson correlation matrix between assets. Used by `correlation_hedge.py` to reduce allocation when a new position correlates >0.7 with an existing one.

---

### 3.8 Advanced Risk Modules

#### `src/risk/adaptive.py`
ATR-based adaptive sizing: when volatility is high (large ATR), reduce position size proportionally. When volatility is low, allow slightly larger allocation (within hard cap).

#### `src/risk/var.py`
Value-at-Risk at 95% confidence using historical simulation on rolling 30-day returns.

#### `src/risk/slippage.py`
Models expected slippage based on order size vs 24h volume. Warns if slippage likely exceeds 0.1%.

#### `src/risk/correlation_hedge.py`
Before placing a new trade, checks correlation of new asset against all open positions. If any correlation > 0.7, reduces new position allocation by 30–50%.

---

### 3.9 Alerts

#### `src/alerts/notifier.py`
`TradingEvent` kinds: `trade_opened`, `trade_closed`, `stop_loss_hit`, `circuit_breaker_tripped`, `decision_error`, `info`

Backends:
- `ConsoleBackend`: always on, logs to stderr
- `TelegramBackend`: async aiohttp POST to Telegram bot (non-blocking)

`build_notifier()` reads `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`.

**Status:** Notifier class is complete but **not instantiated in the live trading loop** — Telegram alerts are not firing. This is a documented critical gap.

---

### 3.10 Memory & RAG

#### `src/memory/rag.py`
Stores trade decisions in `pgvector` for retrieval-augmented generation.

- `store_decision(context, decision, trade_id)`: embed context → insert to `DecisionEmbedding` table
- `retrieve_similar(context, n=5)`: query top-5 most similar past decisions by cosine similarity, weighted by quality score
- `update_quality(trade_id, realized_pnl)`: after position closes, update quality score (positive PnL → higher weight, negative → lower)
- `format_rag_context(memories)`: format retrieved memories for injection into LLM prompt

Embeddings: OpenAI `text-embedding-3-small` (or SHA-512 hash fallback if no OpenAI key).

**Status:** RAG store/retrieve built but **not called by the agent before decisions.** Not wired in.

---

### 3.11 Copy Trading

#### `src/copy_trading/mirror.py`
- `get_followers(leader_user_id)`: fetch all active `CopyRelationship` records for leader
- `mirror_trade(leader_trade, leader_equity)`: for each follower, fetch their balance + configured venue credentials → scale allocation proportionally → execute same trade
- Symbol mapping via `symbol_map.py` for cross-venue compatibility

**Status:** Logic is complete but **not called from the live trading loop** and **not wired to the UI copy-trading page**.

---

### 3.12 Observability

#### `src/observability/setup.py`
- `init_sentry()`: Sentry SDK with performance tracing + profiling
- `init_structlog()`: structured JSON logs (field: venue, asset, action, latency, error)
- Prometheus metrics:
  - `qunta_tick_duration_seconds`: histogram of time per trading tick
  - `qunta_llm_response_seconds{provider}`: LLM call latency by provider
  - `qunta_order_fill_seconds{venue}`: order execution latency by venue
  - `qunta_websocket_clients`: gauge of connected WS clients
  - `qunta_agent_running`: 0/1 binary flag

Prometheus HTTP server at `:9090/metrics` (configurable via `PROMETHEUS_PORT`).

---

## 4. Database Schema

Full Prisma schema at `ui/prisma/schema.prisma`.

```
User
  id, clerkId (unique), email, name
  plan: FREE | STARTER | PRO | ENTERPRISE
  stripeCustomerId, planExpiresAt
  → venues[], settings, agentRun, equityPoints[], tradeLogs[], auditLogs[], copyRelationship[]

Venue
  id, userId, name
  type: HYPERLIQUID | BINANCE | OANDA | CCXT | METATRADER | BYBIT | OKX | KRAKEN | COINBASE | ALPACA | IBKR
  apiKey (AES-256 encrypted), apiSecret (encrypted), apiPassphrase (encrypted)
  accountId, ccxtExchangeId, metaApiToken, metaApiAccountId
  webhookSecret, isPaper, isActive
  → riskProfile

RiskProfile
  venueId (unique), maxPositionPct, maxLeverage, mandatorySlPct
  maxLossPerPositionPct, dailyLossCircuitBreaker
  maxTotalExposurePct, maxConcurrentPositions

UserSettings
  userId (unique), telegramToken, telegramChatId
  emailNotifications, timezone

AgentRun
  userId (unique), isRunning, startedAt

EquityPoint
  agentId, timestamp, equity, balance, unrealizedPnl

TradeLog
  userId, timestamp, asset, action, entryPrice, exitPrice
  quantity, pnl, fee, venue, orderId, rationale

StrategyListing
  userId, name, description, assetClasses[], winRate, sharpe
  maxDrawdown, isPublic

AuditLog
  userId, timestamp, action, details (JSON), ipAddress

CopyRelationship
  leaderId, followerId, allocPct, maxAllocPct, isActive, symbolMap (JSON)

DecisionEmbedding
  userId, tradeId, contextHash, embedding (pgvector), qualityScore
  createdAt, decision (JSON)
```

---

## 5. Frontend — Deep Dive

### 5.1 Authentication Flow
1. User lands on `/` → clicks "Sign In"
2. Clerk handles auth → issues JWT
3. `middleware.ts` validates Clerk session on all `/(protected)/*` routes
4. `lib/auth.ts` fetches `User` from DB via `clerkId` (60s LRU cache)
5. Clerk webhook at `/api/webhooks/clerk` syncs `user.created`, `user.updated`, `user.deleted` → DB

### 5.2 Key API Routes

#### `/api/venues` — Venue Management
- `GET`: list user venues (apiKey/apiSecret masked as `****`)
- `POST`: create venue — validates plan limits (FREE: 1, STARTER: 2, PRO: unlimited), encrypts credentials with `AES-256-GCM`, creates default `RiskProfile`
- `/[id]/test`: POST → call Python `/api/venues/test` → validate real API connection

#### `/api/agent/[...path]` — Agent Proxy
- Validates user plan (FREE → paper only)
- Applies rate limits: 20 starts/hour, 5 killswitches/5min
- Proxies to Python FastAPI: `start`, `stop`, `killswitch`

#### `/api/equity` — Equity Curve
- `GET`: fetch `EquityPoint[]` for current user's agent
- `POST`: insert new point (called by Python agent after each tick)

#### `/api/trades` — Trade Journal
- `GET`: fetch `TradeLog[]` with optional date/asset filters, CSV export support
- `POST`: insert new trade log entry

#### `/api/webhooks/tradingview` — External Signals
- Validates HMAC-SHA256 signature from `TRADINGVIEW_WEBHOOK_SECRET`
- Executes trade based on alert payload: `{symbol, action, size, sl, tp}`

### 5.3 Key Components

#### `TradingChart.tsx`
- TradingView `lightweight-charts` v5 candlestick chart
- **Bug:** Hardcoded to Binance WebSocket price stream regardless of selected venue
- Overlays: active position entry lines, TP/SL price levels
- Time range selector: 1m, 5m, 15m, 1h, 4h, 1d

#### `EquityChart.tsx`
- recharts v3 `AreaChart` of equity over time
- Fetches from `/api/equity`, re-fetches on WebSocket events

#### `DecisionsFeed.tsx`
- Stream of recent LLM decisions: asset badge, action badge, confidence meter, rationale text
- **Gap:** Does not show which LLM made the decision (important when council mode is active)

#### `StatusBar.tsx`
- Top navigation: venue name, model name, agent uptime, tick count
- **Bug:** Venue name hardcoded to "binance" — not reading from actual active venue

#### `MarketPicker.tsx`
- Asset selector dropdown
- **Bug:** Options hardcoded to `["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]` — should be dynamic from selected venue

#### `NLCommandBar.tsx`
- Text input: "Buy 50% BTC at limit 65000 SL 63000"
- Calls `/api/agent/command` → `nl_parser.py` → execute

#### `MacroIntelStrip.tsx`
- Fear & Greed index pill, correlation matrix table, economic event countdown
- Fetches from `/api/intel/macro` (Python backend endpoint)

### 5.4 Hooks

#### `useWebSocket.ts`
```typescript
// Connects to: ws://localhost:8000/ws?token=<clerk_jwt>
// Messages: { type: "price" | "position" | "decision" | "status", data: {...} }
// Auto-reconnects on close with 3s delay
```

### 5.5 Plan Tier Feature Matrix (`lib/plan-limits.ts`)

| Feature | FREE | STARTER | PRO | ENTERPRISE |
|---------|------|---------|-----|------------|
| Live trading | ✗ | ✓ | ✓ | ✓ |
| Max venues | 1 | 2 | Unlimited | Unlimited |
| Max concurrent assets | 1 | 2 | 5 | Unlimited |
| Council mode | ✗ | ✗ | ✓ | ✓ |
| RAG memory | ✗ | ✗ | ✓ | ✓ |
| Copy trading | ✗ | ✗ | ✓ | ✓ |
| Strategy marketplace | ✗ | ✓ | ✓ | ✓ |
| Custom risk rules | ✗ | ✗ | ✓ | ✓ |
| Backtesting | ✓ | ✓ | ✓ | ✓ |
| Telegram alerts | ✗ | ✓ | ✓ | ✓ |
| Webhook (TradingView) | ✗ | ✗ | ✓ | ✓ |
| API access | ✗ | ✗ | ✗ | ✓ |

---

## 6. Data Flows

### 6.1 Agent Tick Loop (end-to-end)
```
[User: Start Agent] 
  → POST /api/agent/start (Next.js)
  → Plan check + rate limit
  → Proxy → Python /api/agent/start
  → Decrypt venue credentials from DB
  → Instantiate Venue adapter
  → Start async tick loop

[Every N seconds:]
  → Venue.get_balances() + get_positions() + get_candles()
  → local_indicators.compute_all(candles)
  → rag.retrieve_similar(context) [when wired]
  → TradingAgent.decide(context) → LLM call
  → RiskManager.validate_trade(decision)
  → Venue.place_order() [if approved]
  → Write diary.jsonl + decisions.jsonl
  → POST /api/equity (equity point)
  → POST /api/trades (trade log)
  → WebSocket broadcast → Frontend updates
  → copy_trading.mirror_trade() [when wired]
  → rag.store_decision() [when wired]
  → alerts.notify() [when wired]
```

### 6.2 Venue Setup
```
User fills Settings form
  → POST /api/venues (Next.js)
  → Validate plan limits
  → AES-256-GCM encrypt (apiKey, apiSecret)
  → Prisma insert Venue + RiskProfile
  → Optional: POST /api/venues/[id]/test → Python venue.get_balances()
```

### 6.3 Backtest Flow
```
User selects: venue, symbol, timeframe, initial_capital, days
  → POST /api/backtest/run (Next.js)
  → Proxy → Python /api/backtest/run
  → data_loader.fetch_candles() (disk-cached)
  → BacktestEngine.run(strategy, MockVenue)
  → compute_all(candles) per bar
  → decision_fn(context) → trade
  → MockVenue.execute() → mark-to-market
  → report.compute_metrics()
  → Return: equity_curve[], metrics{}
  → Frontend: recharts equity + metric cards
```

### 6.4 Copy Trading Flow (intended, not fully wired)
```
Leader agent executes trade on venue A
  → copy_trading.get_followers(leader_user_id)
  → For each follower:
      → Fetch follower's balance + venue credentials
      → Scale: alloc = leader_alloc / leader_equity * follower_equity * follower_maxAllocPct
      → symbol_map.map_symbol(asset, from_venue=A, to_venue=follower_venue)
      → RiskManager.validate_trade(scaled_trade)
      → follower_venue.place_order(scaled_trade)
      → Log to follower's TradeLog
```

---

## 7. Environment Variables Reference

Key groups (see `.env.example` for full list):

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/db

# Encryption (same key in Python + Next.js)
ENCRYPTION_KEY=<32-byte hex>

# LLMs
LLM_PROVIDER=anthropic  # anthropic | groq | gemini | ollama | openrouter
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...
GOOGLE_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434
OPENROUTER_API_KEY=sk-or-...

# Feature Flags
ENABLE_TOOL_CALLING=true
ENABLE_THINKING=false
ENABLE_COUNCIL=false
ENABLE_RAG=false
ENABLE_COPY_TRADING=false
ENABLE_MTF=false
ENABLE_CALENDAR=false

# Exchange Credentials
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_MARKET=futures  # spot | futures
BINANCE_SANDBOX=false

OANDA_ACCOUNT_ID=...
OANDA_ACCESS_TOKEN=...
OANDA_PRACTICE=true

META_API_TOKEN=...
META_API_ACCOUNT_ID=...
MT_IS_PAPER=true

ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALPACA_PAPER=true

# Risk Defaults
MAX_POSITION_PCT=0.03
MAX_TOTAL_EXPOSURE_PCT=0.20
MAX_LEVERAGE=2.0
DAILY_LOSS_CIRCUIT_BREAKER=0.04
MAX_CONCURRENT_POSITIONS=5
BALANCE_RESERVE_PCT=0.30
MANDATORY_SL_PCT=0.025
MAX_LOSS_PER_POSITION=0.08

# Alerts
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Observability
SENTRY_DSN=...
PROMETHEUS_PORT=9090
LOG_LEVEL=INFO

# Auth (Next.js)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_...
CLERK_SECRET_KEY=sk_...
CLERK_WEBHOOK_SECRET=...

# Payments (Next.js)
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Python backend URL (Next.js)
PYTHON_API_URL=http://localhost:8000
```

---

## 8. Known Bugs & Critical Gaps

These are documented, confirmed issues. Any agent working on this codebase should be aware of them.

### 🔴 Critical (blocking features)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| 1 | **TradingChart hardcoded to Binance WebSocket** | `ui/components/TradingChart.tsx` | Chart shows wrong data if venue ≠ Binance |
| 2 | **StatusBar.venue hardcoded to "binance"** | `ui/components/StatusBar.tsx` | Always shows wrong venue |
| 3 | **MarketPicker hardcoded to 6 Binance symbols** | `ui/components/MarketPicker.tsx` | Can't pick non-Binance assets |
| 4 | **Telegram notifier not instantiated in live loop** | `src/main.py`, `src/server.py` | Alerts never fire |
| 5 | **EquityPoint never populated by agent** | `src/main.py`, `src/server.py` | Equity chart always empty |
| 6 | **TradeLog never populated by agent** | `src/main.py`, `src/server.py` | Journal always empty |
| 7 | **AuditLog never populated** | Multiple | Compliance audit trail empty |
| 8 | **Copy trading not called from live loop** | `src/server.py` | Copy trading doesn't work |
| 9 | **RAG retrieve not called before decisions** | `src/agent/decision_maker.py` | LLM never sees past memories |
| 10 | **Council mode never instantiated** | `src/server.py` | Multi-LLM voting unused |
| 11 | **Economic calendar not checked before decisions** | `src/agent/decision_maker.py` | Agent trades through high-impact events |

### 🟡 High Priority

| # | Issue | Impact |
|---|-------|--------|
| 12 | Agent persistence (`AgentRun`) not integrated — restarts lose state | Agent looks dead after restart |
| 13 | DecisionsFeed doesn't show which LLM made decision | Council mode unverifiable |
| 14 | No pre-trade preview / confirmation modal | Users can't review before execution |
| 15 | Onboarding doesn't guide venue setup | New users lost |
| 16 | No connection health indicator per venue | Can't tell if exchange is reachable |
| 17 | Mobile app is 95% stub | No mobile access |
| 18 | Marketplace strategy detail page exists but no subscribe flow | Can't actually copy a strategy |
| 19 | Landing page pricing cards have dead Stripe links | Can't upgrade from landing page |

### 🟢 Medium / Low Priority

| # | Issue |
|---|-------|
| 20 | No order book heatmap / depth visualization |
| 21 | No smart routing (VWAP/TWAP splitting) |
| 22 | No Prometheus/Grafana dashboard link in UI |
| 23 | No rate-limit feedback in UI (shows silent failure) |
| 24 | No dark/light toggle |
| 25 | Kill-switch doesn't write AuditLog entry |
| 26 | No re-auth on Clerk token expiry over WS |

---

## 9. Deployment

### Docker
```bash
docker build -t quntatradeai .
docker run -d \
  --env-file .env \
  -p 8000:8000 \
  -p 9090:9090 \
  quntatradeai
```
- Multi-stage: builder (Poetry install) → runtime (minimal python:3.12-slim)
- Runs as non-root user `qunta` (uid 1001)
- Health check: `curl http://localhost:${API_PORT}/api/status`
- Entrypoint: `python src/server.py`

### Database Setup
```bash
cd ui
npx prisma migrate deploy   # apply all migrations
npx prisma db push          # or push schema directly (dev)
```
- Requires PostgreSQL + `pgvector` extension for RAG
- `DATABASE_URL` shared between Python backend and Next.js

### Development
```bash
# Python backend
poetry install
poetry run python src/server.py

# Frontend
cd ui
pnpm install
pnpm dev   # http://localhost:3000

# Both in parallel
# (use tmux / two terminals)
```

---

## 10. Vision — Where QuntaTradeAI Should Go

This section defines the product we are building toward. Every addition, fix, or agent decision should be measured against this vision.

### 10.1 Core Vision Statement

**QuntaTradeAI becomes the Bloomberg Terminal of AI trading agents** — an institutional-grade, fully autonomous trading platform accessible to everyone from a sophisticated retail trader to a hedge fund. It is the only platform where you can deploy multiple AI models in a voting council, trade across 15+ venues simultaneously, let the system learn from every trade via semantic memory, and have your copy followers mirror your signals in real-time — all behind a single, beautiful dashboard.

---

### 10.2 Agent Intelligence Upgrades

**Multi-LLM Council (Priority: HIGH)**
- Wire `council.py` into the live loop for PRO+ plans
- Claude + Groq + Gemini each decide independently
- 2/3 majority required to execute a trade
- UI shows each LLM's vote + rationale per decision
- Enables: reduces single-model hallucination risk, gives users a "confidence score"

**Smarter Context Injection**
- RAG must be wired: before every decision, retrieve top-5 similar past trades and inject into prompt
- MTF confluence must gate decisions: agent can only enter if 2/3 timeframes agree
- Economic calendar must pause agent: auto-HOLD within 5 min of NFP, CPI, FOMC, BoE
- News sentiment must modulate position sizing

**Reinforcement Learning from Trade Outcomes**
- After each position closes, score the decision quality (realized PnL, max drawdown during hold, slippage)
- Feed score back into prompt ("Your last 10 similar setups had 70% win rate, avg +2.3R")
- Use pgvector quality weights so high-quality memories surface first

**Autonomous Strategy Discovery**
- Backtesting engine runs weekly sweeps across parameter space (RSI thresholds, EMA periods, timeframes)
- Publishes best-performing strategies to marketplace automatically
- Agent auto-adopts the current best strategy per asset class

---

### 10.3 Venue & Execution Upgrades

**Full Multi-Venue Wiring in UI**
- Settings page lets user add/test/remove any of the 14 supported venues
- Dashboard venue picker shows user's actual configured venues
- MarketPicker dynamically loads symbols from selected venue (not hardcoded)
- TradingChart connects to correct WebSocket per venue

**New Venues to Add**
| Priority | Venue | Asset Class |
|----------|-------|-------------|
| HIGH | dYdX v4 | Crypto perps |
| HIGH | GMX | Crypto perps (DEX) |
| HIGH | Aevo | Crypto options |
| MEDIUM | Synthetix | Synthetic assets |
| MEDIUM | Drift Protocol | Solana perps |
| MEDIUM | Bybit (dedicated) | Crypto perps/spot |
| MEDIUM | Phemex | Crypto perps |
| MEDIUM | Gate.io | Crypto spot |
| MEDIUM | Bitget | Crypto perps |
| LOW | Interactive Brokers (expand) | Full equities/options |
| LOW | TD Ameritrade/Schwab | US stocks |
| LOW | FTX-successor platforms | Crypto |
| LOW | CME via broker | Futures |

**Smart Order Routing**
- VWAP/TWAP splitting for large orders (>$10k) to minimize slippage
- Detect best execution venue across connected exchanges by live orderbook comparison
- Auto-route: "execute on whichever venue has tightest spread for BTC right now"

**Order Book Heatmap**
- Show bid/ask walls, detect support/resistance from order book depth
- MEV protection: delay execution by 1–3 blocks on-chain venues to avoid front-running

---

### 10.4 UI/UX Upgrades

**Dashboard Overhaul**
- Venue-agnostic: all data flows from selected active venue, not hardcoded Binance
- Real-time P&L ticker in StatusBar (not just stored equity points)
- Per-position P&L % + liquidation distance meter
- One-click position close from dashboard (not just killswitch all)
- Pre-trade confirmation modal: "Agent wants to buy 500 USDT of ETH at market. Approve?"

**Mobile App (Priority: HIGH)**
- Complete the Expo app with all dashboard screens
- Push notifications for trade events via Expo Push Notifications
- Biometric auth for order approval
- Portfolio overview, P&L, journal, settings screens
- Minimum viable: mirror the web dashboard fully on mobile

**Enhanced DecisionsFeed**
- Show per-LLM opinion card when council mode is active
- Expandable: click decision → full reasoning trace + indicator values at time of decision
- Filter by: asset, action type, confidence level

**Strategy Marketplace (Priority: HIGH)**
- Full publish/subscribe flow (currently missing backend)
- Strategy cards: name, author, backtest stats (Sharpe, max drawdown, win rate, return %)
- One-click copy: subscribe to a strategy → your agent adopts it
- Strategy versioning + changelog
- Revenue share: strategy authors earn % of subscriber fees

**Copy Trading UI (Priority: MEDIUM)**
- Leader leaderboard: ranked by risk-adjusted return (Sharpe ratio)
- Follower dashboard: shows leader's open positions, drawdown, history
- Per-follower allocation control: "copy at 25% of your account"
- Real-time mirror status: "BTC trade mirrored to 3 of 5 followers ✓"

---

### 10.5 Risk & Compliance Upgrades

**Institutional Risk Dashboard**
- Full risk decomposition: portfolio beta, delta, VaR at 95%/99%, Sharpe, Sortino, Calmar
- Drawdown waterfall chart (not just max drawdown number)
- Correlation heatmap: live matrix of all open positions
- Position-level risk contribution

**Regulatory & Compliance**
- Full AuditLog: every agent action, every order, every override logged with timestamp + IP
- Trade blotter export: CSV + PDF report for tax filing
- Position reporting: monthly/quarterly PDF report (total trades, realized P&L, fees, taxes)
- Kill-switch audit entry: every emergency stop logged with reason

**Adaptive Risk**
- Volatility regime detection: switch to conservative sizing in high-VIX / high crypto fear periods
- Drawdown-aware: reduce position size by 50% after -2% daily drawdown (warn before circuit breaker)
- Correlation-aware: reduce new positions if portfolio correlation exceeds threshold

---

### 10.6 Intelligence & Research

**Economic Research Layer**
- Full economic calendar page with event countdown + historical impact analysis
- Post-event analysis: "BTC dropped 3.2% in the 30 min after last CPI surprise"
- Agent brief before each session: macro conditions, upcoming events, current sentiment

**News & Sentiment**
- Real-time news feed per asset (CryptoCompare + NewsAPI + Twitter/X API)
- Sentiment score injected into LLM context
- Alert on unusual sentiment spike (potential pump/dump detection)

**On-Chain Analytics (Crypto)**
- Whale wallet monitoring (large wallet movements)
- Exchange inflow/outflow (supply pressure signal)
- Funding rate anomaly detection
- Open interest analysis

---

### 10.7 Infrastructure & Scale

**Multi-User Architecture**
- Each user's agent runs in isolation (no shared state)
- Per-user agent containers (k8s deployment, one pod per active agent)
- Horizontal scaling: queue agent ticks via Redis to prevent LLM rate limit collisions

**Database Improvements**
- Proper pgvector index (IVFFlat or HNSW) for RAG at scale
- Time-series optimizations for `EquityPoint` (TimescaleDB or partitioned table)
- DB connection pooling via PgBouncer

**WebSocket at Scale**
- Move from direct Python WS to a dedicated WebSocket service (Pusher / Soketi / Ably)
- Reduces Python server load, enables horizontal scaling

**CI/CD**
- GitHub Actions: lint + test on every PR
- Docker build + push to registry on merge to main
- Auto-deploy to staging, manual promote to production
- Lighthouse score + bundle size checks on frontend

---

### 10.8 Monetization

**Tier Pricing (Target)**
| Plan | Price | Key Features |
|------|-------|-------------|
| FREE | $0 | 1 venue, paper trading, backtesting, 1 asset |
| STARTER | $29/mo | 2 venues, live trading, 2 assets, Telegram alerts |
| PRO | $99/mo | Unlimited venues, council, RAG, copy trading, TradingView webhooks |
| ENTERPRISE | $499/mo | White-label, API access, dedicated support, unlimited followers |

**Additional Revenue**
- Strategy marketplace: 20% revenue share on subscriber fees
- Copy trading: 1% AUM fee per month on follower allocations (paid to leaders, Qunta takes 15%)
- White-label: sell the platform to hedge funds / brokers under their brand

---

### 10.9 Immediate Next Steps (Priority Order)

These are the highest-impact things to fix/build first, in order:

1. **Wire EquityPoint + TradeLog into live loop** — foundational, everything else depends on data
2. **Fix StatusBar + MarketPicker + TradingChart venue hardcoding** — makes the app actually work for non-Binance users
3. **Instantiate Telegram notifier in live loop** — users need to know what the agent is doing
4. **Wire RAG store + retrieve into agent tick** — enables learning from history
5. **Wire council.py into server.py for PRO plans** — key differentiator
6. **Wire copy_trading.mirror_trade() into live loop** — copy trading is a major feature
7. **Wire economic_calendar into decision_maker** — prevents trading into volatility events
8. **Complete mobile app (Expo)** — high demand from users
9. **Full strategy marketplace (publish + subscribe)** — creates network effects
10. **Adaptive risk + VaR in RiskPanel** — institutional credibility
11. **Proper CI/CD pipeline** — needed before scaling users
12. **New venues: dYdX, GMX, Aevo** — expand addressable market

---

## 11. Testing

Tests live in `tests/`. Run with: `poetry run pytest tests/ -v`

| File | Coverage |
|------|---------|
| `test_risk_manager.py` | RiskManager: position size, leverage, drawdown, concurrent, reserve |
| `test_indicators.py` | Known OHLCV → verify RSI/EMA/MACD/BBands outputs |
| `test_server_integration.py` | FastAPI: status, account, positions endpoints |

**Gaps in test coverage:**
- No tests for venue adapters (require live API or mock)
- No tests for backtesting engine
- No tests for copy trading mirror logic
- No tests for RAG store/retrieve
- No frontend tests (Playwright/Vitest)

---

## 12. Security Model

- **Credentials encrypted at rest:** AES-256-GCM, same key in Python + Next.js. Keys never returned to client.
- **WS auth:** Clerk JWT validated against Clerk JWKS endpoint per connection
- **API auth:** All Next.js routes check Clerk session. Python routes check token passed from Next.js.
- **TradingView webhooks:** HMAC-SHA256 signature validation
- **Clerk webhooks:** Svix signature validation
- **Stripe webhooks:** Stripe signature validation
- **Rate limiting:** Agent start (20/hour), killswitch (5/5min) — in-memory (should migrate to Redis for multi-instance)
- **Plan enforcement:** Checked on every agent start, every venue create
- **SQL injection:** Prisma ORM parameterized queries throughout
- **Secrets in env:** Never committed, all in `.env` (gitignored)

---

*This document represents the full state of QuntaTradeAI as of May 2026. The codebase is feature-rich but has critical wiring gaps between built modules and the live trading loop. The foundation is solid — the work ahead is integration, not invention.*
