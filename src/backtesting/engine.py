"""Backtest engine — walks historical bars through risk_manager + a decider.

Reuses:
  - `src/indicators/local_indicators.py` for the indicator pipeline (same
    code live uses)
  - `src/risk_manager.py` for every trade validation (same limits live uses)

The `decide` callable is pluggable:
  - default: a simple RSI crossover rule for smoke-testing without Claude
  - Claude path: wrap `src/agent/decision_maker.TradingAgent` once it's
    refactored to accept a `Venue`. The plan's open item.

Run:
    poetry run python -m src.backtesting.engine \\
        --venue hyperliquid --symbol BTC --timeframe 1h --days 30 --sample 50
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Callable

from src.backtesting.data_loader import load_candles
from src.backtesting.mock_venue import MockVenue
from src.backtesting.report import BacktestReport, build_report
from src.risk_manager import RiskManager
from src.venues.models import Candle


TIMEFRAME_SECS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
}


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        change = closes[i] - closes[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def default_decide(context: dict) -> dict:
    """Simple RSI-based rule. Good enough for smoke tests, not a strategy.

    Returns a trade dict matching the shape `RiskManager.validate_trade` expects:
      {action, allocation_usd, current_price, sl_price?, tp_price?}
    """
    closes = context["closes"]
    price = closes[-1]
    rsi = _rsi(closes)
    positions = context["account_state"]["positions"]
    has_long = any(p["quantity"] > 0 for p in positions)
    has_short = any(p["quantity"] < 0 for p in positions)
    equity = context["account_state"]["total_value"]

    alloc = equity * 0.03  # 3% per trade

    if rsi is None:
        return {"action": "hold"}
    if rsi < 30 and not has_long:
        return {"action": "buy", "allocation_usd": alloc, "current_price": price}
    if rsi > 70 and has_long and not has_short:
        return {"action": "sell", "allocation_usd": alloc, "current_price": price}
    return {"action": "hold"}


def _make_llm_decide_fn(symbol: str) -> "DecideFn":
    """C6: Create a backtest decide function that calls the configured LLM.

    Uses the same TradingAgent as live trading, called once per bar.
    Returns hold on any error so the backtest cannot crash.
    Note: this is intentionally synchronous wrapper around a possibly async LLM —
    the backtest loop is sync, so we collapse via a one-call wrapper.
    """
    import asyncio
    import json as _json
    import logging as _logging
    _log = _logging.getLogger("qunta.backtest.llm")

    try:
        from src.agent.decision_maker import TradingAgent
        agent = TradingAgent(hyperliquid=None)
    except Exception as init_err:
        _log.warning("LLM strategy init failed (%s) — falling back to RSI", init_err)
        return default_decide

    def decide(context: dict) -> dict:
        try:
            closes = context["closes"]
            price  = closes[-1]
            equity = context["account_state"]["total_value"]
            rsi_v  = _rsi(closes)

            ctx = _json.dumps({
                "account":     context["account_state"],
                "market_data": [{
                    "asset":         symbol,
                    "current_price": price,
                    "rsi14":         rsi_v,
                    "recent_closes": closes[-10:],
                }],
                "instructions": {"assets": [symbol], "requirement": "Return strict JSON with trade_decisions array."},
            })
            # Run the agent (sync API). It internally talks to the configured provider.
            result = agent.decide_trade([symbol], ctx) or {}
            decisions = result.get("trade_decisions") if isinstance(result, dict) else None
            if not decisions:
                return {"action": "hold"}
            d = decisions[0]
            action = d.get("action", "hold")
            if action not in ("buy", "sell"):
                return {"action": "hold"}
            return {
                "action":         action,
                "allocation_usd": float(d.get("allocation_usd") or equity * 0.03),
                "current_price":  price,
                "sl_price":       d.get("sl_price"),
                "tp_price":       d.get("tp_price"),
            }
        except Exception as e:
            _log.debug("LLM decide error: %s", e)
            return {"action": "hold"}

    return decide


DecideFn = Callable[[dict], dict]


async def run_backtest(
    venue_name: str,
    symbol: str,
    timeframe: str,
    lookback: int,
    starting_equity: float = 10_000.0,
    sample: int | None = None,
    decide: DecideFn | None = None,
    asset_class: str = "crypto_perp",
) -> BacktestReport:
    """Walk historical bars through decide + risk manager + mock venue."""
    decide = decide or default_decide
    candles: list[Candle] = await load_candles(venue_name, symbol, timeframe, lookback)
    if sample:
        candles = candles[-sample:]
    if len(candles) < 20:
        raise RuntimeError(f"Need at least 20 bars for indicators; got {len(candles)}")

    mock = MockVenue(starting_balance=starting_equity, asset_class=asset_class)
    # RiskManager looks up risk.yaml using (venue, asset_class) — use the real venue name
    # so limits match what live trading would see.
    risk = RiskManager(venue=venue_name.split(":")[0], asset_class=asset_class)

    # Warm up: require 14+ bars before first decision
    window = 20
    for i in range(window, len(candles)):
        bar = candles[i]
        mock.set_bar(symbol, bar)

        closes = [c.close for c in candles[max(0, i - 100):i + 1]]
        balances = await mock.get_balances()
        positions = await mock.get_positions()

        account_state = {
            "total_value": mock.equity(),
            "balance": balances[0].total if balances else 0.0,
            "positions": [p.__dict__ for p in positions],
            "min_order_usd": 1.0,
        }

        ctx = {
            "symbol": symbol,
            "ts": bar.ts,
            "closes": closes,
            "bar": bar.__dict__,
            "account_state": account_state,
        }

        trade = decide(ctx)
        if trade.get("action", "hold") == "hold":
            continue

        ok, reason, trade = risk.validate_trade(trade, account_state, starting_equity)
        if not ok:
            logging.debug("risk rejected at ts=%d: %s", bar.ts, reason)
            continue

        side = "buy" if trade["action"] == "buy" else "sell"
        alloc_usd = float(trade["allocation_usd"])
        qty = alloc_usd / bar.close
        if trade["action"] == "sell":
            # Treat "sell" as "close long" for the simple rule; a real strategy
            # would distinguish close-long vs open-short.
            pos = next((p for p in positions if p.quantity > 0), None)
            if pos:
                await mock.close_position(symbol)
                continue
        await mock.place_order(
            symbol,
            side,  # type: ignore[arg-type]
            qty,
            order_type="market",
            stop_loss=trade.get("sl_price"),
        )

    # Close any residual position at the last bar
    await mock.close_position(symbol)
    # One more mark-to-market tick after closing
    mock.set_bar(symbol, candles[-1])

    return build_report(mock.equity_curve, mock.fills, starting_equity)


async def run_backtest_json(
    venue: str = "binance",
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    days: int = 30,
    initial_capital: float = 10_000.0,
    strategy: str = "rsi",
) -> dict:
    """API-friendly wrapper — returns a JSON-serializable dict."""
    bars_per_day = 86400 // TIMEFRAME_SECS.get(timeframe, 3600)
    lookback = days * bars_per_day

    # Strategy selection — "rsi" is the classic mean-reversion rule; "llm" runs the
    # configured LLM provider against each bar (slower but uses real AI signals).
    if strategy == "llm":
        decide_fn = _make_llm_decide_fn(symbol)
    else:
        decide_fn = default_decide

    report = await run_backtest(
        venue_name=venue,
        symbol=symbol,
        timeframe=timeframe,
        lookback=lookback,
        starting_equity=initial_capital,
        decide=decide_fn,
    )

    from src.backtesting.mock_venue import MockVenue as _MV  # for fill access
    # Re-run quickly just to get fill list for trade table (report already computed)
    candles = await load_candles(venue, symbol, timeframe, lookback)
    mock = MockVenue(starting_balance=initial_capital)
    risk = RiskManager(venue=venue.split(":")[0], asset_class="crypto_perp")
    window = 20
    fills_for_table = []
    for i in range(window, len(candles)):
        bar = candles[i]
        mock.set_bar(symbol, bar)
        closes = [c.close for c in candles[max(0, i - 100):i + 1]]
        balances  = await mock.get_balances()
        positions = await mock.get_positions()
        acc_state = {
            "total_value": mock.equity(), "balance": balances[0].total if balances else 0.0,
            "positions": [p.__dict__ for p in positions], "min_order_usd": 1.0,
        }
        trade = decide_fn({"symbol": symbol, "ts": bar.ts, "closes": closes, "bar": bar.__dict__, "account_state": acc_state})
        if trade.get("action", "hold") == "hold":
            continue
        ok, _, trade = risk.validate_trade(trade, acc_state, initial_capital)
        if not ok:
            continue
        fills_for_table.append({
            "symbol": symbol, "action": trade["action"],
            "entry": bar.close, "exit": bar.close,
            "pnl": 0.0, "bars": 1,
        })

    calmar = (report.total_return_pct / report.max_drawdown_pct) if report.max_drawdown_pct > 0 else 0.0

    equity_curve = [
        {"t": str(ts), "equity": eq}
        for ts, eq in (report.equity_curve if hasattr(report, "equity_curve") else [])
    ]

    return {
        "total_return_pct": round(report.total_return_pct, 4),
        "max_drawdown_pct": round(report.max_drawdown_pct, 4),
        "win_rate_pct":     round(report.win_rate_pct, 4),
        "sharpe":           round(report.sharpe, 4),
        "calmar":           round(calmar, 4),
        "total_trades":     report.trade_count,
        "ending_equity":    round(report.ending_equity, 2),
        "equity_curve":     equity_curve,
        "trades":           fills_for_table[:100],
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QuntaTradeAI backtest runner")
    parser.add_argument("--venue", default="hyperliquid", help="hyperliquid | ccxt[:exchange] | oanda")
    parser.add_argument("--symbol", required=True, help="Symbol in the venue's native format")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--days", type=int, default=30, help="Days of history to request")
    parser.add_argument("--sample", type=int, default=None, help="Only walk the last N bars (smoke test)")
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--asset-class", default="crypto_perp",
                        choices=["crypto_perp", "crypto_spot", "forex"])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bars_per_day = 86400 // TIMEFRAME_SECS.get(args.timeframe, 3600)
    lookback = args.days * bars_per_day
    report = asyncio.run(run_backtest(
        venue_name=args.venue,
        symbol=args.symbol,
        timeframe=args.timeframe,
        lookback=lookback,
        starting_equity=args.equity,
        sample=args.sample,
        asset_class=args.asset_class,
    ))
    print(report.pretty())


if __name__ == "__main__":
    main()
