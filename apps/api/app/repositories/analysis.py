"""Analysis persistence (Phase 2)."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis


async def create_analysis(
    session: AsyncSession,
    *,
    user_id: str,
    dataset_ids: list[str],
    query: str,
    dataset_id: str | None = None,
) -> Analysis:
    if not dataset_id:
        dataset_id = dataset_ids[0]
    row = Analysis(
        user_id=user_id,
        dataset_id=dataset_id,
        dataset_ids=json.dumps(dataset_ids, ensure_ascii=False),
        query=query,
        status="pending",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_analysis(session: AsyncSession, analysis_id: str) -> Analysis | None:
    return await session.get(Analysis, analysis_id)


async def list_analyses(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    dataset_id: str | None = None,
) -> list[Analysis]:
    stmt = select(Analysis).where(Analysis.user_id == user_id)

    if dataset_id:
        # Match the primary dataset or any dataset listed in the JSON `dataset_ids`.
        stmt = stmt.where(
            (Analysis.dataset_id == dataset_id)
            | Analysis.dataset_ids.contains(f'"{dataset_id}"')
        )

    stmt = stmt.order_by(Analysis.created_at.desc()).limit(limit).offset(offset)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def set_running(session: AsyncSession, row: Analysis) -> None:
    row.status = "running"
    session.add(row)
    await session.commit()


async def finish_analysis(
    session: AsyncSession,
    row: Analysis,
    *,
    status: str,
    answer: str = "",
    result: dict[str, Any] | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    row.status = status
    row.answer = answer
    row.result_json = json.dumps(result or {}, ensure_ascii=False)
    row.prompt_tokens = prompt_tokens
    row.completion_tokens = completion_tokens
    session.add(row)
    await session.commit()


def _parse_ids(raw: Any) -> list[str]:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def to_summary(row: Analysis) -> dict[str, Any]:
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "dataset_ids": _parse_ids(row.dataset_ids),
        "query": row.query,
        "status": row.status,
        "answer": (row.answer or "")[:200],
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def to_detail(row: Analysis) -> dict[str, Any]:
    try:
        result = json.loads(row.result_json) if row.result_json else {}
    except json.JSONDecodeError:
        result = {}
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "dataset_ids": _parse_ids(row.dataset_ids),
        "query": row.query,
        "status": row.status,
        "answer": row.answer,
        "result": result,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def get_trace(
    session: AsyncSession, analysis_id: str
) -> dict[str, Any] | None:
    """Return the latest AgentRun trace (run summary + steps + tool calls)."""
    from app.models.trace import AgentRun, AgentStep, ToolCall

    run = (
        await session.execute(
            select(AgentRun)
            .where(AgentRun.analysis_id == analysis_id)
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None:
        return None

    steps = (
        await session.execute(
            select(AgentStep)
            .where(AgentStep.run_id == run.id)
            .order_by(AgentStep.order_idx)
        )
    ).scalars().all()
    tool_calls = (
        await session.execute(
            select(ToolCall)
            .where(ToolCall.run_id == run.id)
            .order_by(ToolCall.ts_ms)
        )
    ).scalars().all()
    return {
        "run": run.to_summary(),
        "steps": [s.to_dict() for s in steps],
        "tool_calls": [t.to_dict() for t in tool_calls],
    }
