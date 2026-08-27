"""LangGraph agent state (Phase 3).

Mirrors the design-doc ``AgentState`` but kept pragmatic: fields that should
accumulate across nodes (``events``, token counts) use an ``operator.add``
reducer so each node can return only its own delta.
"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict, total=False):
    user_query: str
    datasets: list[dict]  # Phase 9 多数据集: [{id,name,storage_path,file_type,table_name,schema_text}]
    schema_text: str
    # 语义层已确认口径（Design §6.1 规则#4 供 reviewer 做语义对齐提示）。
    semantic_metrics: list[str]
    semantic_dimensions: list[str]

    plan: list[dict]
    # ReAct 内循环的完整对话（含工具结果），供 reviewer 回边时「续跑」而非重建。
    # 存为 JSON 友好的 dict 列表；analysis_node 每次写回全量（last-writer-wins，无 reducer）。
    analysis_messages: list[dict]
    # 累积字段：重试回到 analysis 时，上一轮已查的证据必须保留（并集），
    # 因此用 operator.add 让每次返回的增量追加，而非 last-writer 覆盖。
    analysis_results: Annotated[list[dict], operator.add]  # every tool call: {tool, sql/code, result}
    sql_results: Annotated[list[dict], operator.add]  # {sql, result}
    python_results: Annotated[list[dict], operator.add]  # {code, result}
    visualizations: list[dict]  # ChartSpec dicts
    answer: str
    review_result: dict
    errors: list[str]

    retries: int
    status: str

    events: Annotated[list, operator.add]
    prompt_tokens: Annotated[int, operator.add]
    completion_tokens: Annotated[int, operator.add]
