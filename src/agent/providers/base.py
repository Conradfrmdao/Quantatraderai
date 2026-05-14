"""Base LLM provider interface — all providers implement this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: str          # raw text output
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "stop"
    # For multi-turn / tool-use providers that return structured blocks
    raw: object = field(default=None, repr=False)


class LLMProvider(ABC):
    """Minimal interface every LLM provider must satisfy."""

    name: str
    model: str

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Synchronous completion (called from the agent's sync context)."""
        ...

    async def acomplete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Async completion when the provider has a native non-blocking client."""
        raise NotImplementedError("Async completion is not implemented for this provider")

    @property
    def supports_tools(self) -> bool:
        """True if this provider supports function/tool calling."""
        return False

    @property
    def supports_thinking(self) -> bool:
        """True if this provider supports extended thinking."""
        return False
