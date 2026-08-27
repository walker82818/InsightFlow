"""Root-cause analysis service (2.0 Root Cause Analysis).

Deterministic contribution decomposition for "why" questions:
  - pick metric + time + dimension from the dataset's role schema;
  - split the timeline into first half vs second half;
  - compute the change of the metric across the two periods;
  - decompose each category's share of that change (its delta / total delta).

The LLM is *not* required for the numbers; ``conclusion`` is synthesized from
the deterministic decomposition. The ``change`` and ``contributions`` fields
mirror the ``RootCause`` model and are fully reproducible/auditable.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from app.core.llm import ModelSize, get_llm_client
from app.core.llm.base import LLMMessage
from app.services import profiler2

_WHY_HINTS = ("为什么", "为何", "原因", "根因", "导致", "为什么上涨", "为什么下降")


def is_why_question(query: str) -> bool:
    """Heuristic: does the question ask for a root cause?"""
    q = (query or "").strip()
    return any(h in q for h in _WHY_HINTS)


def _fmt(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f) and abs(f) < 1e15:
        return f"{int(f):,}"
    return f"{f:,.2f}"


def _pct(a: float, b: float) -> str:
    if b == 0:
        return "—"
    return f"{a / b * 100:.1f}%"


def _pick(df: pd.DataFrame, schema: dict[str, Any], role: str) -> str | None:
    roles = schema.get("roles", {})
    for col, r in roles.items():
        if r == role:
            return str(col)
    return None


def _json_safe(value: Any) -> Any:
    """Recursively coerce numpy scalars to native Python JSON types."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    # numpy bool / int / float
    if type(value).__module__ == "numpy":
        import numpy as np

        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
    return value


def run_root_cause(
    df: pd.DataFrame,
    schema: dict[str, Any],
    *,
    question: str,
    max_factors: int = 5,
    min_delta: float = 0.05,
) -> dict[str, Any] | None:
    """Compute root-cause decomposition. Returns a dict mirroring ``RootCause``
    (change / contributions / factors / conclusion / confidence) or None if the
    dataset lacks a metric + dimension to decompose.

    Design D5（变化显著性门槛）：当变化幅度 < ``min_delta``（默认 5%）或样本过少时，
    返回 ``significant=False`` 的"无根因可分析"结果，而不是强行编造根因。
    """
    metric = _pick(df, schema, profiler2.ROLE_METRIC)
    dim = _pick(df, schema, profiler2.ROLE_DIMENSION)
    time_col = _pick(df, schema, profiler2.ROLE_TIME)
    if metric is None or dim is None:
        return None

    work = df[[metric, dim]].copy()
    work[metric] = pd.to_numeric(work[metric], errors="coerce")
    work = work.dropna(subset=[metric])

    # Split by time when available, else by row order.
    if time_col is not None and time_col in df.columns:
        order = df[time_col]
    else:
        order = pd.Series(range(len(df)))

    order = order.reset_index(drop=True)
    work = work.reset_index(drop=True)
    n = len(work)
    half = n // 2
    first_mask = order.iloc[:half].index
    second_mask = order.iloc[half:].index

    first = work.loc[first_mask]
    second = work.loc[second_mask]
    total_first = first[metric].sum()
    total_second = second[metric].sum()
    delta = total_second - total_first

    def _insignificant(reason: str) -> dict[str, Any]:
        return _json_safe({
            "question": question,
            "change": {
                "metric": metric,
                "delta": round(float(delta), 4),
                "base_value": round(float(total_first), 4),
                "current_value": round(float(total_second), 4),
                "significant": False,
                "reason": reason,
            },
            "contributions": [],
            "factors": [],
            "conclusion": "变化不显著或无足够数据，无法给出可靠根因，故不做分解。",
            "confidence": 0.0,
        })

    # D5 门槛：样本过少直接拒答。
    if n < 6:
        return _insignificant("样本过少（<6 行），无根因可分析")
    # D5 门槛：无基准值或变化幅度低于阈值 → 拒答，不做根因分解。
    if total_first == 0 or abs(delta) / abs(total_first) < min_delta:
        return _insignificant(
            f"{metric} 变化幅度 {_pct(abs(delta), abs(total_first))} "
            f"低于显著性门槛 {min_delta * 100:.0f}%，无根因可分析"
        )

    # Decompose each category's contribution to the delta.
    first_by = first.groupby(dim)[metric].sum()
    second_by = second.groupby(dim)[metric].sum()
    all_dims = sorted(set(first_by.index) | set(second_by.index))
    contributions = []
    for factor in all_dims:
        v1 = first_by.get(factor, 0.0)
        v2 = second_by.get(factor, 0.0)
        contrib = v2 - v1
        contributions.append(
            {
                "factor": str(factor),
                "contribution": round(float(contrib), 4),
                "contribution_pct": round(contrib / delta, 4) if delta else 0.0,
                "metric": metric,
                "period": "half",
            }
        )
    contributions.sort(key=lambda c: abs(c["contribution_pct"]), reverse=True)
    top = contributions[0]
    direction = "上升" if delta > 0 else "下降"
    conclusion = (
        f"{metric} 前后半段{direction} {_fmt(abs(delta))}（{_fmt(total_first)} → {_fmt(total_second)}）。"
        f"主要拉动因素是「{top['factor']}」，贡献 {_pct(top['contribution_pct'], 1)}"
        f"（{_fmt(top['contribution'])}）。"
    )
    significant = abs(delta) / abs(total_first) >= 0.2
    return _json_safe({
        "question": question,
        "change": {
            "metric": metric,
            "delta": round(float(delta), 4),
            "base_value": round(float(total_first), 4),
            "current_value": round(float(total_second), 4),
            "significant": significant,
            "reason": f"{direction} {_pct(abs(delta), abs(total_first))}",
        },
        "contributions": contributions,
        "factors": [c["factor"] for c in contributions[:max_factors]],
        "conclusion": conclusion,
        "confidence": round(min(0.92, 0.6 + abs(top["contribution_pct"]) * 0.4), 2),
    })


_HYPOTHESIS_SYSTEM = """你是数据分析根因假设生成器。
你的输入是：数据集的字段角色、已确认的语义口径、以及确定性分解得到的"变化量"与"各因素贡献"。
任务：给出 2-4 条候选根因假设（hypothesis），解释该变化可能的原因。
硬性约束（违反即为失败）：
1. 只能写定性假设（例如"某地区/某产品线贡献了大部分变化"），禁止编造任何具体数字。
2. 只能使用输入中出现的字段名/因素名/语义口径名，不得凭空捏造不存在的维度或业务。
3. 输出必须是合法 JSON 数组，每个元素为字符串。不要输出任何多余文字。"""


async def generate_hypotheses(
    *,
    schema: dict[str, Any],
    semantic_names: list[str],
    change: dict[str, Any],
    contributions: list[dict[str, Any]],
    question: str,
) -> list[str]:
    """Design §5 步骤② — LLM generates 2-4 qualitative candidate hypotheses.

    The LLM frames *qualitative* hypotheses only (it never invents numbers); the
    auditable numbers come from the deterministic ``contributions`` decomposition.
    Returns a list of hypothesis strings; on any LLM failure returns [] (the
    deterministic core still persists).
    """
    roles = schema.get("roles", {})
    role_lines = "；".join(f"{col}→{r}" for col, r in roles.items()) or "（无角色标注）"
    top = sorted(contributions, key=lambda c: abs(c["contribution_pct"]), reverse=True)[:3]
    top_lines = "；".join(
        f"「{c['factor']}」贡献 {c['contribution_pct'] * 100:.1f}%"
        for c in top
    ) or "（无）"
    change_lines = (
        f"{change.get('metric')} 变化 {change.get('delta')}"
        f"（{change.get('base_value')} → {change.get('current_value')}）"
    )
    sem_lines = "、".join(semantic_names) or "（无已确认语义口径）"

    user = (
        f"问题：{question}\n"
        f"字段角色：{role_lines}\n"
        f"已确认语义口径：{sem_lines}\n"
        f"变化量：{change_lines}\n"
        f"各因素贡献：{top_lines}\n"
        "请输出候选根因假设（JSON 字符串数组，2-4 条，定性、不编数字、只引用上述字段）。"
    )
    try:
        client = get_llm_client(ModelSize.small)
        resp = await client.chat(
            [
                LLMMessage(role="system", content=_HYPOTHESIS_SYSTEM),
                LLMMessage(role="user", content=user),
            ],
            temperature=0.2,
            max_tokens=500,
        )
        text = (resp.content or "").strip()
        # Strip code fences if present.
        if text.startswith("```"):
            text = text.split("```", 2)[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(h).strip() for h in parsed if str(h).strip()][:4]
        return []
    except Exception:  # noqa: BLE001
        return []


async def _load_semantic_names(session, dataset_id: str) -> list[str]:
    """Load confirmed metric/dimension names for a dataset (used by hypotheses)."""
    try:
        from app.models.semantic import Dimension, Metric
        from sqlalchemy import select

        metrics = (
            await session.execute(
                select(Metric.name).where(
                    Metric.dataset_id == dataset_id, Metric.status == "confirmed"
                )
            )
        ).scalars().all()
        dims = (
            await session.execute(
                select(Dimension.name).where(
                    Dimension.dataset_id == dataset_id, Dimension.status == "confirmed"
                )
            )
        ).scalars().all()
        return list(metrics) + list(dims)
    except Exception:  # noqa: BLE001
        return []


async def persist_root_cause(
    session,
    *,
    analysis_id: str,
    dataset_id: str,
    question: str,
    df: pd.DataFrame,
    schema: dict[str, Any],
    min_delta: float = 0.05,
) -> dict[str, Any] | None:
    """Run the decomposition and persist into ``root_causes`` (replace old rows
    for the analysis). Returns the persisted payload dict or None.

    ``hypotheses`` combines the deterministic top factor (已证实) with 2-4 LLM
    qualitative hypotheses (待验证). The deterministic contribution decomposition
    is always the auditable core; LLM failures degrade gracefully to the
    deterministic hypothesis only.
    """
    from app.models.root_cause import RootCause
    from sqlalchemy import delete

    payload = run_root_cause(df, schema, question=question, min_delta=min_delta)
    if payload is None:
        return None

    contributions = payload.get("contributions") or []
    # Deterministic hypothesis: top factor is already confirmed by the numbers.
    hypotheses: list[dict[str, Any]] = []
    if contributions:
        top = sorted(
            contributions, key=lambda c: abs(c["contribution_pct"]), reverse=True
        )[0]
        hypotheses.append(
            {
                "hypothesis": (
                    f"因素「{top['factor']}」是主要拉动因素，"
                    f"贡献 {top['contribution_pct'] * 100:.1f}%。"
                ),
                "status": "已证实",
                "evidence_ids": [],
            }
        )

    # LLM qualitative hypotheses (待验证), never invents numbers.
    semantic_names = await _load_semantic_names(session, dataset_id)
    llm_hypotheses = await generate_hypotheses(
        schema=schema,
        semantic_names=semantic_names,
        change=payload.get("change", {}),
        contributions=contributions,
        question=question,
    )
    hypotheses += [
        {"hypothesis": h, "status": "待验证", "evidence_ids": []}
        for h in llm_hypotheses
    ]

    await session.execute(
        delete(RootCause).where(RootCause.analysis_id == analysis_id)
    )
    session.add(
        RootCause(
            dataset_id=dataset_id,
            analysis_id=analysis_id,
            question=question,
            change=json.dumps(payload["change"], ensure_ascii=False),
            hypotheses=json.dumps(hypotheses, ensure_ascii=False),
            contributions=json.dumps(contributions, ensure_ascii=False),
            conclusion=payload["conclusion"],
            confidence=payload["confidence"],
            factors=json.dumps(payload["factors"], ensure_ascii=False),
        )
    )
    await session.commit()

    # P1 evidence graph: write each factor as a derived evidence node linked to
    # its supporting raw SQL/python evidence (conclusion → data multi-hop).
    try:
        from app.services.evidence import persist_factor_evidences

        await persist_factor_evidences(
            session,
            analysis_id=analysis_id,
            dataset_id=dataset_id,
            contributions=contributions,
        )
    except Exception:  # noqa: BLE001
        pass

    payload["hypotheses"] = hypotheses
    return payload
