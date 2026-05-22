"""Decision-making agent that orchestrates LLM prompts and indicator lookups.

Supports multiple LLM providers via src/agent/providers/:
  anthropic  — Claude (best quality)                        PAID
  bedrock    — Claude through AWS Bedrock credits/quotas
  groq       — Llama 3.3 70B / 8B, Gemma2                  FREE
  gemini     — Gemini 2.0 Flash / 1.5 Flash                 FREE
  ollama     — any local model (llama3, mistral, …)         FREE (local)
  openrouter — DeepSeek-R1, Llama, Mistral and more         FREE models

Set LLM_PROVIDER and LLM_MODEL in .env.
"""

import ast
import asyncio
import json
import logging
import os
import pathlib
import re
from datetime import datetime
from typing import Any

from src.ai.errors import AIError, AIErrorCode
from src.ai.governance import AIRequestContext, governed_complete, new_trace_id
from src.ai.plan_policy import get_ai_plan_policy
from src.ai.redaction import redact_text
from src.agent.providers.factory import get_provider
from src.config_loader import CONFIG
from src.indicators.local_indicators import compute_all, last_n, latest

_LOG_DIR = pathlib.Path(os.environ.get("LOG_DIR", str(pathlib.Path(__file__).parent.parent.parent / "logs")))
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LLM_LOG = str(_LOG_DIR / "llm_requests.log")
_DEBUG_PROMPTS = os.getenv("AI_PROMPT_DEBUG", "").lower() in {"1", "true", "yes", "on"}


class TradingAgent:
    """High-level trading agent that delegates reasoning to an LLM provider."""

    def __init__(self, hyperliquid=None, venue_context: str = "crypto"):
        self.provider = get_provider()
        self.model = self.provider.model
        self.hyperliquid = hyperliquid
        self.venue_context = venue_context  # "crypto" | "forex" | "stocks"
        self.max_tokens = int(CONFIG.get("max_tokens") or 4096)
        self.system_prompt_addendum: str = ""  # set by strategy persona on agent start

        # C4: Build fallback provider chain. If primary fails, try each in order.
        # Chain: primary → anthropic (if key) → groq (free) → gemini (free)
        self._fallback_chain: list = [self.provider]
        primary_name = (CONFIG.get("llm_provider") or "groq").lower()
        anthropic_key = CONFIG.get("anthropic_api_key") or ""
        groq_key = CONFIG.get("groq_api_key") or ""
        allow_paid_fallbacks = bool(CONFIG.get("allow_paid_ai_fallbacks"))

        if (
            allow_paid_fallbacks
            and primary_name != "anthropic"
            and anthropic_key
            and not anthropic_key.startswith("dummy")
        ):
            try:
                from src.agent.providers.anthropic_provider import AnthropicProvider
                self._fallback_chain.append(AnthropicProvider())
            except Exception:
                pass

        if primary_name != "groq" and groq_key and not groq_key.startswith("dummy"):
            try:
                from src.agent.providers.groq_provider import GroqProvider
                self._fallback_chain.append(GroqProvider())
            except Exception:
                pass

        if primary_name not in ("gemini",):
            try:
                from src.agent.providers.gemini_provider import GeminiProvider
                self._fallback_chain.append(GeminiProvider())
            except Exception:
                pass

        # Fallback sanitizer — use a cheap Anthropic model if available
        sanitize_model = CONFIG.get("sanitize_model")
        if (
            sanitize_model
            and (primary_name == "anthropic" or allow_paid_fallbacks)
            and anthropic_key
            and not anthropic_key.startswith("dummy")
        ):
            try:
                from src.agent.providers.anthropic_provider import AnthropicProvider
                self._sanitize_provider = AnthropicProvider(model=sanitize_model)
            except Exception:
                self._sanitize_provider = self.provider
        else:
            self._sanitize_provider = self.provider

        logging.info(
            "TradingAgent using provider=%s model=%s fallback_chain=%s",
            self.provider.name, self.provider.model,
            [p.name for p in self._fallback_chain[1:]],
        )

    def decide_trade(self, assets, context, ai_context: AIRequestContext | None = None, stream_handler=None):
        """Sync wrapper for tests/CLI paths that are not already async."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.decide_trade_async(assets, context, ai_context=ai_context, stream_handler=stream_handler))
        raise RuntimeError("decide_trade() cannot be called from an active event loop. Use await decide_trade_async(...).")

    async def decide_trade_async(self, assets, context, ai_context: AIRequestContext | None = None, stream_handler=None):
        """Decide for multiple assets in one governed async call."""
        return await self._decide_async(context, assets=assets, ai_context=ai_context, stream_handler=stream_handler)

    # ── Venue-specific system prompts ─────────────────────────────────────────

    _FOREX_SYSTEM_PROMPT = (
        "You are a professional FOREX TRADER and quantitative analyst managing spot currency positions "
        "on a retail broker (OANDA or MetaTrader). You operate under real bid-ask spreads, pip-based "
        "profit measurement, and account margin constraints.\n\n"
        "Trading pairs: {assets}\n\n"
        "You will receive market context including per-pair indicator metrics (RSI, MACD, EMA), "
        "active positions, account balance, and hard-enforced risk limits.\n\n"
        "Always use the 'current time' to respect trading sessions and cooldowns.\n\n"
        "FOREX-specific rules:\n"
        "1) Spread cost: Every round-trip on a major pair costs ~1-3 pips. TP must exceed spread + SL risk.\n"
        "2) Pip sizing: Most pairs: 1 pip = 0.0001. JPY pairs: 1 pip = 0.01. Use 5 decimal TP/SL.\n"
        "3) Sessions: London/NY overlap (12:00-16:00 UTC) = peak liquidity — tightest spreads, best setups. "
        "Asian session (00:00-09:00 UTC) = lower liquidity — widen TP/SL for JPY/AUD/NZD pairs.\n"
        "4) Macro events: Central bank decisions and data releases (NFP, CPI) cause 50-150 pip moves. "
        "If context shows an upcoming event, reduce size or hold.\n"
        "5) Correlation: EUR/USD and GBP/USD are ~0.85 correlated. USD/JPY often moves opposite EUR/USD. "
        "XAU/USD is inversely correlated with USD. Avoid large concurrent same-direction positions in correlated pairs.\n"
        "6) No funding rate, no liquidation price. This is spot FX — hold as long as margin allows.\n"
        "7) Minimum TP:SL ratio = 1.5:1 in pips. Do not enter if reward < 1.5× risk.\n\n"
        "Core policy:\n"
        "1) Require multi-timeframe confluence before entry (≥2 timeframes agree on direction).\n"
        "2) Do not chase: if price moved >0.5×ATR since last bar close, wait for a pullback.\n"
        "3) Cooldown: after opening or closing a position, wait ≥3 bars before reversing. Encode in exit_plan.\n"
        "4) Prefer limit orders for entries to avoid full spread cost; use market only for urgent exits.\n"
        "5) If thesis weakens but is not invalidated, tighten SL to breakeven before full close.\n\n"
        "Decision discipline:\n"
        "- Choose one per pair: buy / sell / hold.\n"
        "- allocation_usd is notional size (system converts to lots/units automatically).\n"
        "- BUY: tp_price > current_price, sl_price < current_price. Min distance: spread + 5 pips.\n"
        "- SELL: opposite. A mandatory SL at 0.5% from entry is auto-applied if you omit one.\n"
        "- exit_plan must include at least ONE explicit price-based invalidation trigger.\n\n"
        "Output contract\n"
        "- Output ONLY a strict JSON object (no markdown, no code fences) with exactly two properties:\n"
        "  • \"reasoning\": step-by-step analysis including session, spread cost, and pip targets.\n"
        "  • \"trade_decisions\": array matching the provided assets list.\n"
        "- Each item: asset, action, allocation_usd, order_type, limit_price, tp_price, sl_price, exit_plan, rationale.\n"
        "- Do not emit Markdown or extra properties.\n"
    )

    _CRYPTO_SYSTEM_PROMPT = (
        "You are a rigorous QUANTITATIVE TRADER and interdisciplinary MATHEMATICIAN-ENGINEER optimizing risk-adjusted returns for perpetual futures under real execution, margin, and funding constraints.\n"
        "You will receive market + account context for SEVERAL assets: {assets}\n"
        "Including: per-asset intraday (5m) and higher-timeframe (4h) metrics, Active Trades with Exit Plans, Recent Trading History, Risk management limits (hard-enforced).\n\n"
        "Always use the 'current time' provided in the user message to evaluate time-based conditions.\n\n"
        "Your goal: decisive, first-principles decisions per asset that minimize churn while capturing edge.\n\n"
        "Core policy (low-churn, position-aware)\n"
        "1) Respect prior plans: Do NOT close or flip early unless the explicit exit_plan invalidation has occurred.\n"
        "2) Hysteresis: Flip direction only if BOTH higher-TF structure AND intraday confirmation (decisive break >0.5×ATR + momentum) support the new direction.\n"
        "3) Cooldown: After any direction change, self-impose ≥3 bars cooldown. Encode in exit_plan.\n"
        "4) Funding is a tilt, not a trigger: Only factor funding when it exceeds expected edge over your hold horizon (>~0.25×ATR).\n"
        "5) RSI extremes ≠ reversal: Require structure + momentum confirmation. Prefer tightening stops over instant flips.\n"
        "6) Prefer adjustments over exits: Tighten stop, trail TP, or reduce size before closing.\n\n"
        "Decision discipline:\n"
        "- Choose: buy / sell / hold per asset.\n"
        "- You control allocation_usd (system caps it per risk limits).\n"
        "- order_type: \"market\" (default) or \"limit\" (MUST set limit_price for limit orders).\n"
        "- BUY: tp_price > current_price, sl_price < current_price. SELL: opposite. Mandatory SL auto-applied if omitted.\n"
        "- exit_plan: at least ONE explicit invalidation trigger + optional cooldown guidance.\n\n"
        "Leverage policy (perpetual futures): system enforces hard cap. Reduce in high-vol or funding spikes.\n\n"
        "{tool_section}"
        "Reasoning recipe: Structure (trend, EMAs, HH/HL), Momentum (MACD, RSI slope), Volatility (ATR), Positioning (funding, OI). Favor 4h+5m alignment.\n\n"
        "Output contract\n"
        "- Output ONLY a strict JSON object (no markdown) with exactly two properties:\n"
        "  • \"reasoning\": long-form step-by-step analysis.\n"
        "  • \"trade_decisions\": array matching the assets list.\n"
        "- Each item: asset, action, allocation_usd, order_type, limit_price, tp_price, sl_price, exit_plan, rationale.\n"
        "- Do not emit Markdown or extra properties.\n"
    )

    async def _decide_async(self, context, assets, ai_context: AIRequestContext | None = None, stream_handler=None):
        """Dispatch decision request through the governed AI boundary."""
        is_forex = self.venue_context == "forex"
        enable_tools = CONFIG.get("enable_tool_calling", True)
        indicator_tools_available = bool(enable_tools and self.hyperliquid is not None and not is_forex)
        anthropic_tool_protocol = {"anthropic", "bedrock"}
        can_use_indicator_tools = bool(indicator_tools_available and self.provider.name in anthropic_tool_protocol)
        if indicator_tools_available and not can_use_indicator_tools:
            logging.info(
                "Indicator tool loop disabled for provider=%s; using supplied market context only",
                self.provider.name,
            )
        assets_str = json.dumps(list(assets))

        if is_forex:
            system_prompt = self._FOREX_SYSTEM_PROMPT.replace("{assets}", assets_str)
            tools: list[dict[str, Any]] = []
        else:
            _tool_section = (
                "Tool usage\n"
                "- Use the fetch_indicator tool to sharpen your thesis. Parameters: indicator (ema/sma/rsi/macd/bbands/atr/adx/obv/vwap/stoch_rsi/all), asset (e.g. \"BTC\", \"OIL\", \"GOLD\"), interval (\"5m\"/\"4h\"), optional period.\n"
                "- Indicators are computed from Hyperliquid candle data — works for all perp markets.\n"
                "- Summarize tool findings in reasoning; never paste raw tool output into final JSON.\n\n"
                if can_use_indicator_tools else
                "Tool usage\n"
                "- No external tools available. Base analysis on provided market data.\n\n"
            )
            system_prompt = (
                self._CRYPTO_SYSTEM_PROMPT
                .replace("{assets}", assets_str)
                .replace("{tool_section}", _tool_section)
            )
            tools = [{
                "name": "fetch_indicator",
                "description": (
                    "Fetch technical indicators from Hyperliquid candle data. "
                    "Works for all Hyperliquid perp markets (BTC, ETH, OIL, GOLD, SPX, etc.). "
                    "Available: ema, sma, rsi, macd, bbands, atr, adx, obv, vwap, stoch_rsi, all."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "indicator": {"type": "string", "enum": ["ema", "sma", "rsi", "macd", "bbands", "atr", "adx", "obv", "vwap", "stoch_rsi", "all"]},
                        "asset": {"type": "string", "description": "Hyperliquid symbol, e.g. BTC, ETH, OIL"},
                        "interval": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h", "1d"]},
                        "period": {"type": "integer", "description": "Indicator period (optional)"},
                    },
                    "required": ["indicator", "asset", "interval"],
                },
            }]

        if self.system_prompt_addendum:
            system_prompt = self.system_prompt_addendum + "\n\n" + system_prompt

        if (ai_context.mode if ai_context else "paper") == "paper":
            system_prompt += (
                "\nPaper mode directive\n"
                "- Paper trading is used to validate execution flow and strategy behavior.\n"
                "- If market data is ready and a coherent setup exists, prefer a small, risk-defined starter trade over an overly cautious HOLD.\n"
                "- Do not force trades when data is stale, contradictory, or structurally weak.\n"
            )

        messages: list[dict[str, Any]] = [{"role": "user", "content": context}]

        base_ctx = ai_context or AIRequestContext(
            user_id="",
            trace_id=new_trace_id(),
            plan="FREE",
            action="agent_decision",
            provider=self.provider.name,
            model=self.provider.model,
            mode="paper",
            venue=self.venue_context,
            symbol=",".join(assets),
        )
        if not base_ctx.trace_id:
            base_ctx.trace_id = new_trace_id()

        def _log_request(model_name: str, messages_to_log: list[dict[str, Any]]) -> None:
            if not _DEBUG_PROMPTS:
                return
            with open(_LLM_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n\n=== {datetime.now()} ===\n")
                f.write(f"Model: {model_name}\n")
                f.write(f"Messages count: {len(messages_to_log)}\n")
                last = messages_to_log[-1]
                content_str = redact_text(str(last.get('content', "")))[:500]
                f.write(f"Last message role: {last.get('role')}\n")
                f.write(f"Last message content (truncated): {content_str}\n")

        def _provider_is_usable(name: str) -> bool:
            if name == "groq":
                key = CONFIG.get("groq_api_key") or ""
                return bool(key and not key.startswith("dummy") and not key.startswith("your-"))
            if name == "gemini":
                key = CONFIG.get("gemini_api_key") or ""
                return bool(key and not key.startswith("dummy") and not key.startswith("your-"))
            if name == "anthropic":
                key = CONFIG.get("anthropic_api_key") or ""
                return bool(key and not key.startswith("dummy") and not key.startswith("your-"))
            if name == "bedrock":
                key = CONFIG.get("aws_access_key_id") or ""
                secret = CONFIG.get("aws_secret_access_key") or ""
                profile = CONFIG.get("aws_profile") or ""
                return bool(profile or (key and secret and not key.startswith("your-") and not secret.startswith("your-")))
            if name == "openrouter":
                key = CONFIG.get("openrouter_api_key") or ""
                return bool(key and not key.startswith("dummy") and not key.startswith("your-"))
            if name == "ollama":
                return True
            return False

        def _provider_for_name(name: str):
            if name == self.provider.name:
                return self.provider
            if name == self._sanitize_provider.name:
                return self._sanitize_provider
            for provider in self._fallback_chain:
                if provider.name == name:
                    return provider
            if not _provider_is_usable(name):
                return None
            try:
                return get_provider(provider_name=name)
            except Exception:
                return None

        def _runtime_provider_chain(plan: str | None) -> list[Any]:
            policy = get_ai_plan_policy(plan)
            ordered_names = list(policy.primary_providers) + list(policy.fallback_providers)
            providers: list[Any] = []
            seen: set[str] = set()
            for name in ordered_names:
                provider = _provider_for_name(name)
                if provider is None or provider.name in seen:
                    continue
                providers.append(provider)
                seen.add(provider.name)
            if providers:
                return providers
            return self._fallback_chain

        def _sanitize_provider_for_plan(plan: str | None):
            policy = get_ai_plan_policy(plan)
            for name in policy.sanitize_providers:
                provider = _provider_for_name(name)
                if provider is not None:
                    return provider
            return self._sanitize_provider

        async def _call_llm(msgs: list[dict[str, Any]], use_tools: bool = True):
            last_err: Exception | None = None
            runtime_chain = _runtime_provider_chain(base_ctx.plan)
            for attempt, prov in enumerate(runtime_chain):
                _log_request(prov.model, msgs)
                call_ctx = AIRequestContext(
                    user_id=base_ctx.user_id,
                    trace_id=base_ctx.trace_id,
                    plan=base_ctx.plan,
                    action="agent_decision",
                    provider=prov.name,
                    model=prov.model,
                    mode=base_ctx.mode,
                    venue=base_ctx.venue,
                    symbol=base_ctx.symbol,
                    persona=base_ctx.persona,
                    agent_run_id=base_ctx.agent_run_id,
                    endpoint=base_ctx.endpoint or "/api/agent/start",
                    stream=base_ctx.stream,
                )
                try:
                    tool_list = tools if (
                        use_tools
                        and can_use_indicator_tools
                        and prov.name in anthropic_tool_protocol
                        and prov.supports_tools
                    ) else None
                    response = await governed_complete(
                        provider=prov,
                        system=system_prompt,
                        messages=msgs,
                        max_tokens=self.max_tokens,
                        context=call_ctx,
                        tools=tool_list,
                        stream_handler=stream_handler,
                    )
                    if attempt > 0:
                        logging.warning("LLM failover succeeded on attempt %d via %s", attempt + 1, prov.name)
                    return response, call_ctx
                except AIError as exc:
                    last_err = exc
                    if exc.code not in {AIErrorCode.AI_PROVIDER_FAILED, AIErrorCode.AI_PROVIDER_UNAVAILABLE}:
                        raise
                    logging.warning(
                        "LLM provider %s failed safely (attempt %d/%d): %s",
                        prov.name,
                        attempt + 1,
                        len(runtime_chain),
                        exc.code.value,
                    )
                except Exception as exc:
                    last_err = exc
                    logging.warning(
                        "LLM provider %s failed (attempt %d/%d): %s — trying next",
                        prov.name,
                        attempt + 1,
                        len(runtime_chain),
                        exc,
                    )
            if isinstance(last_err, AIError):
                raise last_err
            raise RuntimeError(f"All LLM providers exhausted. Last error: {last_err}")

        def _handle_tool_call(tool_name, tool_input):
            if tool_name != "fetch_indicator":
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

            try:
                asset = tool_input["asset"]
                interval = tool_input["interval"]
                indicator = tool_input["indicator"]

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        candles = pool.submit(
                            asyncio.run,
                            self.hyperliquid.get_candles(asset, interval, 100)
                        ).result(timeout=30)
                else:
                    candles = asyncio.run(self.hyperliquid.get_candles(asset, interval, 100))

                all_indicators = compute_all(candles)

                if indicator == "all":
                    result = {k: {"latest": latest(v) if isinstance(v, list) else v, "series": last_n(v, 10) if isinstance(v, list) else v} for k, v in all_indicators.items()}
                elif indicator == "macd":
                    result = {
                        "macd": {"latest": latest(all_indicators.get("macd", [])), "series": last_n(all_indicators.get("macd", []), 10)},
                        "signal": {"latest": latest(all_indicators.get("macd_signal", [])), "series": last_n(all_indicators.get("macd_signal", []), 10)},
                        "histogram": {"latest": latest(all_indicators.get("macd_histogram", [])), "series": last_n(all_indicators.get("macd_histogram", []), 10)},
                    }
                elif indicator == "bbands":
                    result = {
                        "upper": {"latest": latest(all_indicators.get("bbands_upper", [])), "series": last_n(all_indicators.get("bbands_upper", []), 10)},
                        "middle": {"latest": latest(all_indicators.get("bbands_middle", [])), "series": last_n(all_indicators.get("bbands_middle", []), 10)},
                        "lower": {"latest": latest(all_indicators.get("bbands_lower", [])), "series": last_n(all_indicators.get("bbands_lower", []), 10)},
                    }
                elif indicator in ("ema", "sma"):
                    period = tool_input.get("period", 20)
                    from src.indicators.local_indicators import ema as _ema, sma as _sma
                    closes = [c["close"] for c in candles]
                    series = _ema(closes, period) if indicator == "ema" else _sma(closes, period)
                    result = {"latest": latest(series), "series": last_n(series, 10), "period": period}
                elif indicator == "rsi":
                    period = tool_input.get("period", 14)
                    from src.indicators.local_indicators import rsi as _rsi
                    series = _rsi(candles, period)
                    result = {"latest": latest(series), "series": last_n(series, 10), "period": period}
                elif indicator == "atr":
                    period = tool_input.get("period", 14)
                    from src.indicators.local_indicators import atr as _atr
                    series = _atr(candles, period)
                    result = {"latest": latest(series), "series": last_n(series, 10), "period": period}
                else:
                    key_map = {"adx": "adx", "obv": "obv", "vwap": "vwap", "stoch_rsi": "stoch_rsi"}
                    mapped = key_map.get(indicator, indicator)
                    series = all_indicators.get(mapped, [])
                    result = {"latest": latest(series) if isinstance(series, list) else series, "series": last_n(series, 10) if isinstance(series, list) else series}

                return json.dumps(result, default=str)
            except Exception as ex:
                logging.error("Tool call error: %s", ex)
                return json.dumps({"error": str(ex)})

        async def _sanitize_output(raw_content: str, assets_list):
            sanitize_provider = _sanitize_provider_for_plan(base_ctx.plan)
            sanitize_ctx = AIRequestContext(
                user_id=base_ctx.user_id,
                trace_id=base_ctx.trace_id,
                plan=base_ctx.plan,
                action="sanitize_output",
                provider=sanitize_provider.name,
                model=sanitize_provider.model,
                mode=base_ctx.mode,
                venue=base_ctx.venue,
                symbol=base_ctx.symbol,
                persona=base_ctx.persona,
                agent_run_id=base_ctx.agent_run_id,
                endpoint=base_ctx.endpoint or "/api/agent/start",
                stream=False,
            )
            try:
                sanitize_resp = await governed_complete(
                    provider=sanitize_provider,
                    system=(
                        "You are a strict JSON normalizer. Return ONLY a JSON object with two keys: "
                        "\"reasoning\" (string) and \"trade_decisions\" (array). "
                        "Each trade_decisions item must have: asset, action (buy/sell/hold), "
                        "allocation_usd (number), order_type (\"market\" or \"limit\"), "
                        "limit_price (number or null), tp_price (number or null), sl_price (number or null), "
                        "exit_plan (string), rationale (string). "
                        f"Valid assets: {json.dumps(list(assets_list))}. "
                        "If input is wrapped in markdown or has prose, extract just the JSON. Do not add fields."
                    ),
                    messages=[{"role": "user", "content": raw_content}],
                    max_tokens=2048,
                    context=sanitize_ctx,
                )
                parsed = json.loads(sanitize_resp.content)
                if isinstance(parsed, dict) and "trade_decisions" in parsed:
                    return parsed
                return {"reasoning": "", "trade_decisions": []}
            except Exception as se:
                logging.error("Sanitize failed: %s", se)
                return {"reasoning": "", "trade_decisions": []}

        def _safe_float(value: Any, default: float | None = None) -> float | None:
            if value is None:
                return default
            if isinstance(value, str):
                raw = value.strip()
                if not raw or raw.endswith("%"):
                    return default
                raw = raw.replace("$", "").replace(",", "")
                value = raw
            try:
                return float(value)
            except Exception:
                return default

        def _normalize_action(value: Any) -> str:
            raw = str(value or "hold").strip().lower()
            aliases = {
                "long": "buy",
                "short": "sell",
                "wait": "hold",
                "no_trade": "hold",
                "none": "hold",
            }
            action = aliases.get(raw, raw)
            if action not in {"buy", "sell", "hold"}:
                return "hold"
            return action

        def _asset_key(value: str) -> str:
            return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

        def _strip_code_fences(text: str) -> str:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned, count=1)
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].rstrip()
            return cleaned.strip()

        def _json_candidates(text: str) -> list[str]:
            cleaned = _strip_code_fences(text)
            candidates: list[str] = []
            if cleaned:
                candidates.append(cleaned)
            for opener, closer in (("{", "}"), ("[", "]")):
                start = cleaned.find(opener)
                end = cleaned.rfind(closer)
                if start != -1 and end > start:
                    candidates.append(cleaned[start:end + 1])
            seen: set[str] = set()
            unique: list[str] = []
            for candidate in candidates:
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    unique.append(candidate)
            return unique

        def _parse_loose_payload(text: str) -> Any | None:
            for candidate in _json_candidates(text):
                try:
                    return json.loads(candidate)
                except Exception:
                    pass
                try:
                    return ast.literal_eval(candidate)
                except Exception:
                    pass
            return None

        def _normalize_trade_item(item: dict[str, Any], fallback_asset: str) -> dict[str, Any]:
            asset = str(
                item.get("asset")
                or item.get("symbol")
                or item.get("ticker")
                or fallback_asset
                or ""
            ).strip()
            requested_by_key = {_asset_key(asset_name): asset_name for asset_name in assets}
            asset = requested_by_key.get(_asset_key(asset), asset)
            action = _normalize_action(item.get("action") or item.get("decision") or item.get("signal"))
            order_type_raw = str(item.get("order_type") or item.get("entry_type") or "").strip().lower()
            limit_price = _safe_float(item.get("limit_price"))
            order_type = order_type_raw or ("limit" if limit_price is not None and action != "hold" else "market")
            tp_price = _safe_float(item.get("tp_price", item.get("take_profit", item.get("tp"))))
            sl_price = _safe_float(item.get("sl_price", item.get("stop_loss", item.get("sl"))))
            allocation_usd = _safe_float(
                item.get("allocation_usd", item.get("size_usd", item.get("position_usd"))),
                0.0,
            ) or 0.0
            confidence = _safe_float(item.get("confidence"))
            rationale = str(
                item.get("rationale")
                or item.get("reason")
                or item.get("why")
                or item.get("explanation")
                or ""
            ).strip()
            exit_plan = str(
                item.get("exit_plan")
                or item.get("exit")
                or item.get("exit_strategy")
                or item.get("invalidation")
                or ""
            ).strip()

            if action == "hold":
                allocation_usd = 0.0
                order_type = "market"
                limit_price = None

            normalized: dict[str, Any] = {
                "asset": asset,
                "action": action,
                "allocation_usd": round(max(0.0, allocation_usd), 2),
                "order_type": order_type if order_type in {"market", "limit"} else "market",
                "limit_price": limit_price,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "exit_plan": exit_plan,
                "rationale": rationale,
            }
            if confidence is not None:
                normalized["confidence"] = max(0.0, min(1.0, confidence))
            if "reason_code" in item and item.get("reason_code"):
                normalized["reason_code"] = str(item.get("reason_code"))
            return normalized

        def _normalize_payload(parsed: Any, assets_list: list[str]) -> dict[str, Any]:
            reasoning = ""
            reason_code = None
            raw_decisions: Any = None

            if isinstance(parsed, list):
                raw_decisions = parsed
            elif isinstance(parsed, dict):
                reasoning = str(
                    parsed.get("reasoning")
                    or parsed.get("analysis")
                    or parsed.get("summary")
                    or parsed.get("message")
                    or ""
                ).strip()
                reason_code = parsed.get("reason_code")
                raw_decisions = (
                    parsed.get("trade_decisions")
                    if "trade_decisions" in parsed
                    else parsed.get("trade_decision", parsed.get("decisions"))
                )
                if raw_decisions is None and any(key in parsed for key in ("asset", "symbol", "action", "decision", "signal")):
                    raw_decisions = [parsed]

            if isinstance(raw_decisions, dict):
                raw_decisions = [raw_decisions]
            if not isinstance(raw_decisions, list):
                return {"reasoning": reasoning, "reason_code": reason_code, "trade_decisions": []}

            normalized: list[dict[str, Any]] = []
            used_asset_keys: set[str] = set()
            for index, item in enumerate(raw_decisions):
                if not isinstance(item, dict):
                    continue
                fallback_asset = assets_list[index] if index < len(assets_list) else (assets_list[0] if len(assets_list) == 1 else "")
                trade = _normalize_trade_item(item, fallback_asset)
                if not trade["asset"]:
                    continue
                normalized.append(trade)
                used_asset_keys.add(_asset_key(trade["asset"]))

            for asset in assets_list:
                if _asset_key(asset) in used_asset_keys:
                    continue
                normalized.append({
                    "asset": asset,
                    "action": "hold",
                    "allocation_usd": 0.0,
                    "order_type": "market",
                    "limit_price": None,
                    "tp_price": None,
                    "sl_price": None,
                    "exit_plan": "",
                    "rationale": "No explicit decision was returned for this asset.",
                    "reason_code": "asset_decision_missing",
                })

            return {
                "reasoning": reasoning,
                "reason_code": reason_code,
                "trade_decisions": normalized,
            }

        tool_rounds = 0
        force_no_tools = False
        seen_tool_calls: set[tuple[str, str]] = set()
        final_ctx = base_ctx

        def _safe_hold_payload(
            *,
            reason: str,
            rationale: str,
            reason_code: str,
            model: str | None = None,
        ) -> dict[str, Any]:
            return {
                "reasoning": reason,
                "reason_code": reason_code,
                "trace_id": final_ctx.trace_id,
                "provider": final_ctx.provider,
                "model": model or final_ctx.model,
                "trade_decisions": [{
                    "asset": a,
                    "action": "hold",
                    "allocation_usd": 0.0,
                    "tp_price": None,
                    "sl_price": None,
                    "exit_plan": "",
                    "rationale": rationale,
                    "reason_code": reason_code,
                } for a in assets],
            }

        for _iteration in range(6):
            try:
                response, final_ctx = await _call_llm(messages, use_tools=not force_no_tools)
            except AIError as e:
                if base_ctx.action == "backtest_commentary":
                    raise
                return {
                    "reasoning": e.definition.user_message,
                    "reason_code": e.metadata.get("reason_code") or e.code.value,
                    "trace_id": e.trace_id,
                    "provider": final_ctx.provider,
                    "model": final_ctx.model,
                    "trade_decisions": [{
                        "asset": a,
                        "action": "hold",
                        "allocation_usd": 0.0,
                        "tp_price": None,
                        "sl_price": None,
                        "exit_plan": "",
                        "rationale": e.definition.user_message,
                        "reason_code": e.metadata.get("reason_code") or e.code.value,
                    } for a in assets],
                }
            except Exception as e:
                logging.error("LLM provider error: %s", e)
                break

            raw_resp = response.raw
            tool_use_blocks = []
            text_blocks_raw = []

            if raw_resp is not None and hasattr(raw_resp, "content"):
                tool_use_blocks = [b for b in raw_resp.content if b.type == "tool_use"]
                text_blocks_raw = [b for b in raw_resp.content if b.type == "text"]

            if tool_use_blocks and response.stop_reason == "tool_use":
                repeated_tool_call = False
                assistant_content = []
                for block in raw_resp.content:
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        assistant_content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
                    elif block.type == "thinking":
                        assistant_content.append({"type": "thinking", "thinking": block.thinking})
                messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in tool_use_blocks:
                    signature = (block.name, json.dumps(block.input, sort_keys=True, default=str))
                    if signature in seen_tool_calls:
                        repeated_tool_call = True
                    seen_tool_calls.add(signature)
                    result_str = _handle_tool_call(block.name, block.input)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result_str})
                messages.append({"role": "user", "content": tool_results})
                tool_rounds += 1
                if repeated_tool_call or tool_rounds >= 3:
                    force_no_tools = True
                    messages.append({
                        "role": "user",
                        "content": (
                            "You already have enough indicator context. "
                            "Do not call any more tools. Return the final strict JSON now. "
                            "If the setup is unclear, return hold with a concise market-based rationale."
                        ),
                    })
                continue

            raw_text = response.content
            if text_blocks_raw:
                raw_text = "".join(b.text for b in text_blocks_raw)

            if not raw_text.strip():
                logging.error("Empty response from LLM provider")
                if force_no_tools:
                    return _safe_hold_payload(
                        reason="The final AI response was empty",
                        rationale="The final AI response was empty after tool analysis, so no trade was executed.",
                        reason_code="ai_final_response_empty",
                        model=response.model or final_ctx.model,
                    )
                break

            normalized = _normalize_payload(_parse_loose_payload(raw_text), assets)
            if normalized.get("trade_decisions"):
                return {
                    "reasoning": normalized.get("reasoning", ""),
                    "reason_code": normalized.get("reason_code"),
                    "trade_decisions": normalized.get("trade_decisions", []),
                    "trace_id": final_ctx.trace_id,
                    "provider": final_ctx.provider,
                    "model": response.model or final_ctx.model,
                }

            logging.error("Could not normalize model JSON safely, attempting sanitize. content=%s", redact_text(raw_text[:200]))
            sanitized = await _sanitize_output(raw_text, assets)
            sanitized_normalized = _normalize_payload(sanitized, assets)
            if sanitized_normalized.get("trade_decisions"):
                sanitized_normalized["trace_id"] = final_ctx.trace_id
                sanitized_normalized["provider"] = final_ctx.provider
                sanitized_normalized["model"] = response.model or final_ctx.model
                return sanitized_normalized

            return {
                "reasoning": "Parse error",
                "reason_code": "ai_output_invalid",
                "trace_id": final_ctx.trace_id,
                "provider": final_ctx.provider,
                "model": response.model or final_ctx.model,
                "trade_decisions": [{
                    "asset": a,
                    "action": "hold",
                    "allocation_usd": 0.0,
                    "tp_price": None,
                    "sl_price": None,
                    "exit_plan": "",
                    "rationale": "The AI response could not be validated safely, so no trade was executed.",
                    "reason_code": "ai_output_invalid",
                } for a in assets],
            }

        if tool_rounds > 0:
            return _safe_hold_payload(
                reason="The model could not complete a safe final analysis on this tick",
                rationale=(
                    "The model reached the tool-analysis safety limit and did not return valid final trading JSON, "
                    "so no trade was executed."
                ),
                reason_code="ai_final_response_invalid",
            )

        return _safe_hold_payload(
            reason="The AI did not return valid final trading JSON on this tick",
            rationale="The AI response could not be validated safely, so no trade was executed.",
            reason_code="ai_final_response_invalid",
        )
