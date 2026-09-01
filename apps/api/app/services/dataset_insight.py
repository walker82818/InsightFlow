"""Insight node orchestration + persistence (P0).

``persist_insights`` runs the deterministic insight node on a DataFrame and
persists results into ``insights``, replacing all previous rows for the
dataset. It is invoked after upload (background), so insights are available
immediately on the dataset detail page.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insight import Insight
from app.services import insight_node


async def persist_insights(
    session: AsyncSession,
    *,
    dataset_id: str,
    df: pd.DataFrame,
    schema_json: dict[str, Any],
    base_profile: dict[str, Any],
    max_insights: int = 12,
) -> int:
    """Compute + persist insights. Returns the number stored."""
    # run_insight_node 是 CPU 密集的 pandas 计算，丢到线程池避免阻塞 event loop。
    insights = await asyncio.to_thread(
        insight_node.run_insight_node,
        df,
        schema_json,
        base_profile,
        max_insights=max_insights,
    )

    await session.execute(delete(Insight).where(Insight.dataset_id == dataset_id))

    for ins in insights:
        session.add(
            Insight(
                dataset_id=dataset_id,
                kind=str(ins.get("kind") or ""),
                title=str(ins.get("title") or ""),
                conclusion=str(ins.get("conclusion") or ""),
                metric=str(ins.get("metric") or ""),
                dimensions=json.dumps(ins.get("dimensions") or [], ensure_ascii=False),
                evidence=json.dumps(
                    ins.get("evidence") or {}, ensure_ascii=False, default=str
                ),
                confidence=float(ins.get("confidence") or 0.0),
                severity=str(ins.get("severity") or "low"),
                sql=str(ins.get("sql") or ""),
            )
        )
    await session.commit()
    return len(insights)


async def load_insights(
    session: AsyncSession, dataset_id: str
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Insight)
            .where(Insight.dataset_id == dataset_id)
            .order_by(Insight.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "dataset_id": r.dataset_id,
            "kind": r.kind,
            "title": r.title,
            "conclusion": r.conclusion,
            "metric": r.metric,
            "dimensions": json.loads(r.dimensions or "[]"),
            "evidence": json.loads(r.evidence or "{}"),
            "confidence": r.confidence,
            "severity": r.severity,
            "sql": r.sql,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
