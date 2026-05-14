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

import aiohttp
import requests

from src.agent.providers.base import LLMProvider, LLMResponse
from src.config_loader import CONFIG

_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(LLMProvider):
    name = "groq"

    # Default: best quality free model
    DEFAULT_MODEL = "llama-3.3-70b-versatile"

    def __init__(self, model: str | None = None):
        self.model = model or CONFIG.get("llm_model") or self.DEFAULT_MODEL
        self.api_key = CONFIG.get("groq_api_key") or ""

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
        kwargs = self._build_payload(system, messages, max_tokens, tools)
        resp = requests.post(
            f"{_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=kwargs,
            timeout=60,
        )
        resp.raise_for_status()
        return self._parse_response(resp.json())

    async def acomplete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        kwargs = self._build_payload(system, messages, max_tokens, tools)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(
                f"{_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=kwargs,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        return self._parse_response(data)

    def _build_payload(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
        tools: list[dict] | None,
    ) -> dict:
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
        return kwargs

    def _parse_response(self, data: dict) -> LLMResponse:

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""

        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            calls = [
                {
                    "name": ((tc.get("function") or {}).get("name") or ""),
                    "arguments": ((tc.get("function") or {}).get("arguments") or "{}"),
                }
                for tc in tool_calls
            ]
            text = json.dumps({"tool_calls": calls})

        usage = data.get("usage") or {}
        logging.info(
            "Groq: model=%s tokens in=%d out=%d",
            self.model,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

        return LLMResponse(
            content=text,
            model=self.model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            stop_reason=choice.get("finish_reason") or "stop",
            raw=data,
        )
