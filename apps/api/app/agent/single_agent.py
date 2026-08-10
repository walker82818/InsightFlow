"""Single-agent ReAct analysis loop (Phase 2).

A pragmatic single-agent: the LLM reasons about a natural-language question,
decides SQL, and we execute it through the read-only DuckDB tool. This is the
"single agent" milestone; Phase 3 will migrate this loop onto LangGraph with
checkpointing + streaming, so the event shapes here are intentionally close to
the final AgentEvent contract (see design doc §10.4).
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agent.tools import SQL_TOOL_SPEC, run_sql_tool
from app.core.llm import ModelSize, get_llm_client
from app.core.llm.base import LLMMessage, ToolCall

SYSTEM_PROMPT = """你是一名严谨的数据分析助手。你只能通过 `sql_execute` 工具用 DuckDB SQL \
分析「当前数据集表」。规则：
1. 只能写只读 SQL（SELECT/WITH/SHOW/DESCRIBE/EXPLAIN），不要尝试写入。
2. 优先聚合与分组，避免 SELECT * 返回过多行。
3. 每次只写一条 SQL；基于上一轮结果决定下一步。
4. 拿到足够证据后，用中文给出最终结论，并引用关键数字与所用 SQL。
5. 如果数据无法回答问题，如实说明并解释原因。
"""


@dataclass
class DatasetRef:
    id: str
    name: str
    storage_path: str
    file_type: str
    table_name: str
    schema_text: str


@dataclass
class AnalysisResult:
    answer: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    sql_results: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


async def run_analysis(
    ref: DatasetRef,
    user_query: str,
    max_steps: int = 6,
) -> AsyncIterator[dict[str, Any]]:
    """Run the ReAct loop, yielding AgentEvent dicts as it progresses.

    The final event is ``{"type": "agent_end", "content": ..., "result": {...}}``.
    """
    client = get_llm_client(ModelSize.small)

    yield {"type": "agent_start", "agent": "analysis"}

    messages: list[LLMMessage] = [
        LLMMessage(role="system", content=SYSTEM_PROMPT),
        LLMMessage(
            role="user",
            content=(
                f"数据集：{ref.name}\n"
                f"可用表名：{ref.table_name}\n"
                f"表结构：\n{ref.schema_text}\n\n"
                f"用户问题：{user_query}"
            ),
        ),
    ]

    result = AnalysisResult(answer="")
    tools = [SQL_TOOL_SPEC]

    for step in range(max_steps):
        try:
            resp = await client.chat(messages, tools=tools, temperature=0.0)
        except RuntimeError as exc:
            yield {"type": "error", "message": str(exc)}
            return

        result.prompt_tokens += resp.prompt_tokens
        result.completion_tokens += resp.completion_tokens

        # Final natural-language answer (no tool calls) -> done.
        if not resp.tool_calls:
            if resp.content:
                result.answer = resp.content
                yield {"type": "message", "content": resp.content}
            break

        # Persist the assistant turn (with its tool_calls) for the next call.
        messages.append(
            LLMMessage(role="assistant", content=resp.content, tool_calls=resp.tool_calls)
        )

        for tc in resp.tool_calls:
            result.tool_calls += 1
            sql = (tc.arguments or {}).get("sql", "")
            yield {"type": "tool_start", "tool": "sql_execute", "input": {"sql": sql}}
            try:
                tool_out = run_sql_tool(
                    ref.id, ref.storage_path, ref.file_type, sql
                )
            except Exception as exc:  # noqa: BLE001
                tool_out = {"error": str(exc)}
            yield {"type": "tool_end", "tool": "sql_execute", "result": tool_out}

            result.sql_results.append({"sql": sql, "result": tool_out})
            result.steps.append({"tool": "sql_execute", "sql": sql, "result": tool_out})
            messages.append(
                LLMMessage(
                    role="tool",
                    content=_summarize_tool(tool_out),
                    tool_call_id=tc.id,
                    name="sql_execute",
                )
            )

    # If we exhausted steps without a final answer, ask the model to conclude.
    if not result.answer:
        try:
            resp = await client.chat(messages, tools=tools, temperature=0.0)
            result.prompt_tokens += resp.prompt_tokens
            result.completion_tokens += resp.completion_tokens
            if resp.content:
                result.answer = resp.content
                yield {"type": "message", "content": resp.content}
        except RuntimeError as exc:
            yield {"type": "error", "message": str(exc)}
            return

    yield {
        "type": "agent_end",
        "content": result.answer,
        "result": {
            "answer": result.answer,
            "steps": result.steps,
            "sql_results": result.sql_results,
            "tool_calls": result.tool_calls,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        },
    }


def _summarize_tool(tool_out: dict[str, Any]) -> str:
    """Compact tool result for the LLM context (avoids huge row dumps)."""
    if "error" in tool_out:
        return f"SQL 执行出错: {tool_out['error']}"
    cols = tool_out.get("columns", [])
    rows = tool_out.get("rows", [])
    rc = tool_out.get("row_count", len(rows))
    truncated = tool_out.get("truncated", False)
    head = rows[:10]
    preview = "\n".join(
        " | ".join(str(v) for v in row) for row in head
    )
    note = f"(共 {rc} 行{'，已截断' if truncated else ''})"
    return f"列: {cols}\n{note}\n示例:\n{preview}"
