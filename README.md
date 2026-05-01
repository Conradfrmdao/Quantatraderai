# QuntaTradeAI

**The AI Agent That Trades While You Sleep.**

QuntaTradeAI is a production-grade autonomous trading platform powered by multi-LLM decision-making (Claude, Groq, Gemini), connecting to 10+ exchanges and brokers across crypto, forex, and stocks. The AI monitors markets 24/7, analyses live indicators, and executes risk-validated trades on your behalf — fully automated, fully audited, fully yours.

---

## What It Does

- Fetches live candles from any connected venue and computes 10+ technical indicators (EMA, RSI, MACD, ATR, BBands, ADX, OBV, VWAP, Stoch RSI)
- Routes market context through an **AI Council** (majority-vote across multiple LLM providers) for high-confidence decisions
- Every trade passes through a **hard-coded risk manager** before execution — no LLM can bypass it
- Full **audit trail** on every decision, order, and risk block
- Real-time dashboard with WebSocket updates, equity curve, and decision timeline

---

## Supported Venues

| Venue | Asset Class | Notes |
|-------|------------|-------|
| **Binance** (spot + perps) | Crypto | Futures + spot markets |
| **Hyperliquid** | Crypto perps | HIP-3 tradfi assets |
| **Bybit / OKX / Kraken / Coinbase** | Crypto | Via CCXT adapter |
| **OANDA** | Forex | Practice + live |
| **MetaTrader 4/5** | Forex + CFDs | Via MetaAPI cloud |
| **Alpaca** | Stocks | Paper + live |
| **Interactive Brokers** | Stocks + options | Requires TWS |
| **Polymarket** | Prediction markets | CLOB via py-clob-client |

---

## Strategy Personas

Choose how the AI thinks before you start:

| Persona | Style | Risk |
|---------|-------|------|
| **Momentum Hunter** | Trend-following | Moderate |
| **Scalper AI** | Fast in/out | Aggressive |
| **Swing Master** | 1-3 day holds | Conservative |
| **News Reactor** | Sentiment-driven | Moderate |

---

## Safety Architecture

Every guard is enforced in code — not just LLM prompts. The LLM cannot override these.

| Guard | Default |
|-------|---------|
| Max position size | 3% of equity |
| Max leverage | 2× |
| Mandatory stop-loss | 2.5% |
| Daily drawdown circuit breaker | −4% |
| Force-close loss threshold | −8% |
| Total exposure | 20% |
| Max concurrent positions | 5 |
| Balance reserve | 30% |
| Confidence gate | Configurable (0–95%) |
| Max trades per day | Configurable |
| Consecutive loss cooldown | Configurable |

---

## Setup

### Prerequisites
- Python 3.12+
- Node.js 22+
- PostgreSQL (via Supabase or self-hosted)
- [Poetry](https://python-poetry.org/) 2.x

### Quick start

```bash
git clone https://github.com/Conradfrmdao/Quantatraderai.git
cd Quantatraderai

# Backend
cp .env.example .env
# Fill in .env (see Environment Variables section)
poetry install
poetry run uvicorn src.server:app --host 0.0.0.0 --port 8000

# Frontend
cd ui
cp .env.local.example .env.local
# Fill in .env.local
pnpm install
pnpm prisma migrate deploy
pnpm dev
```

### Environment Variables

See `.env.example` for the full reference. Minimum required for local dev:

```bash
# Backend (.env)
ENCRYPTION_KEY=        # 32-byte base64 key: python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
DATABASE_URL=          # postgresql://...
LLM_PROVIDER=groq      # groq | anthropic | gemini
GROQ_API_KEY=          # gsk_...

# Frontend (ui/.env.local)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=   # pk_...
CLERK_SECRET_KEY=                     # sk_...
DATABASE_URL=                         # same as backend
ENCRYPTION_KEY=                       # same as backend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
PYTHON_API_URL=http://localhost:8000
```

---

## Running Tests

```bash
bash scripts/run_tests.sh
# 24 test suites: unit, integration, E2E, chaos, concurrency, load, security
# All must pass before deploying: "RELEASE READY — All 24 test suites passed"
```

---

## Docker

```bash
docker build -t quntatradeai .
docker run --env-file .env -p 8000:8000 quntatradeai
```

---

## Architecture

```
src/
  server.py                  # FastAPI + WebSocket API server
  config_loader.py           # Environment config
  risk_manager.py            # Hard safety guards
  agent/
    decision_maker.py        # LLM provider abstraction
    council.py               # Multi-LLM majority vote
    strategy_personas.py     # Named AI trading personalities
    nl_parser.py             # Natural language strategy rules
  venues/
    base.py                  # Abstract Venue interface
    models.py                # Order/Position/Balance/Candle types
    registry.py              # Name → adapter routing
    crypto/                  # Binance, Hyperliquid, CCXT
    forex/                   # OANDA, MetaTrader
    stocks/                  # Alpaca, IBKR
    predictions/             # Polymarket
  backtesting/               # Full backtest engine
  risk/                      # Adaptive sizing, slippage, hedging, VaR
  intel/                     # MTF confluence, news sentiment, economic calendar
  memory/                    # RAG trade memory (pgvector)
  services/                  # Encryption, audit, persistence, receipts
  copy_trading/              # Mirror trades to followers
  alerts/                    # Telegram, email, Discord notifier

ui/
  app/                       # Next.js 16 App Router
    (protected)/             # Auth-gated pages
      dashboard/             # Main trading dashboard
      settings/              # Venue + risk configuration
      backtest/              # Backtesting + replay visualiser
      trust/                 # Trust dashboard (win rate, drawdown, Sharpe)
      admin/                 # Platform admin (users, revenue, active agents)
  components/                # UI components
  lib/                       # Prisma, auth, payments, rate limiting
  prisma/                    # Schema + migrations
```

---

## License

Use at your own risk. Not financial advice. No guarantee of returns. This code has not been independently audited. Always start with paper trading.
