# QuntaTradeAI

A Claude-powered, multi-venue AI trading agent. QuntaTradeAI evaluates live market data with technical indicators, asks Claude for buy/sell/hold decisions, and executes trades through pluggable venue adapters across **crypto** and **forex** platforms.

> Originally forked from [aggarwaldev/hyperliquid-trading-agent](https://github.com/aggarwaldev/hyperliquid-trading-agent). Rearchitected to be venue-agnostic, with tightened risk defaults and scaffolding for backtesting and alerts.

## What It Does

1. Fetches real-time candles from the selected venue and computes local technical indicators (EMA, RSI, MACD, ATR, BBands, ADX, OBV, VWAP).
2. Sends the full market context to Claude, which returns structured buy/sell/hold decisions with allocation and TP/SL.
3. The risk manager validates every trade against hard-coded limits before execution.
4. The venue adapter executes the approved orders.

## Supported Venues

| Venue | Asset classes | Adapter |
|---|---|---|
| **Hyperliquid** | Crypto perps (+ HIP-3 tradfi assets) | `src/venues/crypto/hyperliquid.py` |
| **CCXT** (100+ exchanges: Binance, Coinbase, Kraken, OKX, Bybit, KuCoin, Bitget, Gate, MEXC, ...) | Crypto spot + many perps | `src/venues/crypto/ccxt_adapter.py` |
| **OANDA** | Forex majors/minors/exotics + CFDs | `src/venues/forex/oanda.py` |

Additional native adapters (Binance perps, MetaTrader 5, Interactive Brokers) are stubbed and can be filled in as needs arise.

## Safety Guards

All enforced in code, not just LLM prompts. Defaults are intentionally conservative:

| Guard | QuntaTradeAI default | Upstream default |
|-------|---------------------|------------------|
| Max position size | **3%** | 10% |
| Max leverage | **2x** | 10x |
| Mandatory stop-loss | **2.5%** | 5% |
| Daily drawdown circuit breaker | **-4%** | -10% |
| Force-close loss threshold | **-8%** | -20% |
| Total exposure | **20%** | 50% |
| Max concurrent positions | **5** | 10 |
| Balance reserve | **30%** | 20% |

Loosen these only after backtesting and a testnet/practice run.

Per-venue and per-asset-class overrides live in [risk.yaml](risk.yaml).

## Setup

### Prerequisites
- Python 3.12+
- [Poetry](https://python-poetry.org/) 2.x (or use plain pip per the Dockerfile)

### Install
```bash
poetry install
cp .env.example .env
# fill in your keys
```

### API keys

1. **Anthropic** — create a key at [console.anthropic.com](https://console.anthropic.com) and set `ANTHROPIC_API_KEY`. Default model is `claude-sonnet-4-6` (cheaper for per-bar loops); switch to `claude-opus-4-7` for higher-stakes decisions.
2. **Hyperliquid** — in the Hyperliquid UI, generate an **API wallet** (not your main seed), set `HYPERLIQUID_PRIVATE_KEY` (API wallet key) and `HYPERLIQUID_VAULT_ADDRESS` (main wallet). Start with `HYPERLIQUID_NETWORK=testnet`.
3. **CCXT crypto exchange** — pick one (e.g. Binance). Create a key with **trade enabled, withdrawals disabled**, IP-allowlisted. Set `CCXT_EXCHANGE`, `CCXT_API_KEY`, `CCXT_API_SECRET`, `CCXT_SANDBOX=true`.
4. **OANDA** — create a **practice** account at [developer.oanda.com](https://developer.oanda.com), generate a personal access token. Set `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID`, `OANDA_ENV=practice`.
5. **Telegram alerts** (optional) — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

### Run

```bash
# Hyperliquid (default)
poetry run qunta --venue hyperliquid --assets "BTC ETH SOL" --interval 5m

# CCXT (Binance spot)
poetry run qunta --venue ccxt --assets "BTC/USDT ETH/USDT" --interval 15m

# OANDA (forex, practice env)
poetry run qunta --venue oanda --assets "EUR_USD GBP_USD USD_JPY" --interval 1h
```

Or via `.env` (`VENUE`, `ASSETS`, `INTERVAL`) and `poetry run qunta`.

### Backtesting

```bash
poetry run python -m src.backtesting.engine \
    --venue hyperliquid --symbol BTC --timeframe 1h --days 30 --sample 50
```

Backtests call the **same** `decision_maker` and `risk_manager` code as live; only the venue is swapped for a mock that tracks PnL in memory.

### Status CLI

```bash
poetry run python -m src.dashboard.status
```

Prints current positions, today's PnL, and the last N Claude decisions.

## Validation Sequence (do this before real money)

1. **Backtest** the tightened risk config on ≥30 days of historical data. Confirm it's not catastrophic.
2. **Testnet / practice run** — Hyperliquid testnet or OANDA practice env. Run the live loop for several full decision cycles. Confirm orders submit, the risk manager rejects oversized trades, and alerts fire.
3. **Live with minimum stake** — only after 1 and 2 pass, start with the smallest viable equity.

## Structure

```
src/
  main.py                   # Entry point, trading loop, API server
  config_loader.py          # Environment config
  risk_manager.py           # Safety guards
  agent/decision_maker.py   # Claude integration
  indicators/               # Local TA indicators
  venues/
    base.py                 # Abstract Venue interface
    models.py               # Shared Order/Position/Balance/Candle dataclasses
    registry.py             # venue-name -> adapter
    crypto/
      hyperliquid.py
      ccxt_adapter.py
    forex/
      oanda.py
  backtesting/              # Backtest engine + mock venue
  alerts/                   # Notifier (Telegram, console)
  dashboard/                # Status CLI
  trading/hyperliquid_api.py  # Legacy wrapper, now used by venues/crypto/hyperliquid.py
```

## API Endpoints

When running, the agent serves a local HTTP API:
- `GET /diary` — recent trade diary entries
- `GET /logs` — LLM request logs

## License

Use at your own risk. No guarantee of returns. This code has not been audited.
