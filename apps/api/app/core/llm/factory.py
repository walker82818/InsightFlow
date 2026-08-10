"""LLM client factory and model resolution."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.llm.base import LLMClient, ModelSize
from app.core.llm.openai_compat import OpenAICompatibleClient


@lru_cache
def get_llm_client(_size: ModelSize = ModelSize.small) -> LLMClient:
    """Return a provider client bound to the requested model size.

    All providers are OpenAI-compatible today; the factory exists so future
    providers (Anthropic, etc.) can be slotted in without touching the agent.
    The small client uses ``settings.small_model`` (schema / simple tasks);
    the large client uses ``settings.large_model`` (planning / summaries).
    """
    if settings.llm_provider in ("deepseek", "qwen", "tongyi", "openai"):
        return OpenAICompatibleClient(model=get_model(_size))
    raise ValueError(f"unsupported LLM provider: {settings.llm_provider}")


def get_model(size: ModelSize) -> str:
    """Resolve the configured model name for a given size."""
    if size == ModelSize.large:
        return settings.large_model
    return settings.small_model
