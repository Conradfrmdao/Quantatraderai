from __future__ import annotations

import pytest


def _opinion(
    *,
    role: str,
    action: str,
    confidence: float,
    allocation_usd: float,
    rationale: str = "ok",
    veto: bool = False,
    provider: str = "groq",
    raw: dict | None = None,
):
    from src.agent.council import MemberOpinion

    return MemberOpinion(
        asset="BTC/USDT",
        role=role,
        provider=provider,
        model="mock-model",
        action=action,
        allocation_usd=allocation_usd,
        confidence=confidence,
        rationale=rationale,
        raw_decisions=[raw or {}],
        veto=veto,
        weight=1.0,
    )


def test_synthesize_asset_decision_respects_risk_veto():
    import src.agent.council as council

    opinions = [
        _opinion(role="market_analyst", action="buy", confidence=0.82, allocation_usd=700, rationale="trend is strong"),
        _opinion(role="execution_arbiter", action="buy", confidence=0.74, allocation_usd=650, rationale="entry is executable"),
        _opinion(role="portfolio_allocator", action="buy", confidence=0.68, allocation_usd=400, rationale="sizing is acceptable"),
        _opinion(role="risk_officer", action="hold", confidence=0.9, allocation_usd=0, rationale="volatility too elevated", veto=True),
    ]

    decision = council._synthesize_asset_decision("BTC/USDT", opinions)

    assert decision.action == "hold"
    assert decision.deadlock is False
    assert decision.allocation_usd == 0.0
    assert "Risk officer veto" in decision.rationale


def test_synthesize_asset_decision_uses_conservative_allocation_and_risk_levels():
    import src.agent.council as council

    opinions = [
        _opinion(
            role="market_analyst",
            action="buy",
            confidence=0.84,
            allocation_usd=800,
            rationale="trend alignment",
            raw={"sl_price": 64000.0, "tp_price": 69000.0},
        ),
        _opinion(role="execution_arbiter", action="buy", confidence=0.75, allocation_usd=700, rationale="pullback filled"),
        _opinion(role="portfolio_allocator", action="buy", confidence=0.71, allocation_usd=400, rationale="reserve some cash"),
        _opinion(
            role="risk_officer",
            action="buy",
            confidence=0.78,
            allocation_usd=300,
            rationale="risk acceptable with tight stop",
            raw={"sl_price": 64500.0, "tp_price": 70000.0},
        ),
    ]

    decision = council._synthesize_asset_decision("BTC/USDT", opinions)

    assert decision.action == "buy"
    assert decision.deadlock is False
    assert decision.allocation_usd == 300.0
    assert decision.sl_price == 64500.0
    assert decision.tp_price == 70000.0
    assert decision.confidence > 0.6


@pytest.mark.asyncio
async def test_council_decide_uses_chair_to_break_deadlock(monkeypatch):
    import src.agent.council as council

    async def fake_ask_role(role_cfg, assets, context):
        if role_cfg.role == "market_analyst":
            return [_opinion(role="market_analyst", action="buy", confidence=0.81, allocation_usd=500, rationale="breakout confirmed")]
        if role_cfg.role == "execution_arbiter":
            return [_opinion(role="execution_arbiter", action="sell", confidence=0.72, allocation_usd=450, rationale="failed breakout")]
        if role_cfg.role == "risk_officer":
            return [_opinion(role="risk_officer", action="hold", confidence=0.74, allocation_usd=250, rationale="risk mixed")]
        return [_opinion(role="portfolio_allocator", action="hold", confidence=0.63, allocation_usd=250, rationale="keep capital reserved")]

    async def fake_ask_chair(asset, context, opinions):
        return _opinion(
            role="committee_chair",
            action="buy",
            confidence=0.79,
            allocation_usd=300,
            rationale="market analyst thesis is stronger than the execution objection",
            provider="anthropic",
        )

    monkeypatch.setattr(council, "_ask_role", fake_ask_role)
    monkeypatch.setattr(council, "_ask_chair", fake_ask_chair)

    results = await council.council_decide(["BTC/USDT"], '{"market_data":[]}')

    assert len(results) == 1
    assert results[0].action == "buy"
    assert results[0].deadlock is False
    assert any(op.role == "committee_chair" for op in results[0].opinions)
