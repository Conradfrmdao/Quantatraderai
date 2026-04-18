"""Ollama provider — run LLMs locally for free, completely offline.

Install Ollama: https://ollama.com
Pull a model:  ollama pull llama3.2
               ollama pull mistral
               ollama pull qwen2.5:14b   (good for finance)
               ollama pull deepseek-r1   (reasoning model)

Set OLLAMA_BASE_URL (default: http://localhost:11434) and
LLM_MODEL (e.g. "llama3.2") in .env.

No API key needed — fully local and free.
"""

from __future__ import annotations

import json
import logging

import requests

from src.agent.providers.base import LLMProvider, LLMResponse
from src.config_loader import CONFIG


class OllamaProvider(LLMProvider):
    name = "ollama"

    DEFAULT_MODEL = "llama3.2"

    def __init__(self, model: str | None = None):
        self.model = model or CONFIG.get("llm_model") or self.DEFAULT_MODEL
        self.base_url = (CONFIG.get("ollama_base_url") or "http://localhost:11434").rstrip("/")

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        # Ollama's /api/chat endpoint accepts OpenAI-style messages
        ollama_messages = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg.get("role") or "user"
            content = msg.get("content") or ""
            if isinstance(content, list):
                content = " ".join(
                    c.get("text") or c.get("content") or ""
                    for c in content if isinstance(c, dict)
                )
            ollama_messages.append({"role": role, "content": content})

        payload: dict = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("message") or {}).get("content") or ""
            prompt_tokens = (data.get("prompt_eval_count") or 0)
            output_tokens = (data.get("eval_count") or 0)
            logging.info("Ollama: model=%s tokens in=%d out=%d", self.model, prompt_tokens, output_tokens)
            return LLMResponse(
                content=text,
                model=self.model,
                input_tokens=prompt_tokens,
                output_tokens=output_tokens,
                stop_reason=data.get("done_reason") or "stop",
                raw=data,
            )
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is Ollama running? Start it with: ollama serve"
            )
        except Exception as e:
            logging.error("Ollama error: %s", e)
            return LLMResponse(content="", model=self.model, stop_reason="error")
