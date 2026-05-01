"""Tests for local_indicators — known input → known output ranges."""
import pytest
from src.indicators.local_indicators import compute_all, latest


def test_compute_all_returns_expected_keys(base_candles):
    result = compute_all(base_candles)
    for key in ("ema20", "ema50", "rsi14", "macd", "bbands_upper", "bbands_lower",
                 "atr14", "adx", "obv", "vwap"):
        assert key in result, f"Missing key: {key}"


def test_ema_is_list(base_candles):
    result = compute_all(base_candles)
    assert isinstance(result["ema20"], list)
    assert len(result["ema20"]) == len(base_candles)


def test_rsi_bounded(base_candles):
    result = compute_all(base_candles)
    rsi_vals = [v for v in result["rsi14"] if v is not None]
    assert rsi_vals, "RSI series is empty"
    for v in rsi_vals:
        assert 0 <= v <= 100, f"RSI out of bounds: {v}"


def test_bbands_upper_above_lower(base_candles):
    result = compute_all(base_candles)
    upper = [v for v in result["bbands_upper"] if v is not None]
    lower = [v for v in result["bbands_lower"] if v is not None]
    assert upper and lower
    for u, l in zip(upper, lower):
        assert u >= l, f"Upper band {u} below lower {l}"


def test_latest_ignores_none():
    series = [None, None, 42.0, 43.0]
    assert latest(series) == 43.0


def test_latest_all_none():
    assert latest([None, None]) is None


def test_latest_empty():
    assert latest([]) is None


def test_obv_is_cumulative(base_candles):
    result = compute_all(base_candles)
    obv = [v for v in result["obv"] if v is not None]
    assert len(obv) > 1


def test_atr_positive(base_candles):
    result = compute_all(base_candles)
    atr = [v for v in result["atr14"] if v is not None]
    assert all(v >= 0 for v in atr), "ATR must be non-negative"


def test_vwap_near_price(base_candles):
    result = compute_all(base_candles)
    vwap_vals = [v for v in result["vwap"] if v is not None]
    closes = [c["close"] for c in base_candles]
    assert vwap_vals
    last_vwap = vwap_vals[-1]
    assert 0.5 * min(closes) < last_vwap < 2 * max(closes), "VWAP wildly out of range"
