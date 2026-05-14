from src.server import _apply_market_data_guards, _build_market_data_status


def test_stale_market_data_blocks_trade_with_clear_message():
    status = {
        "symbol": "BTC/USDT",
        "status": "stale",
        "ready": False,
        "fallback_rationale": "old candle",
    }
    guarded = _apply_market_data_guards(
        [{"asset": "BTC/USDT", "action": "buy", "allocation_usd": 100, "rationale": "go"}],
        {"BTC/USDT": status, "BTCUSDT": status},
    )
    assert guarded[0]["action"] == "hold"
    assert guarded[0]["allocation_usd"] == 0.0
    assert guarded[0]["reason_code"] == "market_data_stale"
    assert guarded[0]["rationale"] == "Market data is stale. Agent paused trading for safety."


def test_market_data_status_detects_warmup_and_stale():
    warmup = _build_market_data_status(
        "BTC/USDT",
        [{"time": 1_000, "close": 1.0}] * 20,
        {"rsi14": [50], "ema20": [1], "macd": [0.1]},
        "1m",
        1.0,
        now_ts=1_060,
    )
    assert warmup["status"] == "warmup"

    candles = [{"time": 1_000 + i * 60, "close": 1.0} for i in range(40)]
    stale = _build_market_data_status(
        "BTC/USDT",
        candles,
        {"rsi14": [50], "ema20": [1], "macd": [0.1]},
        "1m",
        1.0,
        now_ts=10_000,
    )
    assert stale["status"] == "stale"
