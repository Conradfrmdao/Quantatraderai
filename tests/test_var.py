from __future__ import annotations

import math

from src.risk.var import _daily_returns, monte_carlo_var, parametric_var


def test_daily_returns_skip_zero_and_negative_equity_points():
    returns = _daily_returns([100.0, 105.0, 0.0, 110.0, 121.0])

    assert len(returns) == 2
    assert math.isclose(returns[0], math.log(105.0 / 100.0), rel_tol=0, abs_tol=1e-12)
    assert math.isclose(returns[1], math.log(121.0 / 110.0), rel_tol=0, abs_tol=1e-12)


def test_var_calculators_skip_non_positive_points_without_crashing():
    curve = [100.0, 101.0, 102.0, 0.0, 103.0, -1.0, 104.0, 105.0, 106.0, 0.0, 107.0]

    mc = monte_carlo_var(curve, simulations=100)
    para = parametric_var(curve)

    assert "error" not in mc
    assert "error" not in para
    assert mc["current_equity"] == 107.0
    assert para["current_equity"] == 107.0
