"""AI Council — parallel 3-LLM consensus voting.

Fires Groq + Claude + Gemini in parallel. A trade is only executed if
≥2 of the 3 models agree on the same action (buy/sell/hold).

Env vars required:
    GROQ_API_KEY        — for Groq (free)
    ANTHROPIC_API_KEY   — for Claude
    GEMINI_API_KEY      — for Gemini (free)

If fewer than 2 providers are configured the council degrades gracefully:
  - 1 provider → that provider's decision passes unconditionally
  - 0 providers → hold everything
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from src.config_loader import CONFIG

logger = logging.getLogger("quantatraderai.council")

COUNCIL_PROVIDERS = [
    {"name": "groq",      "key_config": "groq_api_key",      "model": "llama-3.3-70b-versatile"},
    {"name": "anthropic", "key_config": "anthropic_api_key",  "model": "claude-haiku-4-5-20251001"},
    {"name": "gemini",    "key_config": "gemini_api_key",     "model": "gemini-2.0-flash-exp"},
]


@dataclass
class MemberOpinion:
    provider: str
    model:    str
    action:   str          # buy | sell | hold
    allocation_usd: float
    confidence: float      # 0–1
    rationale:  str
    raw_decisions: list[dict] = field(default_factory=list)
    error: str | None = None


@dataclass
class CouncilDecision:
    asset:          str
    action:         str              # agreed action
    allocation_usd: float            # median of agreeing providers
    confidence:     float            # fraction that agreed
    opinions:       list[MemberOpinion]
    rationale:      str
    sl_price:       float | None = None
    tp_price:       float | None = None
    deadlock:       bool = False     # True if no majority reached


def _available_providers() -> list[dict]:
    available = []
    for p in COUNCIL_PROVIDERS:
        key = CONFIG.get(p["key_config"])
        if key and not key.startswith("your-") and not key.startswith("dummy"):
            available.append(p)
    return available


async def _ask_provider(provider_cfg: dict, assets: list[str], context: str) -> MemberOpinion:
    """Ask a single provider for trade decisions and return its opinion.

    provider.complete() is a blocking HTTP call.  Running it via asyncio.to_thread
    lets asyncio.gather() fire all three council members truly in parallel instead
    of sequentially, cutting council latency from ~3×single to ~1×single.
    """
    import asyncio as _asyncio
    from src.agent.providers.factory import get_provider
    try:
        provider = get_provider(provider_name=provider_cfg["name"], model=provider_cfg["model"])
        system = (
            "You are a disciplined quantitative trader. Given market context, "
            "return ONLY valid JSON with this structure:\n"
            '{"trade_decisions":[{"asset":"<symbol>","action":"buy|sell|hold",'
            '"allocation_usd":<number>,"sl_price":<number|null>,"tp_price":<number|null>,'
            '"rationale":"<brief>","confidence":<0.0-1.0>}]}'
        )
        import json
        messages = [{"role": "user", "content": f"Assets: {json.dumps(assets)}\n\nContext:\n{context}"}]
        # Run blocking HTTP call in a thread so council members fire in parallel
        resp = await _asyncio.to_thread(
            provider.complete, system=system, messages=messages, max_tokens=1024
        )
        raw_text = resp.content if hasattr(resp, "content") else str(resp)
        # Find JSON in the response
        start = raw_text.find("{")
        end   = raw_text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON found in response")
        parsed = json.loads(raw_text[start:end])
        decisions = parsed.get("trade_decisions", [])
        if not decisions:
            return MemberOpinion(
                provider=provider_cfg["name"], model=provider_cfg["model"],
                action="hold", allocation_usd=0, confidence=0.5,
                rationale="No decisions returned",
            )
        d = decisions[0]
        return MemberOpinion(
            provider=provider_cfg["name"], model=provider_cfg["model"],
            action=d.get("action", "hold"),
            allocation_usd=float(d.get("allocation_usd") or 0),
            confidence=float(d.get("confidence") or 0.5),
            rationale=str(d.get("rationale") or ""),
            raw_decisions=decisions,
        )
    except Exception as e:
        logger.warning("Council member %s error: %s", provider_cfg["name"], e)
        return MemberOpinion(
            provider=provider_cfg["name"], model=provider_cfg["model"],
            action="hold", allocation_usd=0, confidence=0.0,
            rationale="error", error=str(e),
        )


async def council_decide(assets: list[str], context: str) -> list[CouncilDecision]:
    """Fire all available providers in parallel and vote per asset.

    Returns a CouncilDecision per asset. If a majority (≥ ceil(n/2)+1) agrees
    the decision executes; otherwise action="hold" with deadlock=True.
    """
    providers = _available_providers()
    if not providers:
        logger.warning("No council providers configured — holding all")
        return [
            CouncilDecision(
                asset=a, action="hold", allocation_usd=0,
                confidence=0, opinions=[], rationale="No providers configured",
                deadlock=True,
            )
            for a in assets
        ]

    # Fire all providers in parallel
    tasks   = [_ask_provider(p, assets, context) for p in providers]
    opinions: list[MemberOpinion] = await asyncio.gather(*tasks)

    n = len(opinions)
    threshold = max(2, (n // 2) + 1)  # majority: 2/3, 3/3, etc.

    decisions: list[CouncilDecision] = []
    for asset in assets:
        # Collect each provider's opinion for this asset
        asset_opinions = []
        for op in opinions:
            # Find the matching asset in raw_decisions
            asset_dec = next(
                (d for d in op.raw_decisions if d.get("asset", "").upper() == asset.upper()),
                None,
            )
            if asset_dec:
                asset_opinions.append(MemberOpinion(
                    provider=op.provider, model=op.model,
                    action=asset_dec.get("action", "hold"),
                    allocation_usd=float(asset_dec.get("allocation_usd") or 0),
                    confidence=float(asset_dec.get("confidence") or 0.5),
                    rationale=str(asset_dec.get("rationale") or ""),
                    raw_decisions=[asset_dec],
                ))
            else:
                asset_opinions.append(op)

        # Count votes per action
        vote_counts: dict[str, int] = {}
        for op in asset_opinions:
            vote_counts[op.action] = vote_counts.get(op.action, 0) + 1

        best_action = max(vote_counts, key=lambda a: vote_counts[a])
        best_votes  = vote_counts[best_action]
        deadlock    = best_votes < threshold

        if deadlock:
            action = "hold"
            rationale = (
                f"Council deadlock: {vote_counts}. "
                f"Required {threshold}/{n} — holding."
            )
            alloc = 0.0
            sl = tp = None
        else:
            action    = best_action
            agreeing  = [op for op in asset_opinions if op.action == action]
            allocs    = [op.allocation_usd for op in agreeing if op.allocation_usd > 0]
            alloc     = sorted(allocs)[len(allocs)//2] if allocs else 0.0
            rationale = " | ".join(f"{op.provider}: {op.rationale[:60]}" for op in agreeing)
            # Use SL/TP from first agreeing member that has them
            sl = tp = None
            for op in agreeing:
                for d in op.raw_decisions:
                    if d.get("sl_price"): sl = float(d["sl_price"])
                    if d.get("tp_price"): tp = float(d["tp_price"])
                    if sl and tp:
                        break
                if sl and tp:
                    break

        confidence = best_votes / n
        decisions.append(CouncilDecision(
            asset=asset, action=action, allocation_usd=alloc,
            confidence=confidence, opinions=asset_opinions,
            rationale=rationale, sl_price=sl, tp_price=tp, deadlock=deadlock,
        ))
        logger.info(
            "COUNCIL %s: %s (%.0f%% agreement) %s",
            asset, action.upper(), confidence * 100,
            "DEADLOCK" if deadlock else "",
        )

    return decisions
