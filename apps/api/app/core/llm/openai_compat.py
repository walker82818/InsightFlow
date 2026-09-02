"""OpenAI-compatible chat client (DeepSeek / Qwen / 通义 / OpenAI)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.llm.base import (
    LLMClient,
    LLMMessage,
    LLMResponse,
    LLMTimeoutError,
    ModelSize,
    ToolCall,
)


def _role_normalize(role: str) -> str:
    # Provider APIs accept system/user/assistant/tool.
    return role


class OpenAICompatibleClient(LLMClient):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = base_url or settings.llm_base_url
        self._api_key = api_key if api_key is not None else settings.llm_api_key
        self._default_model = model
        self._client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=self._api_key or "sk-missing",
        )

    async def is_configured(self) -> bool:
        return bool(self._api_key) and self._api_key not in (
            "",
            "sk-your-key-here",
        )

    def _to_openai_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            msg: dict[str, Any] = {"role": _role_normalize(m.role)}
            if m.content is not None:
                msg["content"] = m.content
            if m.name:
                msg["name"] = m.name
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in m.tool_calls
                ]
            out.append(msg)
        return out

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Literal["auto", "none"] = "auto",  # noqa: ARG002
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> LLMResponse:
        if not await self.is_configured():
            raise RuntimeError(
                "LLM_API_KEY is not configured. Set LLM_API_KEY in apps/api/.env "
                "(e.g. a DeepSeek / Qwen / 通义 key) to enable the analysis agent."
            )
        kwargs: dict[str, Any] = {
            "model": self._default_model or settings.small_model,
            "messages": self._to_openai_messages(messages),
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        # 单次调用超时：偶发 API 挂起时快速失败（抛 LLMTimeoutError —— RuntimeError
        # 的子类，既有捕获 RuntimeError 的节点逻辑不受影响），避免一次挂起耗尽整条
        # pipeline 的墙钟预算。默认用全局 llm_call_timeout；调用方可传更短的 timeout
        # 控制局部预算（如可视化节点的超时重试）。
        effective_timeout = timeout if timeout is not None else settings.llm_call_timeout
        try:
            resp = await asyncio.wait_for(
                self._client.chat.completions.create(**kwargs),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(
                f"LLM 调用超时（超过 {effective_timeout}s）",
                timeout=effective_timeout,
            ) from exc
        choice = resp.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        for tc in getattr(message, "tool_calls", None) or []:
            args = tc.function.arguments or "{}"
            try:
                parsed = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                parsed = {}
            tool_calls.append(
                ToolCall(id=tc.id, name=tc.function.name, arguments=parsed)
            )

        usage = resp.usage
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            model=resp.model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            raw=resp,
        )
