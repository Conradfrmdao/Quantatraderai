"""Anthropic Claude provider — full tool use and extended thinking support."""

from __future__ import annotations

import logging

import anthropic

from src.agent.providers.base import LLMProvider, LLMResponse
from src.config_loader import CONFIG


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str | None = None):
        self.model = model or CONFIG.get("llm_model") or "claude-sonnet-4-6"
        self.client = anthropic.Anthropic(api_key=CONFIG.get("anthropic_api_key") or "")

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def supports_thinking(self) -> bool:
        return True

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools and CONFIG.get("enable_tool_calling"):
            kwargs["tools"] = tools
        if CONFIG.get("thinking_enabled"):
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": int(CONFIG.get("thinking_budget_tokens") or 10000),
            }
            kwargs["max_tokens"] = max(max_tokens, 16000)

        resp = self.client.messages.create(**kwargs)
        logging.info("Anthropic: stop=%s usage=%s", resp.stop_reason, resp.usage)

        text = "".join(b.text for b in resp.content if b.type == "text")
        return LLMResponse(
            content=text,
            model=self.model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            stop_reason=resp.stop_reason or "stop",
            raw=resp,
        )
