from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import Report


async def get_report(session: AsyncSession, analysis_id: str) -> Report | None:
    res = await session.execute(select(Report).where(Report.analysis_id == analysis_id))
    return res.scalar_one_or_none()


async def save_report(
    session: AsyncSession,
    *,
    analysis_id: str,
    content: dict[str, Any],
    html: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    fmt: str = "html",
) -> Report:
    """Upsert the report for an analysis (one report per analysis)."""
    existing = await get_report(session, analysis_id)
    if existing is not None:
        existing.format = fmt
        existing.content_json = content
        existing.html = html
        existing.prompt_tokens = prompt_tokens
        existing.completion_tokens = completion_tokens
        await session.commit()
        await session.refresh(existing)
        return existing

    report = Report(
        analysis_id=analysis_id,
        format=fmt,
        content_json=content,
        html=html,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report
