"""Dataset 2.0 profile + semantic layer orchestration (P0).

A single entry point used by the upload flow (and re-runnable later):

- ``persist_profile`` builds the Data Profiler 2.0 payload from a DataFrame +
  base profile and upserts it into ``dataset_profiles`` (deterministic, fast).
- ``suggest_and_persist_semantic`` runs the semantic layer suggestion (small
  LLM, best-effort) and persists metrics/dimensions, replacing previous
  ``auto`` rows while keeping ``confirmed`` ones.

Split so the deterministic profile is available immediately after upload while
the LLM-backed semantic suggestion can run in a background task.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset_profile import DatasetProfile
from app.models.semantic import Dimension, Metric
from app.services import profiler2
from app.services import semantic


async def persist_profile(
    session: AsyncSession,
    *,
    dataset_id: str,
    df: pd.DataFrame,
    base_profile: dict[str, Any],
) -> dict[str, Any]:
    """Build + persist the 2.0 profile. Returns the schema_json for semantic use."""
    # build_profile 是 CPU 密集的 pandas 计算，丢到线程池避免阻塞 event loop。
    payload = await asyncio.to_thread(profiler2.build_profile, df, base_profile)

    existing = (
        await session.execute(
            select(DatasetProfile).where(DatasetProfile.dataset_id == dataset_id)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = DatasetProfile(dataset_id=dataset_id)
        session.add(existing)
    existing.quality_score = int(payload["quality_score"])
    existing.issues = json.dumps(payload["issues"], ensure_ascii=False)
    existing.schema_json = json.dumps(
        payload["schema_json"], ensure_ascii=False, default=str
    )
    existing.anomalies = json.dumps(
        payload["anomalies"], ensure_ascii=False, default=str
    )
    await session.commit()
    return payload["schema_json"]


async def suggest_and_persist_semantic(
    session: AsyncSession,
    *,
    dataset_id: str,
    schema_json: dict[str, Any],
) -> dict[str, int]:
    """Suggest metrics/dimensions and persist them (auto rows replaced, confirmed kept)."""
    semantics = await semantic.suggest_semantics(schema_json)

    await session.execute(
        delete(Metric).where(Metric.dataset_id == dataset_id, Metric.status == "auto")
    )
    await session.execute(
        delete(Dimension).where(
            Dimension.dataset_id == dataset_id, Dimension.status == "auto"
        )
    )

    for m in semantics.get("metrics", []):
        session.add(
            Metric(
                dataset_id=dataset_id,
                name=str(m.get("name") or m.get("column") or ""),
                column=str(m.get("column") or ""),
                aggregation=str(m.get("aggregation") or "sum"),
                sql_expr=str(m.get("sql_expr") or ""),
                unit=str(m.get("unit") or ""),
                description=str(m.get("description") or ""),
                status=str(m.get("status") or "auto"),
            )
        )
    for d in semantics.get("dimensions", []):
        session.add(
            Dimension(
                dataset_id=dataset_id,
                name=str(d.get("name") or d.get("column") or ""),
                column=str(d.get("column") or ""),
                is_time=bool(d.get("is_time") or False),
                granularity=str(d.get("granularity") or ""),
                description=str(d.get("description") or ""),
                status=str(d.get("status") or "auto"),
            )
        )
    await session.commit()
    return {
        "metrics": len(semantics.get("metrics", [])),
        "dimensions": len(semantics.get("dimensions", [])),
    }
