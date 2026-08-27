"""Semantic Layer (P0).

Auto-suggests business metrics & dimensions from the Data Profiler 2.0 schema
(column roles) using the *small* model. Outputs are persisted with
``status=auto``; the user can confirm/edit them (``status=confirmed``), and
confirmed definitions take precedence when injected into the agent context.

The suggestion is deliberately prompt-driven + JSON-constrained: the LLM only
translates the role/schema into business names & SQL expressions. Deterministic
fallback (rule-based) is applied when the LLM is unavailable.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.llm.base import LLMMessage, ModelSize
from app.core.llm.factory import get_llm_client
from app.services.profiler2 import (
    ROLE_DIMENSION,
    ROLE_METRIC,
    ROLE_NUMERIC_DIMENSION,
    ROLE_TIME,
)

_SUGGEST_SYSTEM = (
    "你是数据分析平台中的语义层建议器。根据给定的数据画像（列名/类型/角色），"
    "为用户建议业务指标（metrics）和维度（dimensions），供后续分析复用。"
    "只输出 JSON，不要多余文字。"
)

# time-like column keywords -> grain
_GRAIN_HINTS = {
    "year": "year",
    "quarter": "quarter",
    "month": "month",
    "week": "week",
    "day": "day",
}


def _agg_for_column(col_name: str) -> str:
    low = col_name.lower()
    if any(k in low for k in ("count", "qty", "quantity", "num", "数量", "个数")):
        return "sum"
    if any(k in low for k in ("price", "amount", "value", "sales", "revenue", "金额", "额", "价")):
        return "sum"
    if any(k in low for k in ("rate", "ratio", "percent", "avg", "mean", "率", "占比", "平均")):
        return "avg"
    return "sum"


def _suggest_dimensions(schema: dict[str, Any]) -> list[dict[str, Any]]:
    roles = schema.get("roles", {})
    out: list[dict[str, Any]] = []
    for col, role in roles.items():
        if role in (ROLE_TIME, ROLE_DIMENSION, ROLE_NUMERIC_DIMENSION):
            is_time = role == ROLE_TIME
            low = str(col).lower()
            grain = next((g for k, g in _GRAIN_HINTS.items() if k in low), "day")
            out.append(
                {
                    "name": str(col),
                    "column": str(col),
                    "is_time": is_time,
                    "granularity": grain if is_time else "",
                    "description": (
                        f"{col}（时间维度）" if is_time else f"{col}（分类维度）"
                    ),
                }
            )
    return out


def _suggest_metrics(schema: dict[str, Any]) -> list[dict[str, Any]]:
    roles = schema.get("roles", {})
    out: list[dict[str, Any]] = []
    for col, role in roles.items():
        if role == ROLE_METRIC:
            agg = _agg_for_column(str(col))
            out.append(
                {
                    "name": str(col),
                    "column": str(col),
                    "aggregation": agg,
                    "sql_expr": f"{agg.upper()}({col})",
                    "unit": "",
                    "description": f"{col}（数值指标，聚合方式 {agg}）",
                }
            )
    return out


def _extract_json(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to isolate the first {...} block.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


async def suggest_semantics(schema: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return {"metrics": [...], "dimensions": [...]} with ``status=auto`` set later."""
    # Rule-based fallback first (always available & deterministic).
    dimensions = _suggest_dimensions(schema)
    metrics = _suggest_metrics(schema)

    # Optionally refine via LLM (best-effort; never raise).
    try:
        client = get_llm_client(ModelSize.small)
        if not await client.is_configured():
            return {"metrics": metrics, "dimensions": dimensions}
        schema_brief = {
            "columns": [
                {
                    "name": c.get("name"),
                    "type": c.get("type"),
                    "role": schema.get("roles", {}).get(c.get("name")),
                }
                for c in schema.get("columns", [])
            ]
        }
        user = (
            "请根据画像输出语义层建议，JSON 格式："
            '{"metrics":[{"name","column","aggregation","unit","description"}],'
            '"dimensions":[{"name","column","is_time","granularity","description"}]}。'
            f"画像如下：\n{json.dumps(schema_brief, ensure_ascii=False)}"
        )
        resp = await client.chat(
            [
                LLMMessage(role="system", content=_SUGGEST_SYSTEM),
                LLMMessage(role="user", content=user),
            ],
            temperature=0.1,
        )
        parsed = _extract_json(resp.content)
        if parsed:
            if isinstance(parsed.get("metrics"), list) and parsed["metrics"]:
                metrics = [dict(m) for m in parsed["metrics"] if isinstance(m, dict)]
            if isinstance(parsed.get("dimensions"), list) and parsed["dimensions"]:
                dimensions = [
                    dict(d) for d in parsed["dimensions"] if isinstance(d, dict)
                ]
    except Exception:  # noqa: BLE001
        # Fall back to deterministic suggestions.
        pass

    for m in metrics:
        m["status"] = "auto"
    for d in dimensions:
        d.setdefault("status", "auto")
        d.setdefault("is_time", False)
        d.setdefault("granularity", "")
    return {"metrics": metrics, "dimensions": dimensions}
