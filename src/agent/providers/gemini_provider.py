"""Google Gemini provider — free-tier AI inference.

Free models (as of 2025, via Google AI Studio):
  gemini-2.0-flash-exp         — latest, fast, multimodal, generous free quota
  gemini-1.5-flash             — battle-tested, 1M ctx, free tier
  gemini-1.5-flash-8b          — lightest, fastest free option

Sign up at aistudio.google.com — no credit card required for free tier.
Set GEMINI_API_KEY in .env.
"""

from __future__ import annotations

import json
import logging

from src.agent.providers.base import LLMProvider, LLMResponse
from src.config_loader import CONFIG


class GeminiProvider(LLMProvider):
    name = "gemini"

    DEFAULT_MODEL = "gemini-2.0-flash-exp"

    def __init__(self, model: str | None = None):
        self.model = model or CONFIG.get("llm_model") or self.DEFAULT_MODEL
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=CONFIG.get("gemini_api_key") or "")
            self._genai = genai
            self._model_client = genai.GenerativeModel(self.model)
        except ImportError as e:
            raise RuntimeError(
                "google-generativeai is not installed. Run: pip install google-generativeai"
            ) from e

    @property
    def supports_tools(self) -> bool:
        return True

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        history, config = self._build_request(system, messages, max_tokens)
        try:
            resp = self._model_client.generate_content(history, generation_config=config)
            return self._build_response(resp)
        except Exception as e:
            logging.error("Gemini API error: %s", e)
            return LLMResponse(content="", model=self.model, stop_reason="error")

    async def acomplete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        history, config = self._build_request(system, messages, max_tokens)
        try:
            if hasattr(self._model_client, "generate_content_async"):
                resp = await self._model_client.generate_content_async(history, generation_config=config)
                return self._build_response(resp)
            return self.complete(system, messages, max_tokens=max_tokens, tools=tools)
        except Exception as e:
            logging.error("Gemini API error: %s", e)
            return LLMResponse(content="", model=self.model, stop_reason="error")

    def _build_request(self, system: str, messages: list[dict], max_tokens: int):
        # Gemini uses a different message format; rebuild from Anthropic-style
        full_system = system
        # Prepend system as a user message (Gemini doesn't have a system role in older API)
        history = [{"role": "user", "parts": [full_system + "\n\n" + (messages[0].get("content") or "")]}]
        for msg in messages[1:]:
            role = "user" if msg.get("role") == "user" else "model"
            content = msg.get("content") or ""
            if isinstance(content, list):
                content = " ".join(
                    c.get("text") or c.get("content") or ""
                    for c in content if isinstance(c, dict)
                )
            history.append({"role": role, "parts": [content]})

        config = self._genai.types.GenerationConfig(max_output_tokens=max_tokens)
        return history, config

    def _build_response(self, resp) -> LLMResponse:
        text = resp.text or ""
        usage = getattr(resp, "usage_metadata", None)
        prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        logging.info("Gemini: model=%s response_len=%d tokens in=%d out=%d", self.model, len(text), prompt_tokens, output_tokens)
        return LLMResponse(
            content=text,
            model=self.model,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            stop_reason="stop",
            raw=resp,
        )
