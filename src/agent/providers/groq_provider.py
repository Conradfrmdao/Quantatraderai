"""Groq provider — free-tier LLM inference (Llama, Gemma, Mixtral).

Free models (as of 2025):
  llama-3.3-70b-versatile      — best quality, 128k ctx
  llama-3.1-8b-instant         — fastest
  gemma2-9b-it                 — Google Gemma 2
  mixtral-8x7b-32768           — Mixtral MoE, 32k ctx

Sign up at console.groq.com — free tier has generous rate limits.
Set GROQ_API_KEY in .env.
"""

from __future__ import annotations

import json
import logging

from src.agent.providers.base import LLMProvider, LLMResponse
from src.config_loader import CONFIG


class GroqProvider(LLMProvider):
    name = "groq"

    # Default: best quality free model
    DEFAULT_MODEL = "llama-3.3-70b-versatile"

    def __init__(self, model: str | None = None):
        self.model = model or CONFIG.get("llm_model") or self.DEFAULT_MODEL
        try:
            from groq import Groq  # type: ignore
            self.client = Groq(api_key=CONFIG.get("groq_api_key") or "")
        except ImportError as e:
            raise RuntimeError(
                "groq package is not installed. Run: pip install groq"
            ) from e

    @property
    def supports_tools(self) -> bool:
        return True  # Groq supports tool use on supported models

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        groq_messages = [{"role": "system", "content": system}] + messages

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": groq_messages,
        }
        if tools and CONFIG.get("enable_tool_calling"):
            # Groq uses OpenAI-style tool format
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema") or t.get("parameters") or {},
                    },
                }
                for t in tools
            ]

        resp = self.client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        text = choice.message.content or ""

        # If tool call returned, serialize it back as text so the agent loop
        # can handle it — the agent re-parses tool calls from the raw response.
        if choice.message.tool_calls:
            calls = [
                {"name": tc.function.name, "arguments": tc.function.arguments}
                for tc in choice.message.tool_calls
            ]
            text = json.dumps({"tool_calls": calls})

        usage = resp.usage
        logging.info("Groq: model=%s tokens in=%d out=%d", self.model,
                     usage.prompt_tokens if usage else 0,
                     usage.completion_tokens if usage else 0)

        return LLMResponse(
            content=text,
            model=self.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            stop_reason=choice.finish_reason or "stop",
            raw=resp,
        )
