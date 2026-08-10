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
    dataset_id: str,
    query: str,
) -> Analysis:
    row = Analysis(user_id=user_id, dataset_id=dataset_id, query=query, status="pending")
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_analysis(session: AsyncSession, analysis_id: str) -> Analysis | None:
    return await session.get(Analysis, analysis_id)


async def list_analyses(
    session: AsyncSession, user_id: str, limit: int = 50
) -> list[Analysis]:
    stmt = (
        select(Analysis)
        .where(Analysis.user_id == user_id)
        .order_by(Analysis.created_at.desc())
        .limit(limit)
    )
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


def to_summary(row: Analysis) -> dict[str, Any]:
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "query": row.query,
        "status": row.status,
        "created_at": row.created_at,
    }


def to_detail(row: Analysis) -> dict[str, Any]:
    try:
        result = json.loads(row.result_json) if row.result_json else {}
    except json.JSONDecodeError:
        result = {}
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "query": row.query,
        "status": row.status,
        "answer": row.answer,
        "result": result,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
