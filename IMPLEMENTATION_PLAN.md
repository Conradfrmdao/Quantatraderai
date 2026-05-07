# QuantatraderAI — Implementation Plan

> Full implementation of `quantatrader_godmode_warroom.html`.
> **Payments/Stripe is the LAST phase** as requested.
> Phases are ordered by dependency + risk (close known holes first, then compound).

---

## How this executes

Each phase produces **testable output** before moving to the next. After each phase:
1. I stop.
2. You test (or I run smoke tests).
3. You give go-ahead for the next phase.

If a phase is too large for one sitting, I'll split it and checkpoint mid-way.

**Phases 1–3** are things the app already half-has — we finish the wiring. Real value, low risk.
**Phases 4–6** are intelligence + platform moat (the compounding stuff).
**Phases 7–9** are institutional-grade ops.
**Phase 10** is payments + mobile (last, per your instruction).

---

## Phase 0 — Prep (before any code)

**Goal:** Make sure we can run tests, have credentials slots, and the pieces we're touching still work.

- Run `poetry install` and `cd ui && pnpm install` — confirm clean state
- Create `tests/` scaffold in Python + `pytest` config in [pyproject.toml](pyproject.toml)
- Add `.env.example` additions for all new env vars we'll introduce across phases
- Create `scripts/smoke.sh` that runs backend + frontend build + a dry tick — our regression canary

**Deliverable:** CI-able test scaffold, no behaviour change.

---

## Phase 1 — Close the 4 critical gaps + architecture debt (War room W1)

**Goal:** Stop the bleeding. Every critical/high item from the architecture tab + the 4 missing features.

### 1.1 Wire the Telegram notifier into live events
- [src/alerts/notifier.py](src/alerts/notifier.py) already has `TelegramBackend`. Instantiate it in [src/main.py](src/main.py) + [src/server.py](src/server.py) at agent boot.
- Add event hooks at:
  - Trade opened → `trade_opened` event after `Venue.place_order()` success
  - Stop-loss triggered → `stop_loss_hit` in reconcile loop
  - Risk block → `circuit_breaker_tripped` when `RiskManager.validate_trade()` rejects
  - Agent crash → wrap main loop in try/except, emit `decision_error` on exception
- Read `telegramToken`/`telegramChatId` from `UserSettings` (Supabase) per running agent, not global env.

### 1.2 JWT auth on WebSocket handshake
- [src/server.py](src/server.py) `/ws` currently accepts any client. Add Clerk JWT validation on upgrade.
- Frontend [ui/hooks/useWebSocket.ts](ui/hooks/useWebSocket.ts) → send Clerk session token as `?token=` query param.
- Backend: verify JWT using Clerk's JWKS endpoint; reject handshake if invalid/expired.

### 1.3 Agent persistence on server restart
- Add `AgentState` table to [ui/prisma/schema.prisma](ui/prisma/schema.prisma): `userId`, `venueId`, `assets`, `interval`, `isRunning`, `startedAt`.
- On `POST /api/agent/start` → set `isRunning=true`.
- On Python server boot ([src/server.py](src/server.py)) → query `AgentState WHERE isRunning=true` → auto-resume each one.
- On clean shutdown → `isRunning=false`.
- If Python crashes, record stays `isRunning=true` → next boot resumes (self-healing).

### 1.4 Dead man's switch
- New `src/safety/deadmans_switch.py`. Tracks last tick timestamp per agent.
- Background task: if `now - last_tick > 30min`, close all positions via `Venue.close_position()` for each open, emit `circuit_breaker_tripped`, set `AgentState.isRunning=false`.

### 1.5 Fix psycopg2 → asyncpg
- Replace `psycopg2-binary` with `asyncpg` in [pyproject.toml](pyproject.toml).
- [src/services/supabase_reader.py](src/services/supabase_reader.py) → async `asyncpg.connect()`, async queries.
- Any other blocking DB call gets the same treatment.

### 1.6 Binance WebSocket reconnect
- [src/server.py](src/server.py) Binance kline WS → wrap in reconnect loop with exponential backoff (1s → 2s → 4s → 8s → 16s, cap 5 retries).
- On final failure emit `decision_error` via notifier.

### 1.7 Cap decisions buffer
- In-memory `decisions` list in [src/server.py](src/server.py) → hard cap 100 entries (`collections.deque(maxlen=100)`).
- On every decision, also persist to new Supabase `Decision` table for history.

### 1.8 pytest scaffold (war room arch row #6)
- `tests/test_risk_manager.py` — edge cases for each check (oversize, over-leverage, circuit breaker, reserve, concurrent limit).
- `tests/test_indicators.py` — known OHLCV fixture → known RSI/EMA/MACD/BBands values.
- `tests/test_venue_mocks.py` — each `Venue` adapter's interface respected via `MockVenue`.

**Deliverable:** 0 critical gaps remain. WS auth'd. Agent survives restart. Tests run green.

---

## Phase 2 — MetaTrader + new venues (War room W2)

**Goal:** 9M+ MT4/MT5 users unlocked. Existing CCXT venues surfaced in UI. Economic calendar integration.

### 2.1 MetaTraderVenue adapter
- `src/venues/forex/metatrader.py` — implements `Venue` ABC using `metaapi-cloud-sdk`.
- Maps MetaAPI positions/orders/accounts to our `Balance`/`Position`/`Order`/`Candle` models.
- Timeframe mapping: `1m → 1M`, `5m → 5M`, `15m → 15M`, `1h → 1H`, `4h → 4H`, `1d → 1D`.
- Paper mode short-circuits order placement.

### 2.2 Venue registry + Prisma enum
- Register `"metatrader"` (and alias `"mt4"`, `"mt5"`) in [src/venues/registry.py](src/venues/registry.py).
- Add `METATRADER` to `VenueType` in [ui/prisma/schema.prisma](ui/prisma/schema.prisma); migrate.
- Add `metaApiToken`, `metaApiAccountId` fields to `Venue` model.

### 2.3 Settings UI — MetaTrader fields
- [ui/app/(protected)/settings/page.tsx](ui/app/(protected)/settings/page.tsx) venue form: conditional fields when `type === "METATRADER"` (token + account ID).
- `/api/venues` route handler: encrypt both + validate.

### 2.4 Expose Bybit / OKX / Kraken / Coinbase Advanced
- Already supported via `CCXT`. Just add them as first-class venue types in the Prisma enum + venue-form dropdown so users don't have to select "CCXT" then pick exchange.
- Simpler UX: "Choose your exchange" → list 10+ direct options that all route to the CCXT adapter under the hood.

### 2.5 Economic calendar — TwelveData
- `src/intel/economic_calendar.py` — fetch next 24h events, filter to "high impact" (NFP, CPI, FOMC, ECB, BoE, payrolls).
- Pre-decision hook in `TradingAgent._decide()`: if within 5min of a high-impact event, return `hold` for all assets with rationale "economic calendar pause".
- Dashboard badge: upcoming event countdown in `StatusBar`.

### 2.6 Fear/greed index — Alternative.me
- `src/intel/sentiment.py` — fetches crypto F&G daily (free, no auth).
- Injected into LLM context payload as `macro_sentiment.crypto_fear_greed`.

**Deliverable:** MetaTrader live (paper), 10+ exchanges in settings dropdown, econ calendar pauses agent, F&G in prompts.

---

## Phase 3 — TradingView webhooks + backtesting UI (War room W3)

**Goal:** Every retail trader already knows TradingView → instant execution. Users can validate strategies before risking money.

### 3.1 TradingView webhook endpoint
- `ui/app/api/webhooks/tradingview/route.ts` — accepts POST with HMAC-SHA256 signed payload.
- Signature validated against user's per-venue webhook secret (stored in `Venue.webhookSecret`, encrypted).
- Body: `{ action: "buy"|"sell"|"close", symbol, size, sl?, tp?, venueId }` — forwarded to Python `POST /api/agent/execute-signal`.
- Python validates through same `RiskManager.validate_trade()` pipeline — TV signals are not trusted, they get the same guardrails.

### 3.2 Backtesting UI page
- `ui/app/(protected)/backtest/page.tsx` — date range picker, venue/symbol selector, timeframe, initial capital, strategy selector (default RSI, custom, LLM-driven).
- Kicks off `POST /api/agent/backtest` → proxies to Python `/api/backtest/run`.
- Runs [src/backtesting/engine.py](src/backtesting/engine.py) with user inputs, returns results JSON.

### 3.3 Backtest metrics + visualisation
- Recharts equity curve + drawdown underlay.
- Metrics cards: total return %, max DD %, win rate, Sharpe, **Calmar** (return / max DD), trade count.
- Trade list below chart with entry/exit/PnL per round-trip.

### 3.4 Trade journal page
- `ui/app/(protected)/journal/page.tsx` — reads from Supabase `TradeLog` table (populated from `diary.jsonl` on each close).
- Filter by date / venue / asset / action. CSV export (for CPA / tax prep).

### 3.5 Equity curve persistence
- New Supabase `EquityPoint` table: `agentId`, `timestamp`, `equity`, `balance`, `unrealizedPnl`.
- Python appends every tick. Dashboard `EquityChart` reads last 1000 points from DB (not in-memory) → survives restart.

**Deliverable:** TV alerts execute trades (risk-gated). Users can backtest any strategy. Trade history persists + exports.

---

## Phase 4 — AI council + RAG memory (War room W4)

**Goal:** The real moat. Multi-LLM consensus + memory that learns.

### 4.1 Parallel LLM council
- `src/agent/council.py` — fires Groq + Claude + Gemini in parallel via `asyncio.gather()`.
- Each returns a `LLMDecision` (action, confidence, rationale).
- Vote aggregator: **2/3 must agree on action** (buy/sell/hold). Otherwise → `hold` with reason "council deadlock".
- Position sizing: median of the 3 `allocation_usd` values from agreeing providers.

### 4.2 All opinions in decisions feed
- Extend `Decision` schema: `groqOpinion`, `claudeOpinion`, `geminiOpinion`, `councilVote`, `agreement` (0–1).
- Frontend `DecisionsFeed` shows 3 mini-cards per decision with per-provider rationale + confidence bar.

### 4.3 pgvector setup
- Enable `pgvector` extension in Supabase (migration in [ui/prisma/](ui/prisma/)).
- New `DecisionEmbedding` table: `decisionId`, `embedding vector(1536)`, `pnl`, `qualityScore`.

### 4.4 RAG retrieval
- `src/memory/rag.py` — on each tick:
  1. Embed current context (market + indicators + open positions) using OpenAI `text-embedding-3-small` (cheap) or local `sentence-transformers` fallback.
  2. Query pgvector: `SELECT * ORDER BY embedding <=> $1 LIMIT 5` — weighted by recency + quality score.
  3. Inject summaries of those 5 past decisions + outcomes into LLM context.

### 4.5 Reinforcement signal
- On trade close, compute realized PnL. Update `qualityScore` on the embedding:
  - Positive PnL → quality ↑
  - Negative PnL → quality ↓
- Retrieval re-ranks by recency × quality, so the agent drifts toward past decisions that actually made money.

**Deliverable:** 3-LLM consensus gates every trade. Agent references 5 similar past decisions before deciding. Learning loop is closed.

---

## Phase 5 — Intelligence engine (War room W5)

**Goal:** Feeds that make the LLM smarter. All Tier 1 + 2 features.

### 5.1 Multi-timeframe confluence
- `src/indicators/confluence.py` — compute indicators on 1h, 4h, 1d simultaneously.
- Rule: buy signal only if RSI/MACD/EMA all agree across **≥2 of 3 timeframes**.
- Exposed in LLM context as `mtf_confluence.{1h, 4h, 1d}` + `mtf_alignment_score` (0–1).

### 5.2 News sentiment
- `src/intel/news.py` — CryptoCompare news API (or NewsAPI for broader coverage).
- Summarise last 10 headlines per asset using a cheap model (Groq Llama 8B or Gemini Flash).
- Inject `news_sentiment` (-1 to +1) + top-3 headlines into LLM prompt.

### 5.3 Correlation matrix
- `src/intel/correlation.py` — rolling 30-day correlation between all assets the user trades.
- Pre-trade gate: if new position correlation with any existing position > 0.8, reduce allocation by half OR reject.

### 5.4 Funding rate monitor
- [src/trading/hyperliquid_api.py](src/trading/hyperliquid_api.py) already has `get_funding_rate()`. Extend to all perp venues.
- Rule: if funding > +0.1% (highly crowded longs), agent auto-reduces long exposure by 50% OR flips short signal weight.

### 5.5 Glassnode on-chain netflow
- `src/intel/onchain.py` — Glassnode API for exchange netflow (inflows - outflows).
- Large positive inflow → sell pressure signal injected into LLM context.
- Applies only to BTC/ETH/major L1s. Skip for altcoins with no coverage.

**Deliverable:** LLM context now includes MTF confluence, news sentiment, correlation, funding, on-chain flows.

---

## Phase 6 — Execution quality + platform growth (War room W3 tier-3 + W6)

**Goal:** Tier-3 execution + Tier-4 social/platform moat.

### 6.1 Smart order routing (Tier 3)
- `src/execution/smart_router.py` — splits large orders:
  - If notional > 5% of 24h volume → TWAP over 10 minutes.
  - VWAP variant for liquid markets.
  - Iceberg: show only 10% of size at a time on the book.

### 6.2 Order book heatmap
- New dashboard component `ui/components/OrderBookHeatmap.tsx` — subscribe to venue depth feed, render bid/ask levels as intensity-coloured bars.

### 6.3 Natural language commands
- `ui/components/NLCommandBar.tsx` — chat input on dashboard.
- "Buy 5% BTC when RSI < 30" → parse via Claude → creates a `StrategyRule` row that the Python agent evaluates each tick.
- `src/agent/nl_parser.py` — structured JSON extraction from NL input.

### 6.4 Strategy marketplace MVP
- `ui/app/(protected)/marketplace/page.tsx` + `ui/app/(protected)/marketplace/[strategyId]/page.tsx`.
- Users publish their agent config (`StrategyConfig` model) with backtested metrics.
- Subscribe button → copies config to user's own agent.
- Revenue split wiring deferred to Phase 10 (payments).

### 6.5 Public leaderboard
- `ui/app/leaderboard/page.tsx` — anonymised top 100 by Sharpe (verified by platform, reading from `EquityPoint`).
- Users opt in via `UserSettings.publicProfile`.

### 6.6 Interactive Brokers adapter
- `src/venues/stocks/ibkr.py` — wraps `ib_insync` (cleaner than raw `ibapi`).
- Supports stocks, options, futures, FX through one broker.

### 6.7 Alpaca adapter
- `src/venues/stocks/alpaca.py` — `alpaca-py` SDK. US stocks + options. Paper trading by default.

**Deliverable:** Smart order routing live. NL commands work. Marketplace MVP + leaderboard visible. IBKR + Alpaca connected.

---

## Phase 7 — Risk & compliance (War room Tier 5)

**Goal:** Institutional-grade risk. Unlock hedge fund clients.

### 7.1 VaR calculations
- `src/risk/var.py` — Monte Carlo 10k simulations on portfolio returns → 95% / 99% Value at Risk.
- Shown in dashboard Risk panel.

### 7.2 Kill switch + dead man's
- Dead man's already built in Phase 1. Add explicit **kill switch button** in dashboard header — one-click closes all positions immediately.
- Confirmation modal.

### 7.3 Compliance audit trail
- New Supabase `AuditLog` table: append-only, every decision/order/rejection with timestamp, userId, action, data JSON.
- Accessible via `/api/audit` endpoint with Clerk auth.
- Immutable by RLS policy (no DELETE/UPDATE allowed).

**Deliverable:** VaR visible. Kill switch functional. Every action auditable.

---

## Phase 8 — Observability + architecture hardening (War room W8)

**Goal:** 3am crash → you actually know why.

### 8.1 Sentry integration
- Next.js: `@sentry/nextjs`, wrap `ClerkProvider`, capture API route errors.
- Python: `sentry-sdk[fastapi]`, auto-instrument FastAPI + asyncio tasks.

### 8.2 Structured logging
- Python: replace `print`/`rich` with `structlog` JSON output.
- Log levels: DEBUG (prompts), INFO (ticks), WARN (retries), ERROR (crashes).

### 8.3 Prometheus + Grafana
- `src/metrics/prometheus.py` — expose `/metrics`:
  - `tick_duration_seconds` (histogram)
  - `llm_response_duration_seconds{provider}` (histogram)
  - `order_fill_duration_seconds{venue}` (histogram)
  - `websocket_uptime_seconds{stream}` (gauge)
  - `agent_running_total` (gauge)
- Grafana dashboard JSON committed to `ops/grafana/`.

### 8.4 KMS migration
- Replace [ui/lib/encryption.ts](ui/lib/encryption.ts) flat key with AWS KMS (or Supabase Vault if cheaper).
- Per-user DEKs (data encryption keys) wrapped by KMS master key.
- Rotation endpoint: `/api/security/rotate-key` (admin only).

### 8.5 CDN + edge caching
- Next.js: `export const runtime = 'edge'` on read-only API routes (`/api/venues` GET, `/api/user/settings` GET).
- Redis for indicator cache (compute once per symbol/timeframe/minute, serve many agents).

**Deliverable:** Production-grade ops. Know when things break, automated alerts, KMS-backed encryption.

---

## Phase 9 — Copy trading + white-label

**Goal:** Virality + enterprise.

### 9.1 Copy trading
- `src/copy_trading/mirror.py` — for each follower, on each leader trade, auto-place scaled order on follower's venue.
- Follower sets `maxAllocationPct` as safety ceiling.
- Revenue split deferred to Phase 10.

### 9.2 White-label
- Env-driven theming in [ui/app/globals.css](ui/app/globals.css) (custom CSS variable values per tenant).
- Subdomain routing middleware: `tenant1.quantatraderai.com` → loads tenant config from DB.
- Custom logo upload in admin panel.

**Deliverable:** Copy trading works. Enterprise customers get subdomain + branded UI.

---

## Phase 10 — Payments, plans, mobile (LAST — per your instruction)

**Goal:** Monetise. Mobile app for reach.

### 10.1 Stripe integration
- `ui/app/api/webhooks/stripe/route.ts` — verify signature, handle `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`.
- Update `User.plan` in Supabase.

### 10.2 Plan enforcement
- Backend guard middleware on `/api/agent/start`:
  - **Free:** paper only, 1 venue, 1 asset
  - **Starter:** 2 venues, 3 assets
  - **Pro:** unlimited
  - **Enterprise:** unlimited + white-label + API access
- Reject with `402 Payment Required` if over plan limit.

### 10.3 Billing UI
- `ui/app/(protected)/billing/page.tsx` — show current plan, usage, upgrade button → Stripe Checkout session.

### 10.4 Revenue split for marketplace + copy trading
- Stripe Connect for strategy creators. Platform takes 30%.
- Automated payouts monthly.

### 10.5 Tax reporting
- `ui/app/(protected)/tax/page.tsx` — FIFO/LIFO cost basis calculation from `TradeLog`.
- PDF export for year-end (jsPDF or server-rendered).
- IRS Form 8949 CSV format.

### 10.6 React Native mobile app
- New `mobile/` directory. Expo managed workflow.
- Screens: login (Clerk), dashboard (live PnL), start/stop agent, notifications.
- Push via Expo Push Notifications — replicates Telegram alerts.
- App Store + Play Store submission.

**Deliverable:** Revenue live. Plan limits enforced. Mobile app shipped.

---

## Risk & time estimates (honest)

| Phase | Rough hours | Blocks |
|---|---|---|
| 0 — Prep | 2 | — |
| 1 — Critical gaps | 16–24 | Clerk JWKS docs, Supabase migration |
| 2 — MetaTrader + venues | 12–16 | MetaAPI account for testing |
| 3 — TradingView + backtest UI | 12–16 | — |
| 4 — Council + RAG | 16–24 | Claude + Gemini API keys, pgvector enable |
| 5 — Intelligence engine | 16–20 | Glassnode key, NewsAPI key |
| 6 — Execution + platform | 20–28 | IBKR + Alpaca test accounts |
| 7 — Risk & compliance | 8–12 | — |
| 8 — Observability | 12–16 | AWS KMS setup, Grafana host |
| 9 — Copy trading + WL | 12–16 | — |
| 10 — Payments + mobile | 24–40 | Stripe account, App Store cert |
| **Total** | **150–220 hrs** | ~4–6 weeks full-time |

---

## What I need from you per phase

Each phase has dependencies that only you can provide. I'll ask before we start a phase if a key is needed.

- **Phase 1:** Clerk JWT signing key info (JWKS URL), Supabase URL + service role key for migrations
- **Phase 2:** MetaAPI token (free dev tier), TwelveData free key
- **Phase 4:** Claude + Gemini API keys, Supabase plan that allows `pgvector`
- **Phase 5:** Glassnode key (if you want on-chain), NewsAPI/CryptoCompare key
- **Phase 6:** IBKR paper account, Alpaca paper key
- **Phase 8:** AWS account for KMS (or stick with Supabase Vault)
- **Phase 10:** Stripe account in test mode, Apple/Google dev accounts for mobile

---

## Commit strategy

- One branch per phase: `phase-1-critical-gaps`, `phase-2-metatrader`, etc.
- Each phase = one PR with verification steps.
- No force-pushes, no skipped hooks, no `git add .`.
- Tests run green before merge.

---

## Verification per phase

Every phase ends with:
1. **Backend smoke test**: `poetry run python -m src.backtesting.engine --venue <x> --symbol <y> --days 7` — agent still makes decisions.
2. **Frontend smoke test**: `pnpm dev` → dashboard loads → WS connects → live price ticks.
3. **Unit tests**: `pytest tests/ -v` all green.
4. **Manual check**: specific feature of that phase works end-to-end (e.g., Phase 1 = send a test trade, verify Telegram fires).

---

## Ready?

Once you approve this plan, I'll start with **Phase 0 + Phase 1.1 (Telegram wiring)** and checkpoint there. We move forward one phase at a time, and I stop between phases so you can review before we spend more tokens.

If any phase is too ambitious as written, tell me and I'll split it.
