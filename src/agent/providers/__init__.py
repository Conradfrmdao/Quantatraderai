"""LLM provider abstraction.

Supported providers and their free-tier options:

  anthropic  — Claude (claude-sonnet-4-6, claude-opus-4-7)          PAID
  groq       — Llama 3.3 70B, Llama 3.1 8B, Gemma2 9B              FREE tier
  gemini     — gemini-2.0-flash-exp, gemini-1.5-flash               FREE tier
  ollama     — any model pulled locally (llama3, mistral, …)        FREE (local)
  openrouter — many free models (nousresearch/hermes, meta-llama/…)  FREE models

Set LLM_PROVIDER and LLM_MODEL in .env.
"""
from src.agent.providers.base import LLMProvider, LLMResponse
from src.agent.providers.factory import get_provider

__all__ = ["LLMProvider", "LLMResponse", "get_provider"]
