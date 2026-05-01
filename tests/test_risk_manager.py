"""Tests for RiskManager — every guard must block what it claims to block."""
import pytest
from src.risk_manager import RiskManager


@pytest.fixture
def rm():
    return RiskManager(venue="test", asset_class="crypto_spot")


# ── position size ─────────────────────────────────────────────────────────────

def test_position_size_ok(rm):
    ok, _ = rm.check_position_size(alloc_usd=200, account_value=10_000)
    assert ok  # 200 / 10000 = 2% < 3%

def test_position_size_over(rm):
    ok, reason = rm.check_position_size(alloc_usd=500, account_value=10_000)
    assert not ok
    assert "exceeds" in reason

def test_position_size_zero_account(rm):
    ok, _ = rm.check_position_size(alloc_usd=100, account_value=0)
    assert not ok


# ── leverage ──────────────────────────────────────────────────────────────────

def test_leverage_ok(rm):
    ok, _ = rm.check_leverage(alloc_usd=100, balance=200)
    assert ok  # 0.5x < 2x

def test_leverage_over(rm):
    ok, reason = rm.check_leverage(alloc_usd=500, balance=100)
    assert not ok
    assert "leverage" in reason.lower()

def test_leverage_zero_balance(rm):
    ok, _ = rm.check_leverage(alloc_usd=100, balance=0)
    assert not ok


# ── daily drawdown / circuit breaker ─────────────────────────────────────────

def test_circuit_breaker_not_triggered(rm):
    ok, _ = rm.check_daily_drawdown(account_value=10_000)
    assert ok

def test_circuit_breaker_triggers(rm):
    rm._reset_daily_if_needed(10_000)
    rm.daily_high_value = 10_000
    # 5% drop > 4% threshold
    ok, reason = rm.check_daily_drawdown(account_value=9_500)
    assert not ok
    assert rm.circuit_breaker_active
    assert "circuit breaker" in reason.lower()

def test_circuit_breaker_blocks_subsequent(rm):
    from datetime import datetime, timezone
    rm.circuit_breaker_active = True
    rm.daily_high_date = datetime.now(timezone.utc).date()
    rm.daily_high_value = 10_000
    ok, reason = rm.check_daily_drawdown(account_value=10_000)
    assert not ok
    assert "circuit breaker" in reason.lower()


# ── concurrent positions ──────────────────────────────────────────────────────

def test_concurrent_ok(rm):
    ok, _ = rm.check_concurrent_positions(current_count=3)
    assert ok

def test_concurrent_at_limit(rm):
    ok, reason = rm.check_concurrent_positions(current_count=5)
    assert not ok
    assert "max concurrent" in reason.lower()


# ── balance reserve ───────────────────────────────────────────────────────────

def test_balance_reserve_ok(rm):
    ok, _ = rm.check_balance_reserve(balance=8_000, initial_balance=10_000)
    assert ok  # 8000/10000 = 80% > 30%

def test_balance_reserve_below(rm):
    ok, reason = rm.check_balance_reserve(balance=2_000, initial_balance=10_000)
    assert not ok
    assert "reserve" in reason.lower()

def test_balance_reserve_zero_initial(rm):
    ok, _ = rm.check_balance_reserve(balance=0, initial_balance=0)
    assert ok  # No initial balance known — skip check


# ── stop-loss enforcement ─────────────────────────────────────────────────────

def test_enforce_sl_buy_no_sl(rm):
    sl = rm.enforce_stop_loss(sl_price=None, entry_price=1_000, is_buy=True)
    assert sl < 1_000  # SL below entry for longs

def test_enforce_sl_sell_no_sl(rm):
    sl = rm.enforce_stop_loss(sl_price=None, entry_price=1_000, is_buy=False)
    assert sl > 1_000  # SL above entry for shorts

def test_enforce_sl_provided(rm):
    sl = rm.enforce_stop_loss(sl_price=980, entry_price=1_000, is_buy=True)
    assert sl == 980  # Should keep user-provided SL


# ── composite validate_trade ──────────────────────────────────────────────────

def test_validate_trade_hold(rm, account_state_factory):
    trade = {"action": "hold", "allocation_usd": 0}
    ok, reason, _ = rm.validate_trade(trade, account_state_factory(), 10_000)
    assert ok

def test_validate_trade_zero_alloc(rm, account_state_factory):
    trade = {"action": "buy", "allocation_usd": 0}
    ok, _, _ = rm.validate_trade(trade, account_state_factory(), 10_000)
    assert not ok

def test_validate_trade_caps_oversize(rm, account_state_factory):
    trade = {"action": "buy", "allocation_usd": 5_000, "current_price": 100}
    ok, _, adjusted = rm.validate_trade(trade, account_state_factory(), 10_000)
    assert ok
    assert adjusted["allocation_usd"] <= 10_000 * (rm.max_position_pct / 100) + 1

def test_validate_trade_sl_auto_set(rm, account_state_factory):
    trade = {"action": "buy", "allocation_usd": 200, "current_price": 1_000}
    ok, _, adjusted = rm.validate_trade(trade, account_state_factory(), 10_000)
    assert ok
    assert adjusted.get("sl_price") is not None
    assert adjusted["sl_price"] < 1_000
