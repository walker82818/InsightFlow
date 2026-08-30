"""Agent2UI 错误自愈：iframe 渲染失败 → LLM 修复 ArtifactSpec。

流程（设计 §4）：前端拿到 iframe 的 ``{type:"error"}`` 后调用
``POST /analyses/{id}/artifact-repair``，本服务加载该次分析的上下文，
连同上次代码与报错一起交给 LLM 修复，返回新的 ArtifactSpec。
最多 3 轮（attempt 计数由前端维护）。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select

from app.agent.nodes import (
    ARTIFACT_VIZ_SYSTEM,
    _artifact_validation_error,
    _extract_artifact_spec,
)
from app.core.llm import ModelSize, get_llm_client
from app.core.llm.base import LLMMessage
from app.db.session import AsyncSessionLocal
from app.models.analysis import Analysis
from app.models.dataset import Dataset

logger = logging.getLogger(__name__)

REPAIR_SYSTEM = """你是 React 代码修复专家。下面是一次「Agent 生成的 TSX 组件在沙箱中渲染失败」的报错，\
请分析原因并输出修复后的完整组件。

硬性要求（与初次生成相同）：
1. 组件必须默认导出：export default function App({ data, theme }) { ... }
2. 只允许 import：react、react/jsx-runtime、react-dom/client、echarts。
3. 数据只能来自 props.data（对象数组），禁止硬编码数据；禁止 fetch / localStorage / document。
4. 输出格式（必须）：第一行 标题：<标题>，然后一个 ```tsx 代码块。除标题行与代码块外不要输出任何其他文字。
"""


def _field_context(result: dict[str, Any]) -> str:
    """从 analysis 结果中汇总可绘图字段（columns）信息，供修复参考。"""
    fields: set[str] = set()
    parts: list[str] = []
    for key in ("sql_results", "python_results"):
        for entry in result.get(key) or []:
            r = entry.get("result") or entry.get("output")
            if isinstance(r, dict):
                cols = r.get("columns")
                if isinstance(cols, list):
                    fields.update(str(c) for c in cols)
    if fields:
        parts.append("可用字段：" + ", ".join(sorted(fields)))
    sample_rows = (result.get("sql_results") or [{}])[0].get("result", {}).get("rows", [])
    if sample_rows:
        parts.append("样例：" + json.dumps(list(sample_rows)[:5], ensure_ascii=False)[:800])
    return "\n".join(parts) or "（无结构化字段信息）"


async def repair_artifact(
    analysis_id: str,
    spec: dict[str, Any],
    error: dict[str, Any],
) -> dict[str, Any]:
    """修复一次渲染失败的 artifact。

    Returns:
        {"repaired": True, "spec": {title, code, imports, data}}
        | {"repaired": False, "reason": str}
    """
    # 1) 加载分析上下文
    query = ""
    result: dict[str, Any] = {}
    dataset_names: list[str] = []
    async with AsyncSessionLocal() as db:
        analysis = await db.get(Analysis, analysis_id)
        if analysis is None:
            return {"repaired": False, "reason": "analysis not found"}
        query = analysis.query
        try:
            result = json.loads(analysis.result_json or "{}")
        except json.JSONDecodeError:
            result = {}
        ids = json.loads(analysis.dataset_ids) if analysis.dataset_ids else [analysis.dataset_id]
        if ids:
            rows = (
                await db.execute(select(Dataset).where(Dataset.id.in_(ids)))
            ).scalars().all()
            dataset_names = [d.name for d in rows]

    # 2) 构造修复上下文并调 LLM
    ctx = (
        f"用户问题：{query}\n"
        f"数据集：{'、'.join(dataset_names) or '-'}\n"
        f"{_field_context(result)}\n"
        f"上次生成的代码：\n{spec.get('code', '')}\n"
        f"运行时报错：{error.get('message', '')}\n"
        f"（错误位置：第 {error.get('line')} 行，第 {error.get('column')} 列）\n"
        "请分析报错原因并输出修复后的完整 TSX 组件。"
    )
    try:
        client = get_llm_client(ModelSize.large)
        resp = await client.chat(
            [
                LLMMessage(role="system", content=REPAIR_SYSTEM),
                LLMMessage(role="user", content=ctx),
            ],
            temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("artifact repair LLM call failed for %s", analysis_id)
        return {"repaired": False, "reason": f"修复调用失败：{exc}"}

    fixed = _extract_artifact_spec(
        resp.content, title_fallback=spec.get("title", ""), data=spec.get("data")
    )
    if fixed is None:
        return {"repaired": False, "reason": "修复结果无法解析（缺少 TSX 代码块）"}
    err = _artifact_validation_error(fixed)
    if err:
        return {"repaired": False, "reason": f"修复结果不合规：{err}"}
    return {"repaired": True, "spec": fixed}
