"""Value at Risk (VaR) calculator.

Computes 95% and 99% VaR via Monte Carlo simulation (10k paths) on the
current portfolio's daily return distribution.

Exposed via GET /api/var — results are shown in the dashboard Risk panel.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Any


def _daily_returns(equity_curve: list[float]) -> list[float]:
    """Convert equity values to daily log-returns."""
    returns = []
    for i in range(1, len(equity_curve)):
        prev = float(equity_curve[i - 1] or 0)
        cur = float(equity_curve[i] or 0)
        if prev <= 0 or cur <= 0:
            continue
        if not math.isfinite(prev) or not math.isfinite(cur):
            continue
        returns.append(math.log(cur / prev))
    return returns


def monte_carlo_var(
    equity_curve: list[float],
    confidence_levels: tuple[float, ...] = (0.95, 0.99),
    simulations: int = 10_000,
    horizon_days: int = 1,
) -> dict[str, Any]:
    """
    Run Monte Carlo VaR simulation.

    Args:
        equity_curve: Historical equity values (most recent last).
        confidence_levels: e.g. (0.95, 0.99)
        simulations: Number of Monte Carlo paths.
        horizon_days: Holding period in trading days.

    Returns dict with VaR at each confidence level + expected shortfall.
    """
    if len(equity_curve) < 10:
        return {"error": "Not enough equity history (need ≥ 10 data points)"}

    current_equity = equity_curve[-1]
    if current_equity <= 0 or not math.isfinite(current_equity):
        return {"error": "Current equity must be positive"}
    returns        = _daily_returns(equity_curve)
    if len(returns) < 2:
        return {"error": "Could not compute enough valid returns"}

    mu    = statistics.mean(returns)
    sigma = statistics.stdev(returns) if len(returns) > 1 else 0.01

    # Scale to horizon
    mu_h    = mu    * horizon_days
    sigma_h = sigma * math.sqrt(horizon_days)

    # Monte Carlo paths
    simulated_pnl = []
    for _ in range(simulations):
        # Box-Muller normal random
        u1 = random.random() or 1e-10
        u2 = random.random()
        z  = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
        r  = mu_h + sigma_h * z
        simulated_pnl.append(current_equity * (math.exp(r) - 1))

    simulated_pnl.sort()
    n = len(simulated_pnl)

    result: dict[str, Any] = {
        "current_equity":  round(current_equity, 2),
        "horizon_days":    horizon_days,
        "simulations":     simulations,
        "mean_daily_return_pct": round(mu * 100, 4),
        "daily_volatility_pct":  round(sigma * 100, 4),
    }

    for cl in confidence_levels:
        idx = int((1 - cl) * n)
        var = abs(simulated_pnl[idx])
        # Expected Shortfall = mean of losses beyond VaR
        es  = abs(statistics.mean(simulated_pnl[:idx])) if idx > 0 else var
        key = f"var_{int(cl * 100)}"
        result[key] = {
            "usd":        round(var, 2),
            "pct":        round(var / current_equity * 100, 4) if current_equity else 0,
            "es_usd":     round(es,  2),
            "confidence": cl,
        }

    return result


def parametric_var(
    equity_curve: list[float],
    confidence_levels: tuple[float, ...] = (0.95, 0.99),
) -> dict[str, Any]:
    """Faster analytical (parametric) VaR assuming log-normal returns."""
    if len(equity_curve) < 5:
        return {"error": "Not enough history"}

    current  = equity_curve[-1]
    if current <= 0 or not math.isfinite(current):
        return {"error": "Current equity must be positive"}
    returns  = _daily_returns(equity_curve)
    if len(returns) < 2:
        return {"error": "Could not compute enough valid returns"}
    mu       = statistics.mean(returns)
    sigma    = statistics.stdev(returns) if len(returns) > 1 else 0.01

    # Standard normal Z-scores for common confidence levels
    Z = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326, 0.999: 3.090}

    result: dict[str, Any] = {"current_equity": round(current, 2)}
    for cl in confidence_levels:
        z   = Z.get(cl, 1.645)
        var = current * (1 - math.exp(mu - z * sigma))
        key = f"var_{int(cl * 100)}"
        result[key] = {
            "usd": round(abs(var), 2),
            "pct": round(abs(var) / current * 100, 4) if current else 0,
            "confidence": cl,
            "method": "parametric",
        }
    return result
