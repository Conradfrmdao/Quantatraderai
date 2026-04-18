"""OpenRouter provider — access many free and paid models via one key.

Free models on OpenRouter (set LLM_MODEL to one of these):
  meta-llama/llama-3.3-70b-instruct:free
  meta-llama/llama-3.1-8b-instruct:free
  google/gemma-2-9b-it:free
  mistralai/mistral-7b-instruct:free
  nousresearch/hermes-3-llama-3.1-405b:free
  microsoft/phi-3-medium-128k-instruct:free
  deepseek/deepseek-r1:free                — reasoning model, great for trading

Sign up at openrouter.ai — free tier available without credit card.
Set OPENROUTER_API_KEY in .env.
"""

from __future__ import annotations

import logging

import requests

from src.agent.providers.base import LLMProvider, LLMResponse
from src.config_loader import CONFIG

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

    def __init__(self, model: str | None = None):
        self.model = model or CONFIG.get("llm_model") or self.DEFAULT_MODEL
        self.api_key = CONFIG.get("openrouter_api_key") or ""

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        openrouter_messages = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg.get("role") or "user"
            content = msg.get("content") or ""
            if isinstance(content, list):
                content = " ".join(
                    c.get("text") or c.get("content") or ""
                    for c in content if isinstance(c, dict)
                )
            openrouter_messages.append({"role": role, "content": content})

        payload: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": openrouter_messages,
        }

        try:
            resp = requests.post(
                f"{_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://github.com/QuntaTradeAI",
                    "X-Title": "QuntaTradeAI",
                },
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content") or ""
            usage = data.get("usage") or {}
            logging.info("OpenRouter: model=%s tokens in=%d out=%d",
                         self.model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
            return LLMResponse(
                content=text,
                model=self.model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                stop_reason=choice.get("finish_reason") or "stop",
                raw=data,
            )
        except Exception as e:
            logging.error("OpenRouter error: %s", e)
            return LLMResponse(content="", model=self.model, stop_reason="error")
