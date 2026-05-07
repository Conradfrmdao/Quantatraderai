"""Strategy Personas — named AI trading personalities.

Each persona wraps the core TradingAgent with a distinct:
  - Trading style (momentum / scalping / swing / news-driven)
  - Risk tolerance (aggressive / moderate / conservative)
  - Indicator focus (which signals to weight most)
  - System prompt addendum (injected into every LLM call)

Users pick one in Settings. The selected persona is stored in UserSettings.strategyType
and loaded by _do_start() to configure the agent.

Personas:
  MOMENTUM_HUNTER  — rides strong trends, uses RSI + MACD + EMA alignment
  SCALPER_AI       — fast in/out on short-term signals, tight SL, frequent trades
  SWING_MASTER     — 1-3 day holds, macro + HTF confluence, wider SL
  NEWS_REACTOR     — sentiment-driven, reacts to economic calendar + fear/greed index
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

StrategyStyle   = Literal["momentum", "scalping", "swing", "news"]
RiskProfile     = Literal["aggressive", "moderate", "conservative"]
StrategyTypeId  = Literal[
    "MOMENTUM_HUNTER", "SCALPER_AI", "SWING_MASTER", "NEWS_REACTOR"
]


@dataclass
class StrategyPersona:
    id:             StrategyTypeId
    name:           str
    tagline:        str
    description:    str
    style:          StrategyStyle
    risk_profile:   RiskProfile
    typical_hold:   str              # e.g. "< 4 hours", "1-3 days"
    win_rate_range: str              # indicative e.g. "55-65%"
    indicator_focus: list[str]

    # Risk manager overrides when this persona is active
    risk_overrides: dict = field(default_factory=dict)

    # Addendum injected at the TOP of every LLM system prompt
    prompt_addendum: str = ""

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "name":             self.name,
            "tagline":          self.tagline,
            "description":      self.description,
            "style":            self.style,
            "riskProfile":      self.risk_profile,
            "typicalHold":      self.typical_hold,
            "winRateRange":     self.win_rate_range,
            "indicatorFocus":   self.indicator_focus,
        }


PERSONAS: dict[StrategyTypeId, StrategyPersona] = {

    "MOMENTUM_HUNTER": StrategyPersona(
        id="MOMENTUM_HUNTER",
        name="Momentum Hunter",
        tagline="Ride the wave — catch strong trends early",
        description=(
            "Looks for assets with strong directional momentum confirmed "
            "by RSI, MACD, and EMA alignment. Enters after a pullback to "
            "a key level and holds until momentum fades. Best in trending markets."
        ),
        style="momentum",
        risk_profile="moderate",
        typical_hold="4-24 hours",
        win_rate_range="indicative only — backtest before live use",
        indicator_focus=["RSI", "MACD", "EMA", "ATR"],
        risk_overrides={
            "max_position_pct":  3.5,
            "mandatory_sl_pct":  2.0,
        },
        prompt_addendum=(
            "PERSONA: Momentum Hunter.\n"
            "STYLE: Trend-following momentum trader. "
            "Only trade when RSI is above 50 (bull momentum) or below 50 (bear momentum) "
            "AND MACD histogram is accelerating in the same direction. "
            "Do NOT chase overextended moves (RSI > 75 for buys or < 25 for sells). "
            "Wait for the first pullback after a trend break.\n"
        ),
    ),

    "SCALPER_AI": StrategyPersona(
        id="SCALPER_AI",
        name="Scalper AI",
        tagline="Fast execution, tight stops, high frequency",
        description=(
            "High-frequency strategy targeting 0.2-0.5% moves. Uses RSI extremes and "
            "Bollinger Band mean-reversion. Tight stop-losses, small allocations, "
            "many small wins. Best on liquid crypto pairs in ranging markets."
        ),
        style="scalping",
        risk_profile="aggressive",
        typical_hold="< 2 hours",
        win_rate_range="indicative only — backtest before live use",
        indicator_focus=["RSI", "Bollinger Bands", "Stoch-RSI", "Volume"],
        risk_overrides={
            "max_position_pct":        2.0,
            "mandatory_sl_pct":        1.0,
            "max_loss_per_position_pct": 3.0,
            "max_concurrent_positions": 3,
        },
        prompt_addendum=(
            "PERSONA: Scalper AI.\n"
            "STYLE: Mean-reversion scalper. Target small moves (0.2-0.5% profit). "
            "Enter ONLY when RSI < 28 (oversold) for buys or RSI > 72 (overbought) for sells. "
            "Confirm with Stoch-RSI. Set tight take-profit of 0.4%, tight stop-loss of 0.8%. "
            "Close positions quickly. Never let a scalp turn into a swing. "
            "Max 3 concurrent positions.\n"
        ),
    ),

    "SWING_MASTER": StrategyPersona(
        id="SWING_MASTER",
        name="Swing Master",
        tagline="Patience pays — catch the big multi-day moves",
        description=(
            "Multi-timeframe analysis targeting 2-8% moves over 1-3 days. "
            "Uses HTF confluence (4h + 1d), support/resistance levels, and "
            "broader risk management. Lower win rate but larger R:R per trade."
        ),
        style="swing",
        risk_profile="conservative",
        typical_hold="1-3 days",
        win_rate_range="indicative only — backtest before live use",
        indicator_focus=["EMA", "Support/Resistance", "Volume", "Bollinger Bands"],
        risk_overrides={
            "max_position_pct":  5.0,
            "mandatory_sl_pct":  3.5,
            "max_leverage":      1.5,
            "max_concurrent_positions": 2,
        },
        prompt_addendum=(
            "PERSONA: Swing Master.\n"
            "STYLE: Multi-day swing trader with patience. "
            "Only trade high-conviction setups — 4h and 1d trend must align. "
            "Look for price at key support/resistance with RSI divergence. "
            "Target 3-7% profit per trade. Use wider stop-loss (3%). "
            "Quality over quantity — maximum 1 new trade per 8 hours. "
            "Do NOT trade choppy/ranging markets.\n"
        ),
    ),

    "NEWS_REACTOR": StrategyPersona(
        id="NEWS_REACTOR",
        name="News Reactor",
        tagline="Trade the narrative — sentiment drives price",
        description=(
            "Prioritises macro news, economic calendar events, and crypto sentiment "
            "(fear/greed index) over pure technical signals. Pauses before major events "
            "and capitalises on post-event volatility. Requires PRO plan for full signal access."
        ),
        style="news",
        risk_profile="aggressive",
        typical_hold="1-8 hours",
        win_rate_range="indicative only — backtest before live use",
        indicator_focus=["News Sentiment", "Fear/Greed", "Economic Calendar", "RSI"],
        risk_overrides={
            "max_position_pct":  3.0,
            "mandatory_sl_pct":  2.5,
        },
        prompt_addendum=(
            "PERSONA: News Reactor.\n"
            "STYLE: Sentiment and macro event trader. "
            "ALWAYS check the macro_sentiment context before deciding. "
            "If crypto_fear_greed < 20 (extreme fear): look for BUY opportunities (contrarian). "
            "If crypto_fear_greed > 80 (extreme greed): look for SELL/SHORT opportunities. "
            "If a major economic event is within 2 hours: hold/skip until after the release. "
            "Weight news_sentiment 3x more than technical indicators.\n"
        ),
    ),
}


def get_persona(strategy_type: str | None) -> StrategyPersona:
    """Return the persona for a strategy type, defaulting to MOMENTUM_HUNTER."""
    return PERSONAS.get(strategy_type or "MOMENTUM_HUNTER",
                        PERSONAS["MOMENTUM_HUNTER"])


def build_persona_prompt(strategy_type: str | None) -> str:
    """Return the prompt addendum to prepend to the LLM system prompt."""
    return get_persona(strategy_type).prompt_addendum


def get_risk_overrides(strategy_type: str | None) -> dict:
    """Return risk limit overrides for this persona (merged into RiskManager.config)."""
    return get_persona(strategy_type).risk_overrides.copy()


def list_personas() -> list[dict]:
    return [p.to_dict() for p in PERSONAS.values()]
