"""Provider factory — resolve LLM_PROVIDER to the right adapter.

Free options (no Anthropic key needed):
  groq       — fastest free inference (Llama 3.3 70B)
  gemini     — Google Gemini 2.0 Flash (free quota)
  ollama     — local models, fully offline
  openrouter — many free models incl. DeepSeek-R1

Paid:
  anthropic  — Claude (best quality for trading decisions)
  bedrock    — Claude through AWS Bedrock credits/quotas
"""

from __future__ import annotations

from src.agent.providers.base import LLMProvider
from src.config_loader import CONFIG


def get_provider(provider_name: str | None = None, model: str | None = None) -> LLMProvider:
    name = (provider_name or CONFIG.get("llm_provider") or "anthropic").lower().strip()

    if name == "anthropic":
        from src.agent.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model)

    if name == "bedrock":
        from src.agent.providers.bedrock_provider import BedrockProvider
        return BedrockProvider(model=model)

    if name == "groq":
        from src.agent.providers.groq_provider import GroqProvider
        return GroqProvider(model=model)

    if name == "gemini":
        from src.agent.providers.gemini_provider import GeminiProvider
        return GeminiProvider(model=model)

    if name == "ollama":
        from src.agent.providers.ollama_provider import OllamaProvider
        return OllamaProvider(model=model)

    if name == "openrouter":
        from src.agent.providers.openrouter_provider import OpenRouterProvider
        return OpenRouterProvider(model=model)

    raise ValueError(
        f"Unknown LLM provider: {name!r}. "
        "Choose one of: anthropic | bedrock | groq | gemini | ollama | openrouter"
    )
