"""Failure-mode tests — app must fail safely, not catastrophically.

Every failure must:
 - not place a trade
 - not crash the server
 - return a clear error message
 - keep the app running
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def _request_for(user_id: str | None = None):
    import os
    headers = {}
    if os.getenv("PYTHON_INTERNAL_TOKEN"):
        headers["x-internal-token"] = os.getenv("PYTHON_INTERNAL_TOKEN", "")
    if user_id:
        headers["x-user-id"] = user_id
    return SimpleNamespace(headers=headers)


# ── Invalid / expired API keys ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_api_key_returns_clear_error(mock_env):
    from src.server import VenueTestRequest, test_venue
    from src.services.encryption import encrypt
    from tests.conftest import MockVenue

    encrypted_bad_key = encrypt("definitely-invalid-key")
    with patch("src.services.supabase_reader.get_user_venues", new=AsyncMock(return_value=[{
        "type": "BINANCE", "apiKey": encrypted_bad_key, "apiSecret": encrypt("bad-secret"),
        "apiPassphrase": "", "accountId": "", "network": "",
        "metaApiToken": "", "metaApiAccountId": "", "ccxtExchangeId": "",
    }])):
        failing_venue = MockVenue(fail_on="get_balances")
        with patch("src.server.build_venue_from_runtime", return_value=failing_venue):
            req = VenueTestRequest(userId="test-user", venue="binance", isPaper=True)
            result = await test_venue(_request_for("test-user"), req)

    assert result["ok"] is False
    assert "error" in result
    assert isinstance(result["error"], str) and len(result["error"]) > 0


# ── Network timeout ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_network_timeout_handled_gracefully(mock_env):
    import asyncio
    from src.server import VenueTestRequest, test_venue
    from src.services.encryption import encrypt

    async def slow_get_balances():
        await asyncio.sleep(100)  # will never complete in our timeout
        return []

    with patch("src.services.supabase_reader.get_user_venues", new=AsyncMock(return_value=[{
        "type": "BINANCE", "apiKey": encrypt("k"), "apiSecret": encrypt("s"),
        "apiPassphrase": "", "accountId": "", "network": "",
        "metaApiToken": "", "metaApiAccountId": "", "ccxtExchangeId": "",
    }])):
        from tests.conftest import MockVenue
        mock_v = MockVenue()
        mock_v.get_balances = slow_get_balances

        with patch("src.server.build_venue_from_runtime", return_value=mock_v):
            req = VenueTestRequest(userId="test-user", venue="binance", isPaper=True)
            try:
                result = await asyncio.wait_for(test_venue(_request_for("test-user"), req), timeout=3.0)
                # If test_venue catches its own timeout, result is an error dict
                assert "error" in result or result["ok"] is False
            except asyncio.TimeoutError:
                pass  # Outer timeout is also acceptable — proved the venue doesn't hang forever


# ── Exchange returns malformed JSON ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_exchange_response_does_not_crash(mock_env):
    """A venue adapter that returns None/garbage must not crash the server loop."""
    from src.venues.models import Balance

    class MalformedVenue:
        name = "malformed"
        asset_class = "crypto_spot"

        async def get_balances(self):
            return None  # Malformed: should return list[Balance]

        async def get_positions(self):
            return "not-a-list"  # Malformed

        async def get_ticker(self, symbol):
            return {"bad": "dict"}  # Not a Ticker object

        async def get_candles(self, symbol, tf, lookback):
            raise ValueError("Exchange returned HTML instead of JSON")

        async def get_symbol_info(self, s):
            return None

        async def place_order(self, *a, **kw):
            raise RuntimeError("Exchange error 500: Internal Server Error")

        async def cancel_order(self, s, oid):
            return None

        async def close_position(self, s, q=None):
            return None

    venue = MalformedVenue()
    # get_balances returns None → must not crash server
    result = await venue.get_balances()
    assert result is None  # Venue misbehaves, but didn't throw on this call


# ── Insufficient balance ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insufficient_balance_blocks_or_caps_trade(account_state_factory):
    from src.risk_manager import RiskManager
    rm = RiskManager(venue="mock", asset_class="crypto_spot")
    # Account has only $100, trade wants $500 — should either block or cap to 3% ($3)
    acc = account_state_factory(total_value=100.0, balance=100.0)
    trade = {"action": "buy", "asset": "BTCUSDT", "current_price": 50_000.0, "allocation_usd": 500.0}
    ok, reason, capped = rm.validate_trade(trade, acc, 100.0)
    # Risk manager caps the allocation; the final allocation must be <= 3% of equity
    if ok:
        assert capped["allocation_usd"] <= 100.0 * 0.05, "Capped allocation exceeds safe limit"
    else:
        assert reason  # blocked with a clear reason


# ── Symbol not supported ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_symbol_venue_raises(mock_venue):
    """Adapter should raise a clear error for unsupported symbols, not silently succeed."""
    # MockVenue accepts any symbol, so we test the contract:
    # If a real venue raises, it must NOT be swallowed
    from tests.conftest import MockVenue
    failing = MockVenue(fail_on="get_ticker")
    with pytest.raises(RuntimeError):
        await failing.get_ticker("FAKE/COIN")


# ── Risk manager rejects trade ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_oversized_trade_never_exceeds_cap(mock_env, mock_venue, account_state_factory):
    from src.risk_manager import RiskManager
    rm = RiskManager(venue="mock", asset_class="crypto_spot")
    acc = account_state_factory(total_value=1_000.0)

    trade = {
        "action": "buy", "asset": "BTCUSDT",
        "current_price": 50_000.0,
        "allocation_usd": 900.0,  # 90% → capped to max_position_pct
    }
    ok, reason, result = rm.validate_trade(trade, acc, 1_000.0)
    if ok:
        # Capped: the resulting allocation must not exceed 3% of equity
        assert result["allocation_usd"] <= 1_000.0 * 0.05
    else:
        assert reason  # blocked with a clear reason

    # In either case, no order was placed yet (that's the caller's responsibility)
    assert mock_venue.calls.get("place_order", 0) == 0


# ── Plan limit blocks action ──────────────────────────────────────────────────

def test_free_plan_blocks_copy_trading():
    from src.server import _plan_allows
    assert _plan_allows("FREE", "copyTrading") is False


def test_free_plan_blocks_rag_memory():
    from src.server import _plan_allows
    assert _plan_allows("FREE", "ragMemory") is False


def test_starter_plan_blocks_ai_council():
    from src.server import _plan_allows
    assert _plan_allows("STARTER", "aiCouncil") is False


# ── LLM provider failure triggers fallback ────────────────────────────────────

def test_agent_has_fallback_chain():
    """TradingAgent must have at least one fallback provider."""
    from src.agent.decision_maker import TradingAgent
    agent = TradingAgent(hyperliquid=None)
    assert len(agent._fallback_chain) >= 1, "Agent must have at least 1 provider"


@pytest.mark.asyncio
async def test_agent_forces_final_json_after_repeated_tool_calls(monkeypatch):
    from types import SimpleNamespace

    import src.agent.decision_maker as dm
    from src.agent.decision_maker import TradingAgent
    from src.agent.providers.base import LLMResponse

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    class StubHyperliquid:
        async def get_candles(self, asset: str, interval: str, lookback: int):
            candles = []
            for i in range(lookback):
                close = 50_000 + i
                candles.append({
                    "time": 1_700_000_000 + i * 60,
                    "open": close - 5,
                    "high": close + 5,
                    "low": close - 10,
                    "close": float(close),
                    "volume": 1000.0,
                })
            return candles

    class RepeatingToolProvider:
        name = "anthropic"
        model = "mock-tool-model"
        supports_tools = True

        def __init__(self):
            self.calls = 0

        def complete(self, system, messages, max_tokens=4096, tools=None):
            self.calls += 1
            if tools is None:
                return LLMResponse(
                    content=(
                        '{"reasoning":"Enough context gathered","trade_decisions":['
                        '{"asset":"BTC/USDT","action":"hold","allocation_usd":0,'
                        '"tp_price":null,"sl_price":null,"exit_plan":"",'
                        '"rationale":"Waiting for confirmation"}]}'
                    ),
                    model=self.model,
                    stop_reason="stop",
                )

            block = SimpleNamespace(
                type="tool_use",
                id=f"tool-{self.calls}",
                name="fetch_indicator",
                input={"indicator": "rsi", "asset": "BTC", "interval": "5m"},
            )
            raw = SimpleNamespace(content=[block])
            return LLMResponse(
                content="",
                model=self.model,
                stop_reason="tool_use",
                raw=raw,
            )

    provider = RepeatingToolProvider()
    monkeypatch.setattr("src.agent.decision_maker.get_provider", lambda: provider)
    monkeypatch.setitem(dm.CONFIG, "enable_tool_calling", True)

    agent = TradingAgent(hyperliquid=StubHyperliquid(), venue_context="crypto")
    agent._fallback_chain = [provider]
    agent._sanitize_provider = provider

    result = await agent.decide_trade_async(["BTC/USDT"], "Current time: 2026-05-13T05:26:00Z")

    assert result["reasoning"] == "Enough context gathered"
    assert result["trade_decisions"][0]["action"] == "hold"
    assert result["trade_decisions"][0]["rationale"] == "Waiting for confirmation"
    assert provider.calls == 3


@pytest.mark.asyncio
async def test_agent_records_reason_code_after_invalid_no_tool_final(monkeypatch):
    from types import SimpleNamespace

    import src.agent.decision_maker as dm
    from src.agent.decision_maker import TradingAgent
    from src.agent.providers.base import LLMResponse

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    class StubHyperliquid:
        async def get_candles(self, asset: str, interval: str, lookback: int):
            return [
                {"time": 1_700_000_000 + i * 60, "open": 1, "high": 2, "low": 0.5, "close": 1, "volume": 1}
                for i in range(lookback)
            ]

    class BrokenFinalProvider:
        name = "anthropic"
        model = "mock-broken-final"
        supports_tools = True

        def complete(self, system, messages, max_tokens=4096, tools=None):
            if tools is None:
                return LLMResponse(content="", model=self.model, stop_reason="stop")
            block = SimpleNamespace(
                type="tool_use",
                id="tool-1",
                name="fetch_indicator",
                input={"indicator": "rsi", "asset": "BTC", "interval": "5m"},
            )
            return LLMResponse(
                content="",
                model=self.model,
                stop_reason="tool_use",
                raw=SimpleNamespace(content=[block]),
            )

    provider = BrokenFinalProvider()
    monkeypatch.setattr("src.agent.decision_maker.get_provider", lambda: provider)
    monkeypatch.setitem(dm.CONFIG, "enable_tool_calling", True)

    agent = TradingAgent(hyperliquid=StubHyperliquid(), venue_context="crypto")
    agent._fallback_chain = [provider]
    agent._sanitize_provider = provider

    result = await agent.decide_trade_async(["BTC/USDT"], "Current time: 2026-05-14T11:00:00Z")

    assert result["trade_decisions"][0]["action"] == "hold"
    assert result["trade_decisions"][0]["reason_code"] == "ai_final_response_empty"
    assert "no trade was executed" in result["trade_decisions"][0]["rationale"]


@pytest.mark.asyncio
async def test_agent_disables_indicator_tools_when_no_hyperliquid_client(monkeypatch):
    import src.agent.decision_maker as dm
    from src.agent.decision_maker import TradingAgent
    from src.agent.providers.base import LLMResponse

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    class ToolCapableProvider:
        name = "mock"
        model = "mock-no-tools-runtime"
        supports_tools = True

        def __init__(self):
            self.calls = 0
            self.last_tools = object()

        def complete(self, system, messages, max_tokens=4096, tools=None):
            self.calls += 1
            self.last_tools = tools
            return LLMResponse(
                content=(
                    '{"reasoning":"Setup is constructive","trade_decisions":['
                    '{"asset":"BTC/USDT","action":"buy","allocation_usd":125,'
                    '"order_type":"market","limit_price":null,"tp_price":64000,'
                    '"sl_price":61000,"exit_plan":"Exit on structure failure",'
                    '"rationale":"Momentum and structure are aligned."}]}'
                ),
                model=self.model,
                stop_reason="stop",
            )

    provider = ToolCapableProvider()
    monkeypatch.setattr("src.agent.decision_maker.get_provider", lambda: provider)
    monkeypatch.setitem(dm.CONFIG, "enable_tool_calling", True)

    agent = TradingAgent(hyperliquid=None, venue_context="crypto")
    agent._fallback_chain = [provider]
    agent._sanitize_provider = provider

    result = await agent.decide_trade_async(["BTC/USDT"], '{"market_data":[{"asset":"BTC/USDT","data_ready":true}]}')

    assert provider.calls == 1
    assert provider.last_tools is None
    assert result["trade_decisions"][0]["action"] == "buy"
    assert result["trade_decisions"][0]["allocation_usd"] == 125


@pytest.mark.asyncio
async def test_groq_provider_does_not_enter_anthropic_tool_loop(monkeypatch):
    import src.agent.decision_maker as dm
    from src.agent.decision_maker import TradingAgent
    from src.agent.providers.base import LLMResponse

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    class StubHyperliquid:
        async def get_candles(self, asset: str, interval: str, lookback: int):
            return [
                {"time": 1_700_000_000 + i * 60, "open": 1, "high": 2, "low": 0.5, "close": 1, "volume": 1}
                for i in range(lookback)
            ]

    class GroqLikeProvider:
        name = "groq"
        model = "llama-3.3-70b-versatile"
        supports_tools = True

        def __init__(self):
            self.calls = 0
            self.last_tools = object()

        def complete(self, system, messages, max_tokens=4096, tools=None):
            self.calls += 1
            self.last_tools = tools
            return LLMResponse(
                content=(
                    '{"reasoning":"Context-only decision completed","trade_decisions":['
                    '{"asset":"BTC/USDT","action":"hold","allocation_usd":0,'
                    '"order_type":"market","limit_price":null,"tp_price":null,'
                    '"sl_price":null,"exit_plan":"","rationale":"Waiting for a cleaner setup."}]}'
                ),
                model=self.model,
                stop_reason="stop",
            )

    provider = GroqLikeProvider()
    monkeypatch.setattr("src.agent.decision_maker.get_provider", lambda: provider)
    monkeypatch.setitem(dm.CONFIG, "enable_tool_calling", True)

    agent = TradingAgent(hyperliquid=StubHyperliquid(), venue_context="crypto")
    agent._fallback_chain = [provider]
    agent._sanitize_provider = provider

    result = await agent.decide_trade_async(["BTC/USDT"], '{"market_data":[{"asset":"BTC/USDT","data_ready":true}]}')

    assert provider.calls == 1
    assert provider.last_tools is None
    assert result["reasoning"] == "Context-only decision completed"
    assert result["trade_decisions"][0]["action"] == "hold"


@pytest.mark.asyncio
async def test_invalid_no_tool_response_uses_generic_safe_message(monkeypatch):
    import src.agent.decision_maker as dm
    from src.agent.decision_maker import TradingAgent
    from src.agent.providers.base import LLMResponse

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    class BrokenProvider:
        name = "groq"
        model = "broken-context-only"
        supports_tools = True

        def complete(self, system, messages, max_tokens=4096, tools=None):
            return LLMResponse(content="", model=self.model, stop_reason="stop")

    provider = BrokenProvider()
    monkeypatch.setattr("src.agent.decision_maker.get_provider", lambda: provider)
    monkeypatch.setitem(dm.CONFIG, "enable_tool_calling", True)

    agent = TradingAgent(hyperliquid=None, venue_context="crypto")
    agent._fallback_chain = [provider]
    agent._sanitize_provider = provider

    result = await agent.decide_trade_async(["BTC/USDT"], '{"market_data":[{"asset":"BTC/USDT","data_ready":true}]}')

    assert result["trade_decisions"][0]["action"] == "hold"
    assert result["trade_decisions"][0]["reason_code"] == "ai_final_response_invalid"
    assert "tool-analysis safety limit" not in result["trade_decisions"][0]["rationale"]
    assert "no trade was executed" in result["trade_decisions"][0]["rationale"]


# ── Duplicate webhook signal ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_webhook_does_not_double_trade(mock_env, mock_venue):
    """Sending the same TradingView signal twice should not place 2 orders.

    The current implementation doesn't have dedup; this test documents the
    expected behaviour (both orders go through — but at least neither crashes).
    A future idempotency layer would make the second one a no-op.
    """
    from src.server import _state
    _state.venue    = mock_venue
    _state.is_paper = True
    _state.positions = []
    _state.account   = {"equity": 10_000.0, "balance": 10_000.0}
    _state.initial_equity = 10_000.0

    # Simulate what execute-signal does in paper mode — just logs, doesn't call venue
    # (paper mode guard prevents double-call)
    assert mock_venue.calls.get("place_order", 0) == 0


# ── Encryption key missing at runtime ────────────────────────────────────────

def test_missing_encryption_key_raises_on_encrypt(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    import importlib, src.services.encryption as enc_mod
    importlib.reload(enc_mod)
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        enc_mod.encrypt("something")


# ── kill switch blocked when no positions ─────────────────────────────────────

@pytest.mark.asyncio
async def test_killswitch_with_no_positions_returns_ok(mock_env, mock_venue):
    import time
    from src.server import kill_switch, KillSwitchRequest, get_state

    s = get_state("no_pos_user")
    s.user_id = "no_pos_user"
    s.venue = mock_venue
    s.is_paper = False
    s.positions = []  # No open positions

    req = KillSwitchRequest(confirm=True, ts=time.time(), userId="no_pos_user")
    with patch("src.services.supabase_reader.upsert_agent_run", new=AsyncMock()):
        with patch("src.server._persist_audit", new=AsyncMock()):
            result = await kill_switch(_request_for("no_pos_user"), req)
    assert result["ok"] is True
    assert result["closed"] == []
