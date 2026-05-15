"""AWS Bedrock Claude provider.

Uses Anthropic's Bedrock client so QuantatraderAI can spend AWS Bedrock credits
without routing through a separate command-capable proxy server.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from src.agent.providers.base import LLMProvider, LLMResponse
from src.config_loader import CONFIG


class BedrockProvider(LLMProvider):
    name = "bedrock"

    DEFAULT_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    def __init__(self, model: str | None = None):
        configured_model = model or CONFIG.get("bedrock_model")
        if not configured_model and (CONFIG.get("llm_provider") or "").lower() == "bedrock":
            configured_model = CONFIG.get("llm_model")
        self.model = configured_model or self.DEFAULT_MODEL

        kwargs = self._client_kwargs()
        self.client = anthropic.AnthropicBedrock(**kwargs)
        self.async_client = anthropic.AsyncAnthropicBedrock(**kwargs)

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
        return self._build_response(self.client.messages.create(**self._build_kwargs(system, messages, max_tokens, tools)))

    async def acomplete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        return self._build_response(await self.async_client.messages.create(**self._build_kwargs(system, messages, max_tokens, tools)))

    def _client_kwargs(self) -> dict[str, str]:
        kwargs: dict[str, str] = {
            "aws_region": CONFIG.get("aws_region") or "us-east-1",
        }
        if CONFIG.get("aws_access_key_id"):
            kwargs["aws_access_key"] = str(CONFIG.get("aws_access_key_id"))
        if CONFIG.get("aws_secret_access_key"):
            kwargs["aws_secret_key"] = str(CONFIG.get("aws_secret_access_key"))
        if CONFIG.get("aws_session_token"):
            kwargs["aws_session_token"] = str(CONFIG.get("aws_session_token"))
        if CONFIG.get("aws_profile"):
            kwargs["aws_profile"] = str(CONFIG.get("aws_profile"))
        return kwargs

    def _build_kwargs(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
        tools: list[dict] | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
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
        return kwargs

    def _build_response(self, resp) -> LLMResponse:
        usage = getattr(resp, "usage", None)
        logging.info("Bedrock Claude: stop=%s usage=%s", getattr(resp, "stop_reason", None), usage)

        text = "".join(getattr(block, "text", "") for block in resp.content if getattr(block, "type", "") == "text")
        return LLMResponse(
            content=text,
            model=self.model,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            stop_reason=getattr(resp, "stop_reason", None) or "stop",
            raw=resp,
        )
