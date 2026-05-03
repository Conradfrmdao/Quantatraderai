# QuntaTradeAI — Complete Product Guide

> **What is QuntaTradeAI?**
> An autonomous AI trading agent that monitors financial markets 24/7, analyses
> live data, makes buy/sell decisions using multiple AI models, and executes trades
> on your connected exchange — all automatically, while you sleep.

---

## Table of Contents

1. [How It Works — The Big Picture](#1-how-it-works)
2. [What Is a Tick?](#2-what-is-a-tick)
3. [The AI Brain](#3-the-ai-brain)
4. [Supported Exchanges (Venues)](#4-supported-exchanges)
5. [Strategy Personas](#5-strategy-personas)
6. [Risk Management](#6-risk-management)
7. [Paper Trading vs Live Trading](#7-paper-vs-live)
8. [The Dashboard — What You See](#8-the-dashboard)
9. [Safety Features](#9-safety-features)
10. [Trust Dashboard](#10-trust-dashboard)
11. [Backtesting & Replay](#11-backtesting)
12. [Plans & Billing](#12-plans-and-billing)
13. [Admin Dashboard](#13-admin-dashboard)
14. [Technical Architecture](#14-technical-architecture)

---

## 1. How It Works

### The simple version

You connect your exchange (e.g. Binance), pick an AI persona and timeframe,
click **Start**, and the agent runs automatically until you stop it.

Every few minutes it wakes up, looks at the market, asks the AI what to do,
checks the decision against your risk rules, and either places a trade or holds.
You watch everything happen in real time on the dashboard.

### The full flow

```
You                          QuntaTradeAI                    Exchange
──────                       ────────────                    ────────
Connect Binance API key  →   Encrypts & stores key (AES-256)
Set persona: Momentum   →   Loads Momentum Hunter risk profile
Set timeframe: 5m       →   Starts the agent loop
Click Start             →   ✓

                             Every 5 minutes:
                             1. Fetch BTC/USDT candles ──────────────→ Binance API
                                                        ←────────────  180 candles returned
                             2. Compute indicators (local, no API)
                                RSI=28 (oversold), MACD=+0.3, EMA crossing
                             3. Send context to AI
                                → "RSI is 28, MACD just crossed positive..."
                             4. AI decides: BUY $150 BTC
                             5. Risk check:
                                • $150 ≤ 3.5% of $10,000 equity ✓
                                • Stop-loss set at -2% ✓
                                • Daily loss not exceeded ✓
                             6. [PAPER] Log fake trade, update balance
                                [LIVE]  Place market order ───────────→ Binance
                                                           ←───────────  Order filled at $67,420
                             7. Send receipt to dashboard
                             8. Sleep 5 minutes, repeat
```

---

## 2. What Is a Tick?

A **tick** is one complete cycle of the agent — one heartbeat.

| Step | What Happens | Time |
|------|-------------|------|
| Wake up | Agent fires on schedule | instant |
| Fetch data | Downloads latest candles from exchange | ~0.3s |
| Compute indicators | RSI, MACD, EMA, ATR, etc. calculated locally | ~0.01s |
| AI decision | Sends context to LLM, waits for response | 0.3–3s |
| Risk validation | Checks every rule before allowing execution | ~0.01s |
| Execute | Places order (or logs paper trade) | ~0.5s |
| Broadcast | Sends update to your dashboard via WebSocket | instant |

**Timeframe = how often a tick fires:**

| Timeframe | Ticks per day | Best for |
|-----------|--------------|----------|
| 1m | 1,440 | Scalping (very active) |
| 5m | 288 | Testing, active monitoring |
| 15m | 96 | Day trading |
| 1h | 24 | Swing trading |
| 4h | 6 | Long-term holds |

Start with **5m** for testing so you see results within minutes.
Switch to **1h** or **4h** for lower activity and lower API costs.

---

## 3. The AI Brain

### How the AI makes decisions

Every tick, the agent builds a "situation report" containing:
- Current account balance and equity
- Open positions and unrealised P&L
- Latest technical indicators (RSI, MACD, EMA, ATR, Bollinger Bands)
- Macro data: fear/greed index, economic calendar events
- Recent trade history (for context)
- Risk limits (so the AI knows its constraints)

This entire context is sent to the LLM which returns a structured JSON decision:
```json
{
  "action": "buy",
  "allocation_usd": 150.00,
  "tp_price": 68900.00,
  "sl_price": 66100.00,
  "rationale": "RSI at 28 signals oversold. MACD bullish crossover confirmed.
                 EMA20 > EMA50 trend intact. Entry on pullback to key support."
}
```

### AI Council (PRO plan)

Instead of one AI making the decision, three run in parallel and vote:
- **Groq** (Llama 3.3 70B) votes
- **Claude** (Anthropic) votes
- **Gemini** (Google) votes

If 2 of 3 agree → execute. If all three disagree → hold (no trade on uncertainty).
This significantly improves decision quality and reduces false signals.

### Supported AI providers

| Provider | Model | Speed | Cost | Notes |
|----------|-------|-------|------|-------|
| **Groq** | Llama 3.3 70B | Very fast (0.3s) | Free | Default primary |
| **Anthropic** | Claude Sonnet | Medium (1–2s) | ~$0.01/tick | Best quality |
| **Google** | Gemini 2.0 Flash | Fast (0.5s) | Free | Council member |
| **OpenRouter** | Various | Varies | Free/paid | 100+ models |
| **Ollama** | Local models | Slow (2–5s) | Free | Full privacy |

The fallback chain: if Groq fails → Claude → Gemini. The agent never stops
because one provider is down.

---

## 4. Supported Exchanges

QuntaTradeAI connects to your exchange using an **API key** — a read/trade key
that you generate in your exchange settings. We never ask for withdrawal access.

| Exchange | Asset class | Notes |
|----------|------------|-------|
| **Binance** | Crypto (spot + futures) | Most popular, best for crypto |
| **Hyperliquid** | Crypto perpetuals | On-chain, no KYC |
| **Bybit** | Crypto (spot + perps) | Good for Asia markets |
| **OKX** | Crypto | Large global exchange |
| **Kraken** | Crypto | Regulated, EU/US |
| **Coinbase** | Crypto | US-regulated |
| **OANDA** | Forex + CFDs | Practice accounts available |
| **MetaTrader 4/5** | Forex + CFDs | Via MetaAPI cloud bridge |
| **Alpaca** | US Stocks + Crypto | Commission-free, paper trading |
| **IBKR** | Stocks + Options + Forex | Professional broker |
| **Polymarket** | Prediction markets | CLOB-based, Polygon chain |

### How to connect an exchange

1. Go to **Settings → Venues → Add Venue**
2. Select your exchange
3. Click the direct link → opens your exchange's API settings page
4. Create a key with **Trade** permission only — **never enable Withdrawals**
5. Copy the key and secret into the form
6. Click **Test Connection** — confirms it works and shows your balance
7. Save

Your API key is encrypted with **AES-256-GCM** before it touches the database.
It is never logged, never sent in plain text, never visible after saving.

---

## 5. Strategy Personas

A persona is a named AI personality — it changes how the AI thinks about trades,
which indicators it weights most, and what risk limits apply.

### Available personas

#### 🟢 Momentum Hunter
- **Style:** Trend-following — rides strong directional moves
- **Best in:** Trending markets (bull or bear runs)
- **Indicators focused on:** RSI, MACD, EMA alignment
- **Typical hold:** 4–24 hours
- **Risk:** Moderate (3.5% max position, 2% stop-loss)
- **When it trades:** When RSI confirms momentum + MACD crossover aligned

#### 🟡 Scalper AI
- **Style:** Fast in/out — captures small, frequent gains
- **Best in:** Volatile, sideways markets
- **Indicators focused on:** RSI extremes, tight Bollinger Band bounces
- **Typical hold:** Under 4 hours
- **Risk:** Aggressive (2% max position, 1.2% stop-loss)
- **When it trades:** Frequently — many small trades, tight stops

#### 🟣 Swing Master
- **Style:** 1–3 day holds using higher-timeframe confluence
- **Best in:** Markets with clear structure (support/resistance)
- **Indicators focused on:** Multi-timeframe EMA, ATR, volume
- **Typical hold:** 1–3 days
- **Risk:** Conservative (4% max position, 3.5% stop-loss — wider stops)
- **When it trades:** Less frequently, but with higher conviction

#### 🩷 News Reactor
- **Style:** Sentiment-driven — reacts to economic calendar + fear/greed
- **Best in:** News-heavy periods, macro events
- **Indicators focused on:** Fear/greed index, RSI, economic calendar
- **Typical hold:** 4–12 hours
- **Risk:** Moderate (2.5% max position, 2.5% stop-loss)
- **When it trades:** Around economic events, sentiment extremes

### Persona Leaderboard

The leaderboard at `/leaderboard` shows each persona's **verified backtest performance**:
- 90-day return on BTC/USDT using real Binance historical data
- Win rate, Sharpe ratio, max drawdown
- Automatically updated every Monday via GitHub Actions

---

## 6. Risk Management

Every trade decision from the AI is passed through a **hard-coded risk manager**
before it can execute. The AI cannot override these rules. They are enforced in code,
not just instructions.

### Default risk limits

| Guard | Default | What it does |
|-------|---------|-------------|
| Max position size | 3% of equity | No single trade > 3% of your account |
| Max leverage | 2× | Cannot use more than 2× leverage |
| Mandatory stop-loss | 2.5% | Every trade gets a stop-loss automatically |
| Daily drawdown circuit breaker | −4% | Agent stops if you lose 4% in one day |
| Force-close threshold | −8% | All positions closed if down 8% total |
| Max total exposure | 20% | Never more than 20% of capital in trades |
| Max concurrent positions | 5 | Cannot hold more than 5 open trades |
| Balance reserve | 30% | Always keeps 30% as uninvested reserve |

### User-configurable guards (Guard Settings in dashboard)

| Setting | What it does |
|---------|-------------|
| **Confidence gate (0–95%)** | Skip trades where AI confidence < threshold |
| **Max daily loss** | Stop trading after X% daily loss |
| **Max trades/day** | Hard cap on number of trades per day |
| **Loss cooldown** | Pause after N consecutive losses |

### Beta live cap

During beta: maximum $500 per individual trade allocation, enforced server-side.
This protects users from catastrophic losses while the system is still being tested.
Remove by setting `BETA_LIVE_CAP_USD=0` in the backend `.env`.

---

## 7. Paper Trading vs Live Trading

### Paper trading (recommended for beginners)

- **Simulated money** — uses a fake balance, usually $10,000
- **Same AI decisions** — exactly the same logic as live trading
- **Same risk rules** — risk manager still validates every trade
- **No real money** — nothing actually executes on the exchange
- **Zero risk** — safe to run 24/7 while learning

Use paper trading to:
- Learn how the system works
- Test a strategy for 2–4 weeks before going live
- Observe the AI's decision-making in real market conditions

### Live trading

- **Real money** — executes actual orders on your exchange
- **Real P&L** — you gain or lose real funds
- **Shows "LIVE" badge** in red on the dashboard
- **Pre-start gate** — requires checking a risk acknowledgment box before starting

**Strongly recommended:** Run paper trading for at least 2 weeks first.
Watch 50–100 ticks. Only go live when you understand what the AI is doing
and you're comfortable with the risk settings.

---

## 8. The Dashboard — What You See

### Status Bar (top of page)

When the agent is **running**, you see two rows:

**Row 1:**
- `● Agent Active` — pulsing green dot
- `PAPER` or `LIVE` badge
- Venue name (e.g. Binance)
- Watching: which symbol (e.g. BTCUSDT)
- Persona (e.g. Momentum)
- Ticks: how many cycles completed
- Uptime: how long it's been running

**Row 2 (live activity):**
- `Next tick [progress bar] 3m 42s` — countdown to next AI decision
- `Last tick: 47s ago` — when it last ran
- `Interval: 5m` — your chosen timeframe
- `● AI: HOLD BTCUSDT — RSI neutral...` — latest log message, updates live

### Account stats

Shows your current balance, equity, return %, open positions, and Sharpe ratio.

### Equity Curve

A live chart showing your account value over time as trades execute.

### Positions Table

All currently open positions with entry price, current price, unrealised P&L,
leverage, and liquidation price.

### Decision Feed

Every AI decision logged in real time:
- Timestamp
- Which asset
- Action: BUY / SELL / HOLD
- Allocation amount
- AI rationale (why it decided this)

### Decision Timeline

When the agent is running, a live feed shows every event:
- `SIGNAL — RSI 28.4 — oversold zone entered`
- `SIGNAL — MACD +0.032 detected`
- `DECISION — AI decided BUY — confidence 74%`
- `EXECUTED — Order filled: BUY 0.002231 @ $67,420.00`
- `BLOCKED — Risk blocked — max position exceeded`

This answers "is this random?" — you can see exactly what triggered every trade.

### Controls (toolbar)

| Control | What it does |
|---------|-------------|
| Symbol picker | Switch between BTC, ETH, SOL, etc. |
| Persona selector | Choose AI personality before starting |
| Timeframe dropdown | 1m / 5m / 15m / 1h / 4h |
| Guards button | Opens confidence gate + loss protection sliders |
| Start / Stop | Start or stop the agent |
| Kill Switch | Emergency: close ALL positions immediately |
| Refresh | Force-refresh all data |

---

## 9. Safety Features

### Pre-start safety gate

Every time you click Start (in live mode), a confirmation screen appears showing:
- Which persona is selected
- Whether it's paper or live
- Your confidence gate threshold
- Your max daily loss setting
- A checkbox: "I understand this may result in losses"

The Start button is disabled until you check the box. Forces a deliberate decision.

### 2-second undo window

When a signal is sent manually via the TradingView webhook, there is a 2-second
window to cancel before it executes. API endpoint: `DELETE /api/agent/pending-order/{id}`.

### Kill switch

Immediately closes all open positions and stops the agent. Requires:
- Clicking the Kill Switch button
- Clicking it again to confirm (within 10 seconds)

### Dead man's switch

If the agent's tick loop crashes or freezes, a background watchdog detects it
and automatically stops the agent + closes positions after a timeout.

### HMAC receipt hashing

Every trade generates a cryptographically signed receipt that can be verified
for tampering. The hash is computed with your `ENCRYPTION_KEY` using HMAC-SHA256.

---

## 10. Trust Dashboard

Located at `/trust`. Shows your AI's real performance:

| Metric | What it means |
|--------|--------------|
| **Trust Score** | Composite score (0–100) based on win rate, Sharpe, drawdown |
| **Win Rate** | % of trades that were profitable |
| **Profit Curve** | Chart of running equity over last 50 trades |
| **Sharpe Ratio** | Risk-adjusted return (>1.5 = excellent, >0.5 = good) |
| **Max Drawdown** | Worst losing streak — how far equity fell from peak |
| **AI Accuracy** | % of high-confidence calls that were correct |

The Trust Score formula:
```
Trust Score = (win_rate × 0.4) + (sharpe × 20, capped at 30) +
              (30 - max_drawdown, capped at 0) + (ai_accuracy × 0.1)
```

---

## 11. Backtesting & Replay

Located at `/backtest`. Lets you test a strategy on historical data before risking
real money.

### How backtesting works

1. Choose symbol, exchange, timeframe, number of days, and strategy
2. Historical candles are fetched from the exchange
3. The strategy runs on those candles using the same risk manager code as live
4. Results show: total return, win rate, max drawdown, Sharpe ratio, Calmar ratio

**The same code runs in backtesting as in live trading** — no difference. This means
backtest results are genuinely predictive of live performance (no "backtest only" logic).

### Replay Visualiser

After a backtest completes, you can step through every trade one by one:
- Press **Play** to watch trades execute automatically
- Drag the slider to jump to any trade
- See the running P&L update with each trade
- "Trade 12 of 48: BUY BTC/USDT Entry $64,200 → Exit $66,800"

### Verified Persona Benchmarks

The leaderboard shows real 90-day backtest results for each persona on BTC/USDT.
These are regenerated every Monday automatically using GitHub Actions.
The data comes from Binance's public API — real historical prices, not simulations.

---

## 12. Plans & Billing

| Feature | Free | Starter ($20/mo) | Pro ($99/mo) | Enterprise ($299/mo) |
|---------|------|-----------------|-------------|---------------------|
| Paper trading | ✓ | ✓ | ✓ | ✓ |
| Live trading | ✗ | ✓ | ✓ | ✓ |
| Connected venues | 1 | 2 | 5 | Unlimited |
| AI model | Groq only | Groq + Claude | All providers | All providers |
| AI Council (3-vote) | ✗ | ✗ | ✓ | ✓ |
| RAG trade memory | ✗ | ✗ | ✓ | ✓ |
| Copy trading | ✗ | ✗ | ✓ | ✓ |
| Assets per session | 1 | 2 | 10 | Unlimited |
| Backtesting | Basic | Full | Full | Full |

Billing is handled by Stripe. Plans update instantly after payment.
Cancel any time — your data is kept for 90 days.

---

## 13. Admin Dashboard

Located at `/admin`. Only accessible to admin users (set via `ADMIN_CLERK_IDS`).

### Overview tab

- **MRR** — Monthly recurring revenue (live from plan counts)
- **ARR** — Annualised revenue
- **Total users** — New today, new 7d, new 30d
- **Paying users** — Count by plan
- **Live agents** — How many agents are running right now
- **Recent signups** — Last 20 sign-ups with email and plan
- **Recent activity** — Audit log: orders, risk blocks, agent starts

### Users & Payments tab

- **Search** — Find any user by email, name, or Clerk ID
- **Filter** — Filter by FREE / STARTER / PRO / ENTERPRISE
- **Click any user** → Slide-over panel showing:
  - Identity and plan status
  - Revenue from Stripe (real invoice amounts and dates)
  - All trades and P&L
  - Connected venues
  - **Manual plan override** (customer support tool)

### Manual plan override (customer support)

When a user pays but Stripe fails to update their plan:
1. Find the user in Users tab
2. Click their name
3. In the "Manual Plan Override" section, select the correct plan
4. Type the reason (e.g. "Stripe webhook failed, user emailed PayPal receipt")
5. Click Apply

The change takes effect immediately across both the database and the AI agent
(cache is flushed automatically). Every override is audit-logged.

---

## 14. Technical Architecture

### Backend — Python FastAPI

```
src/
  server.py                  Main API server (FastAPI + WebSocket)
  risk_manager.py            Hard-coded safety rules
  config_loader.py           Environment configuration
  agent/
    decision_maker.py        LLM provider abstraction + fallback chain
    council.py               Multi-LLM majority vote
    strategy_personas.py     Named AI personalities
    nl_parser.py             Natural language strategy rules
    providers/               Groq, Anthropic, Gemini, OpenRouter, Ollama
  venues/
    base.py                  Abstract Venue interface
    models.py                Order, Position, Balance, Candle types
    registry.py              Name → adapter routing
    crypto/                  Binance, Hyperliquid, CCXT (100+ exchanges)
    forex/                   OANDA, MetaTrader
    stocks/                  Alpaca, IBKR
    predictions/             Polymarket
  backtesting/               Backtest engine (same code as live)
  risk/                      Adaptive sizing, slippage, correlation hedge, VaR
  intel/                     MTF confluence, news sentiment, economic calendar
  memory/                    RAG trade memory (pgvector)
  services/                  Encryption, audit logging, receipts, observability
  copy_trading/              Mirror trades to followers
  alerts/                    Telegram, email, Discord notifications
```

### Frontend — Next.js 16 (App Router)

```
ui/app/
  (protected)/
    dashboard/     Main trading dashboard
    settings/      Venue + risk configuration
    backtest/      Backtesting + replay visualiser
    trust/         Trust dashboard (win rate, drawdown, Sharpe)
    admin/         Platform admin (users, revenue, agents)
    audit/         Full trade + decision audit log
    billing/       Plan management
    leaderboard/   Persona performance + marketplace
    calendar/      Economic calendar
    journal/       Trade journal
    marketplace/   Community strategy marketplace
```

### Database — PostgreSQL (via Supabase)

Tables: User, Venue, RiskProfile, TradeLog, EquityPoint, AuditLog, AgentRun,
StrategyListing, CopyRelationship, UserSettings

### Authentication — Clerk

All routes protected. JWT tokens verified on every request.
WebSocket connections authenticated via JWT query parameter.

### Security

- API credentials: AES-256-GCM encryption, keys never in plaintext after storage
- WebSocket: per-user scoping (no user sees another user's data)
- Rate limiting: global IP-based (120 req/min) + per-endpoint (10 agent starts/hr)
- CORS: locked to your domain in production
- Startup validation: server refuses to start if critical env vars are missing

### Data flow

```
Browser ──HTTPS──→ Next.js (Vercel)
                       │
                       ├──→ Clerk (auth verification)
                       ├──→ Prisma → PostgreSQL (Supabase)
                       └──→ Python API (Railway/Render)
                                   │
                                   ├──→ LLM providers (Groq/Anthropic/Gemini)
                                   └──→ Exchange adapters (Binance/Hyperliquid/...)

Browser ──WSS───→ Python WebSocket server (real-time updates)
```

---

## Quick Reference — URLs

| Page | URL | What it is |
|------|-----|-----------|
| Landing | `/` | Marketing page |
| Dashboard | `/dashboard` | Main trading interface |
| Settings | `/settings` | Venues, risk, API keys |
| Backtest | `/backtest` | Historical strategy testing |
| Trust | `/trust` | Performance analytics |
| Leaderboard | `/leaderboard` | Persona rankings + marketplace |
| Audit | `/audit` | Every trade and decision logged |
| Admin | `/admin` | Platform management (admin only) |
| Billing | `/billing` | Plans and payment |
| Docs | `/docs` | Exchange setup guides |

---

## Glossary

| Term | Plain English |
|------|--------------|
| **Tick** | One complete cycle: fetch → analyse → decide → execute |
| **Timeframe** | How often a tick fires (5m = every 5 minutes) |
| **Venue** | The exchange or broker you're trading on |
| **Persona** | The AI's trading personality and risk style |
| **Paper trading** | Simulated trading with fake money — no real risk |
| **Equity** | Your total account value (cash + open position value) |
| **Drawdown** | How much your account dropped from its highest point |
| **Sharpe ratio** | Return ÷ risk. Higher = better risk-adjusted performance |
| **RSI** | Relative Strength Index — measures if asset is overbought/oversold |
| **MACD** | Trend indicator — shows momentum direction |
| **EMA** | Exponential Moving Average — smoothed price trend line |
| **Confidence gate** | Minimum AI confidence score required before a trade executes |
| **Kill switch** | Emergency button that closes all trades immediately |
| **AI Council** | 3 AI models voting simultaneously (PRO plan) |
| **RAG memory** | AI remembers past trades and learns from them (PRO plan) |
| **AES-256-GCM** | Military-grade encryption used to protect your API keys |
| **HMAC** | Cryptographic signature that proves a receipt hasn't been tampered with |

---

*QuntaTradeAI — Not financial advice. Past performance does not guarantee future results.
All trading involves risk. Start with paper trading.*
