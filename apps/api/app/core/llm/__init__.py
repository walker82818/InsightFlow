"""LLM provider abstraction (Phase 2).

All supported providers (DeepSeek / Qwen / 通义) speak the OpenAI-compatible
chat completions protocol, so a single client implementation covers them.
The factory selects the client by `settings.llm_provider` and resolves the
small/large model names used for the planner vs. summarizer split.
"""
from __future__ import annotations

from app.core.llm.base import (
    LLMClient,
    LLMMessage,
    LLMResponse,
    ModelSize,
)
from app.core.llm.factory import get_llm_client, get_model

__all__ = [
    "LLMClient",
    "LLMMessage",
    "LLMResponse",
    "ModelSize",
    "get_llm_client",
    "get_model",
]
