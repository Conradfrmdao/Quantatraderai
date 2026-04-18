"""Backtest report: total return, max drawdown, win rate, Sharpe."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class BacktestReport:
    starting_equity: float
    ending_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    trade_count: int
    sharpe: float

    def pretty(self) -> str:
        return (
            f"Backtest report\n"
            f"  starting equity : ${self.starting_equity:,.2f}\n"
            f"  ending equity   : ${self.ending_equity:,.2f}\n"
            f"  total return    : {self.total_return_pct:+.2f}%\n"
            f"  max drawdown    : {self.max_drawdown_pct:.2f}%\n"
            f"  trades          : {self.trade_count}\n"
            f"  win rate        : {self.win_rate_pct:.2f}%\n"
            f"  sharpe (per-bar): {self.sharpe:.2f}\n"
        )


def build_report(
    equity_curve: list[tuple[int, float]],
    fills: list[dict],
    starting_equity: float,
) -> BacktestReport:
    if not equity_curve:
        return BacktestReport(starting_equity, starting_equity, 0, 0, 0, 0, 0)

    ending_equity = equity_curve[-1][1]
    total_return_pct = (ending_equity / starting_equity - 1) * 100 if starting_equity else 0

    peak = starting_equity
    max_dd = 0.0
    prev = starting_equity
    returns: list[float] = []
    for _, eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)
        if prev:
            returns.append((eq - prev) / prev)
        prev = eq

    # Pair buys and sells per symbol to compute win rate at a round-trip level.
    round_trips = _pair_fills(fills)
    wins = sum(1 for rt in round_trips if rt > 0)
    trade_count = len(round_trips)
    win_rate_pct = (wins / trade_count * 100) if trade_count else 0

    if returns and len(returns) > 1:
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        stddev = math.sqrt(var)
        sharpe = (mean / stddev) * math.sqrt(len(returns)) if stddev > 0 else 0.0
    else:
        sharpe = 0.0

    return BacktestReport(
        starting_equity=starting_equity,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_dd,
        win_rate_pct=win_rate_pct,
        trade_count=trade_count,
        sharpe=sharpe,
    )


def _pair_fills(fills: list[dict]) -> list[float]:
    """Naive pairing: close when running qty returns to zero. Returns PnL per round-trip."""
    by_symbol: dict[str, list[dict]] = {}
    for f in fills:
        by_symbol.setdefault(f["symbol"], []).append(f)

    round_trips: list[float] = []
    for symbol, flist in by_symbol.items():
        qty = 0.0
        entry_cost = 0.0
        for f in flist:
            signed = f["quantity"] if f["side"] == "buy" else -f["quantity"]
            if qty == 0 or (qty > 0) == (signed > 0):
                entry_cost += signed * f["price"]
                qty += signed
            else:
                closing = min(abs(qty), abs(signed))
                direction = 1 if qty > 0 else -1
                pnl = (f["price"] - (entry_cost / qty if qty else 0)) * closing * direction
                round_trips.append(pnl)
                qty += signed
                if qty == 0:
                    entry_cost = 0.0
                else:
                    entry_cost = qty * f["price"]
    return round_trips
