"""LLM client interface and message types."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class ModelSize(str, Enum):
    small = "small"
    large = "large"


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: Any | None = None


class LLMClient:
    """Minimal chat-completions contract used by the agent loop."""

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Literal["auto", "none"] = "auto",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    async def is_configured(self) -> bool:
        return True
