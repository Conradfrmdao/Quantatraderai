"""Centralized environment variable loading for QuantatraderAI."""

import json
import os
from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}: {raw}") from exc


def _get_json(name: str, default: dict | None = None) -> dict | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError(f"Environment variable {name} must be a JSON object")
        return parsed
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON for {name}: {raw}") from exc


def _get_list(name: str, default: list[str] | None = None) -> list[str] | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise RuntimeError(f"Environment variable {name} must be a list if using JSON syntax")
            return [str(item).strip().strip('"\'') for item in parsed if str(item).strip()]
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON list for {name}: {raw}") from exc
    values = []
    for item in raw.split(","):
        cleaned = item.strip().strip('"\'')
        if cleaned:
            values.append(cleaned)
    return values or default


CONFIG = {
    # Venue selection
    "venue": _get_env("VENUE", "hyperliquid"),

    # Hyperliquid
    "hyperliquid_private_key": _get_env("HYPERLIQUID_PRIVATE_KEY"),
    "mnemonic": _get_env("MNEMONIC"),
    "hyperliquid_base_url": _get_env("HYPERLIQUID_BASE_URL"),
    "hyperliquid_network": _get_env("HYPERLIQUID_NETWORK", "mainnet"),
    "hyperliquid_vault_address": _get_env("HYPERLIQUID_VAULT_ADDRESS"),

    # CCXT (generic crypto exchange)
    "ccxt_exchange": _get_env("CCXT_EXCHANGE", "binance"),
    "ccxt_api_key": _get_env("CCXT_API_KEY"),
    "ccxt_api_secret": _get_env("CCXT_API_SECRET"),
    "ccxt_sandbox": _get_bool("CCXT_SANDBOX", True),
    "ccxt_market": _get_env("CCXT_MARKET", "spot"),  # spot | futures — drives asset_class + risk limits

    # OANDA (forex)
    "oanda_api_token": _get_env("OANDA_API_TOKEN"),
    "oanda_account_id": _get_env("OANDA_ACCOUNT_ID"),
    "oanda_env": _get_env("OANDA_ENV", "practice"),

    # LLM provider selection
    # Free options: groq | gemini | ollama | openrouter
    # Paid: anthropic (best quality)
    "llm_provider": _get_env("LLM_PROVIDER", "anthropic"),
    "llm_model": _get_env("LLM_MODEL", "claude-sonnet-4-6"),
    "max_tokens": _get_int("MAX_TOKENS", 4096),
    "enable_tool_calling": _get_bool("ENABLE_TOOL_CALLING", True),
    "thinking_enabled": _get_bool("THINKING_ENABLED", False),
    "thinking_budget_tokens": _get_int("THINKING_BUDGET_TOKENS", 10000),

    # Anthropic (llm_provider=anthropic)
    "anthropic_api_key": _get_env("ANTHROPIC_API_KEY"),
    "sanitize_model": _get_env("SANITIZE_MODEL", "claude-haiku-4-5-20251001"),

    # Groq — FREE (llm_provider=groq)
    # Sign up at console.groq.com — no credit card needed
    # Models: llama-3.3-70b-versatile | llama-3.1-8b-instant | gemma2-9b-it
    "groq_api_key": _get_env("GROQ_API_KEY"),

    # Google Gemini — FREE (llm_provider=gemini)
    # Sign up at aistudio.google.com — no credit card needed
    # Models: gemini-2.0-flash-exp | gemini-1.5-flash
    "gemini_api_key": _get_env("GEMINI_API_KEY"),

    # Ollama — FREE local (llm_provider=ollama)
    # Install: https://ollama.com  then: ollama pull llama3.2
    "ollama_base_url": _get_env("OLLAMA_BASE_URL", "http://localhost:11434"),

    # OpenRouter — FREE models available (llm_provider=openrouter)
    # Sign up at openrouter.ai — free models: deepseek/deepseek-r1:free etc.
    "openrouter_api_key": _get_env("OPENROUTER_API_KEY"),

    # Binance (venue=binance or binance:futures / binance:spot)
    "binance_api_key": _get_env("BINANCE_API_KEY"),
    "binance_api_secret": _get_env("BINANCE_API_SECRET"),
    "binance_market": _get_env("BINANCE_MARKET", "futures"),
    "binance_sandbox": _get_bool("BINANCE_SANDBOX", True),

    # Runtime
    "assets": _get_env("ASSETS"),
    "interval": _get_env("INTERVAL"),

    # Risk management — global fallbacks; per-venue overrides in risk.yaml
    "max_position_pct": _get_env("MAX_POSITION_PCT", "3"),
    "max_loss_per_position_pct": _get_env("MAX_LOSS_PER_POSITION_PCT", "8"),
    "max_leverage": _get_env("MAX_LEVERAGE", "2"),
    "max_total_exposure_pct": _get_env("MAX_TOTAL_EXPOSURE_PCT", "20"),
    "daily_loss_circuit_breaker_pct": _get_env("DAILY_LOSS_CIRCUIT_BREAKER_PCT", "4"),
    "mandatory_sl_pct": _get_env("MANDATORY_SL_PCT", "2.5"),
    "max_concurrent_positions": _get_env("MAX_CONCURRENT_POSITIONS", "5"),
    "min_balance_reserve_pct": _get_env("MIN_BALANCE_RESERVE_PCT", "30"),
    "risk_config_path": _get_env("RISK_CONFIG_PATH", "risk.yaml"),

    # Alerts
    "telegram_bot_token": _get_env("TELEGRAM_BOT_TOKEN"),
    "telegram_chat_id": _get_env("TELEGRAM_CHAT_ID"),

    # API server
    "api_host": _get_env("API_HOST", "127.0.0.1"),
    "api_port": _get_env("APP_PORT") or _get_env("API_PORT") or "3000",

    # Legacy / optional
    "taapi_api_key": _get_env("TAAPI_API_KEY"),
}
