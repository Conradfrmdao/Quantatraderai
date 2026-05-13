"""Role-based AI council for low-cost multi-model trade review.

The council is organized around four distinct responsibilities:
  - market_analyst: directional thesis and structure
  - risk_officer: hard risk veto and stop/target discipline
  - execution_arbiter: whether the setup is executable right now
  - portfolio_allocator: conservative sizing across the whole account

Free/default path:
  - Groq
  - Gemini
  - optional Ollama if explicitly enabled

Optional paid escalation:
  - Anthropic/OpenRouter chair only for deadlocks or high-risk disagreement

The rest of the app still calls `council_decide()` and receives one
CouncilDecision per asset, so this module can evolve without disturbing the
execution loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from src.config_loader import CONFIG

logger = logging.getLogger("quantatraderai.council")

_SYMBOL_RE = re.compile(r"[^A-Z0-9]")

DEFAULT_MODELS: dict[str, str] = {
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.0-flash-exp",
    "anthropic": "claude-haiku-4-5-20251001",
    "ollama": os.getenv("COUNCIL_OLLAMA_MODEL", "qwen2.5:14b"),
    "openrouter": "deepseek/deepseek-r1:free",
}

ROLE_PROMPTS: dict[str, str] = {
    "market_analyst": (
        "You are the MARKET ANALYST on a quantitative trading committee. "
        "Focus on directional edge, structure, momentum, trend quality, and whether "
        "the setup is strong enough to act. Do not be timid, but do not invent edge."
    ),
    "risk_officer": (
        "You are the RISK OFFICER on a trading committee. Your first duty is capital preservation. "
        "Use veto=true when the trade should be blocked because the setup is unsafe, overextended, "
        "poorly defined, or inconsistent with the supplied risk/account context."
    ),
    "execution_arbiter": (
        "You are the EXECUTION ARBITER on a trading committee. Decide whether the trade is executable "
        "right now, whether confirmation is sufficient, and whether the entry should wait."
    ),
    "portfolio_allocator": (
        "You are the PORTFOLIO ALLOCATOR on a trading committee. Focus on conservative sizing, "
        "portfolio fit, existing exposure, and whether capital should stay reserved."
    ),
    "committee_chair": (
        "You are the CHAIR of a trading committee. You only intervene when specialist roles disagree "
        "or risk is elevated. Resolve the conflict conservatively and prefer hold over weak conviction."
    ),
}


@dataclass(frozen=True)
class RoleConfig:
    role: str
    provider_order: tuple[str, ...]
    weight: float = 1.0


ROLE_CONFIGS: tuple[RoleConfig, ...] = (
    RoleConfig("market_analyst", ("groq", "gemini", "ollama", "anthropic"), 1.1),
    RoleConfig("risk_officer", ("gemini", "groq", "ollama", "anthropic"), 1.15),
    RoleConfig("execution_arbiter", ("ollama", "groq", "gemini", "anthropic"), 1.0),
    RoleConfig("portfolio_allocator", ("gemini", "ollama", "groq", "anthropic"), 0.95),
)

CHAIR_PROVIDER_ORDER: tuple[str, ...] = ("anthropic", "openrouter")


@dataclass
class MemberOpinion:
    asset: str
    role: str
    provider: str
    model: str
    action: str          # buy | sell | hold
    allocation_usd: float
    confidence: float    # 0–1
    rationale: str
    raw_decisions: list[dict] = field(default_factory=list)
    error: str | None = None
    veto: bool = False
    weight: float = 1.0
    order_type: str | None = None


@dataclass
class CouncilDecision:
    asset: str
    action: str
    allocation_usd: float
    confidence: float
    opinions: list[MemberOpinion]
    rationale: str
    sl_price: float | None = None
    tp_price: float | None = None
    deadlock: bool = False


def _truthy(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_asset(asset: str | None) -> str:
    return _SYMBOL_RE.sub("", str(asset or "").upper())


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_confidence(value: Any, default: float = 0.5) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(0.0, min(1.0, parsed))


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    parsed = json.loads(text[start:end])
    if not isinstance(parsed, dict):
        raise ValueError("Council response JSON must be an object")
    return parsed


def _provider_is_available(name: str) -> bool:
    lname = name.lower().strip()
    if lname == "groq":
        key = CONFIG.get("groq_api_key") or ""
        return bool(key and not key.startswith("your-") and not key.startswith("dummy"))
    if lname == "gemini":
        key = CONFIG.get("gemini_api_key") or ""
        return bool(key and not key.startswith("your-") and not key.startswith("dummy"))
    if lname == "anthropic":
        key = CONFIG.get("anthropic_api_key") or ""
        return bool(key and not key.startswith("your-") and not key.startswith("dummy"))
    if lname == "openrouter":
        key = CONFIG.get("openrouter_api_key") or ""
        return bool(key and not key.startswith("your-") and not key.startswith("dummy"))
    if lname == "ollama":
        return _truthy(os.getenv("ENABLE_OLLAMA_COUNCIL"), False) or (CONFIG.get("llm_provider") == "ollama")
    return False


def _provider_model(name: str) -> str:
    env_name = f"COUNCIL_{name.upper()}_MODEL"
    return os.getenv(env_name) or DEFAULT_MODELS[name]


def _role_candidates(role_cfg: RoleConfig) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for pname in role_cfg.provider_order:
        if _provider_is_available(pname):
            out.append({"name": pname, "model": _provider_model(pname)})
    return out


def _chair_candidates() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not _truthy(os.getenv("ENABLE_COUNCIL_CHAIR"), True):
        return out
    for pname in CHAIR_PROVIDER_ORDER:
        if _provider_is_available(pname):
            out.append({"name": pname, "model": _provider_model(pname)})
    return out


def _empty_opinion(asset: str, role_cfg: RoleConfig, provider: str, model: str, rationale: str, error: str | None = None) -> MemberOpinion:
    return MemberOpinion(
        asset=asset,
        role=role_cfg.role,
        provider=provider,
        model=model,
        action="hold",
        allocation_usd=0.0,
        confidence=0.0,
        rationale=rationale,
        error=error,
        veto=False,
        weight=role_cfg.weight,
    )


def _build_role_system_prompt(role: str) -> str:
    return (
        f"{ROLE_PROMPTS[role]}\n\n"
        "Return ONLY valid JSON with this structure:\n"
        '{"trade_decisions":[{"asset":"<symbol>","action":"buy|sell|hold",'
        '"allocation_usd":<number>,"sl_price":<number|null>,"tp_price":<number|null>,'
        '"rationale":"<brief>","confidence":<0.0-1.0>,"veto":<true|false>,"order_type":"market|limit|hold"}]}\n'
        "Use veto=true only if the trade should be blocked outright for safety or policy reasons."
    )


def _parse_role_response(
    *,
    role_cfg: RoleConfig,
    provider_name: str,
    provider_model: str,
    assets: list[str],
    payload: dict[str, Any],
) -> list[MemberOpinion]:
    decisions = payload.get("trade_decisions", [])
    if not isinstance(decisions, list):
        raise ValueError("trade_decisions must be a list")

    by_asset = {}
    for item in decisions:
        if not isinstance(item, dict):
            continue
        by_asset[_normalize_asset(item.get("asset"))] = item

    opinions: list[MemberOpinion] = []
    for asset in assets:
        raw = by_asset.get(_normalize_asset(asset))
        if raw is None:
            opinions.append(
                _empty_opinion(
                    asset,
                    role_cfg,
                    provider_name,
                    provider_model,
                    "No decision returned for this asset",
                )
            )
            continue
        action = str(raw.get("action") or "hold").strip().lower()
        if action not in {"buy", "sell", "hold"}:
            action = "hold"
        opinions.append(
            MemberOpinion(
                asset=asset,
                role=role_cfg.role,
                provider=provider_name,
                model=provider_model,
                action=action,
                allocation_usd=max(0.0, _safe_float(raw.get("allocation_usd"), 0.0)),
                confidence=_safe_confidence(raw.get("confidence"), 0.5),
                rationale=str(raw.get("rationale") or "").strip() or "No rationale provided",
                raw_decisions=[raw],
                veto=bool(raw.get("veto")),
                weight=role_cfg.weight,
                order_type=str(raw.get("order_type") or "").strip().lower() or None,
            )
        )
    return opinions


async def _ask_role(role_cfg: RoleConfig, assets: list[str], context: str) -> list[MemberOpinion]:
    """Ask one specialist role, with provider fallback inside that role."""
    from src.agent.providers.factory import get_provider

    candidates = _role_candidates(role_cfg)
    if not candidates:
        logger.warning("No provider available for council role %s", role_cfg.role)
        return [
            _empty_opinion(
                asset,
                role_cfg,
                provider="none",
                model="none",
                rationale="No provider configured for this council role",
                error="no_provider",
            )
            for asset in assets
        ]

    messages = [{"role": "user", "content": f"Assets: {json.dumps(assets)}\n\nContext:\n{context}"}]
    system = _build_role_system_prompt(role_cfg.role)
    last_error: str | None = None

    for candidate in candidates:
        try:
            provider = get_provider(provider_name=candidate["name"], model=candidate["model"])
            resp = await asyncio.to_thread(
                provider.complete,
                system=system,
                messages=messages,
                max_tokens=1024,
            )
            parsed = _extract_json_object(resp.content if hasattr(resp, "content") else str(resp))
            opinions = _parse_role_response(
                role_cfg=role_cfg,
                provider_name=candidate["name"],
                provider_model=candidate["model"],
                assets=assets,
                payload=parsed,
            )
            return opinions
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "Council role %s failed via %s: %s",
                role_cfg.role,
                candidate["name"],
                exc,
            )

    return [
        _empty_opinion(
            asset,
            role_cfg,
            provider=candidates[0]["name"],
            model=candidates[0]["model"],
            rationale="Role failed across all configured providers",
            error=last_error or "provider_error",
        )
        for asset in assets
    ]


def _needs_chair(opinions: list[MemberOpinion]) -> bool:
    non_hold = [op for op in opinions if op.action in {"buy", "sell"}]
    if len(non_hold) < 2:
        return False

    buy = [op for op in non_hold if op.action == "buy"]
    sell = [op for op in non_hold if op.action == "sell"]
    risk = next((op for op in opinions if op.role == "risk_officer"), None)

    if buy and sell:
        return True
    if risk and risk.action == "hold" and risk.confidence >= 0.7:
        return True
    if max(len(buy), len(sell)) < 2:
        return True
    return False


async def _ask_chair(asset: str, context: str, opinions: list[MemberOpinion]) -> MemberOpinion | None:
    """Ask an optional chair model to break deadlocks or elevated-risk disputes."""
    from src.agent.providers.factory import get_provider

    candidates = _chair_candidates()
    if not candidates:
        return None

    role_cfg = RoleConfig("committee_chair", CHAIR_PROVIDER_ORDER, 1.2)
    summary = [
        {
            "role": op.role,
            "provider": op.provider,
            "action": op.action,
            "allocation_usd": op.allocation_usd,
            "confidence": op.confidence,
            "veto": op.veto,
            "rationale": op.rationale[:220],
        }
        for op in opinions
    ]
    user_content = (
        f"Asset: {asset}\n\n"
        f"Specialist opinions:\n{json.dumps(summary)}\n\n"
        f"Full market context:\n{context}"
    )
    system = _build_role_system_prompt("committee_chair")

    for candidate in candidates:
        try:
            provider = get_provider(provider_name=candidate["name"], model=candidate["model"])
            resp = await asyncio.to_thread(
                provider.complete,
                system=system,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=1024,
            )
            parsed = _extract_json_object(resp.content if hasattr(resp, "content") else str(resp))
            chair_opinion = _parse_role_response(
                role_cfg=role_cfg,
                provider_name=candidate["name"],
                provider_model=candidate["model"],
                assets=[asset],
                payload=parsed,
            )[0]
            chair_opinion.confidence = max(chair_opinion.confidence, 0.55)
            return chair_opinion
        except Exception as exc:
            logger.warning("Council chair failed via %s: %s", candidate["name"], exc)
    return None


def _pick_level(opinions: list[MemberOpinion], field_name: str) -> float | None:
    for role in ("risk_officer", "committee_chair", "market_analyst", "execution_arbiter", "portfolio_allocator"):
        for op in opinions:
            if op.role != role or not op.raw_decisions:
                continue
            raw = op.raw_decisions[0]
            value = raw.get(field_name)
            if value is not None:
                return _safe_float(value)
    return None


def _conservative_allocation(supporters: list[MemberOpinion], all_opinions: list[MemberOpinion]) -> float:
    positive = sorted(op.allocation_usd for op in supporters if op.allocation_usd > 0)
    if not positive:
        return 0.0
    base = positive[len(positive) // 2]

    caps = [
        op.allocation_usd
        for op in all_opinions
        if op.role in {"risk_officer", "portfolio_allocator"} and op.allocation_usd > 0
    ]
    if caps:
        base = min(base, min(caps))
    return round(max(0.0, base), 2)


def _vote_support(opinions: list[MemberOpinion], action: str) -> tuple[list[MemberOpinion], float]:
    supporters = [op for op in opinions if op.action == action]
    score = sum(op.weight * max(op.confidence, 0.35) for op in supporters)
    return supporters, score


def _synthesize_asset_decision(asset: str, opinions: list[MemberOpinion], chair_opinion: MemberOpinion | None = None) -> CouncilDecision:
    """Combine specialist role output into a final committee decision."""
    visible_opinions = list(opinions)
    if chair_opinion is not None:
        visible_opinions.append(chair_opinion)

    risk_opinion = next((op for op in opinions if op.role == "risk_officer"), None)
    if risk_opinion and risk_opinion.veto and risk_opinion.confidence >= 0.55:
        return CouncilDecision(
            asset=asset,
            action="hold",
            allocation_usd=0.0,
            confidence=min(0.99, max(0.55, risk_opinion.confidence)),
            opinions=visible_opinions,
            rationale=f"Risk officer veto: {risk_opinion.rationale}",
            deadlock=False,
        )

    buy_supporters, buy_score = _vote_support(visible_opinions, "buy")
    sell_supporters, sell_score = _vote_support(visible_opinions, "sell")

    best_action = "buy" if buy_score >= sell_score else "sell"
    best_supporters = buy_supporters if best_action == "buy" else sell_supporters
    opposite_supporters = sell_supporters if best_action == "buy" else buy_supporters
    best_score = buy_score if best_action == "buy" else sell_score
    opposite_score = sell_score if best_action == "buy" else buy_score

    if len(best_supporters) < 2 or best_score <= opposite_score:
        counts = {
            "buy": len(buy_supporters),
            "sell": len(sell_supporters),
            "hold": len([op for op in visible_opinions if op.action == "hold"]),
        }
        rationale = f"Committee deadlock: {counts}. Waiting for stronger alignment."
        if chair_opinion is not None:
            rationale = f"{rationale} Chair view: {chair_opinion.action.upper()} — {chair_opinion.rationale}"
        return CouncilDecision(
            asset=asset,
            action="hold",
            allocation_usd=0.0,
            confidence=0.0,
            opinions=visible_opinions,
            rationale=rationale,
            deadlock=True,
        )

    average_confidence = sum(op.confidence for op in best_supporters) / len(best_supporters)
    allocation = _conservative_allocation(best_supporters, visible_opinions)
    confidence = min(
        0.99,
        round((average_confidence * 0.65) + (len(best_supporters) / max(3.0, len(visible_opinions))) * 0.35, 4),
    )

    role_summaries = [
        f"{op.role}: {op.rationale[:90]}"
        for op in visible_opinions
        if op.action == best_action or op.role in {"risk_officer", "portfolio_allocator", "committee_chair"}
    ]

    return CouncilDecision(
        asset=asset,
        action=best_action,
        allocation_usd=allocation,
        confidence=confidence,
        opinions=visible_opinions,
        rationale=" | ".join(role_summaries)[:500],
        sl_price=_pick_level(visible_opinions, "sl_price"),
        tp_price=_pick_level(visible_opinions, "tp_price"),
        deadlock=False,
    )


async def council_decide(assets: list[str], context: str) -> list[CouncilDecision]:
    """Run the role-based committee and synthesize one decision per asset."""
    if not assets:
        return []

    if not any(_provider_is_available(name) for name in ("groq", "gemini", "ollama", "anthropic", "openrouter")):
        logger.warning("No council providers configured — holding all")
        return [
            CouncilDecision(
                asset=asset,
                action="hold",
                allocation_usd=0.0,
                confidence=0.0,
                opinions=[],
                rationale="No council providers configured",
                deadlock=True,
            )
            for asset in assets
        ]

    role_results = await asyncio.gather(*[_ask_role(role_cfg, assets, context) for role_cfg in ROLE_CONFIGS])
    flattened = [op for role_group in role_results for op in role_group]

    decisions: list[CouncilDecision] = []
    for asset in assets:
        asset_opinions = [op for op in flattened if _normalize_asset(op.asset) == _normalize_asset(asset)]
        chair = await _ask_chair(asset, context, asset_opinions) if _needs_chair(asset_opinions) else None
        decision = _synthesize_asset_decision(asset, asset_opinions, chair)
        logger.info(
            "ROLE-COUNCIL %s: %s (conf=%.2f alloc=%.2f deadlock=%s)",
            asset,
            decision.action.upper(),
            decision.confidence,
            decision.allocation_usd,
            decision.deadlock,
        )
        decisions.append(decision)

    return decisions
