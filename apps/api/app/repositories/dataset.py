"""Async repository for Dataset persistence (Phase 1)."""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dataset import Dataset, DatasetColumn
from app.schemas.dataset import DatasetColumnOut


def _to_summary(ds: Dataset) -> dict[str, Any]:
    source_type = ds.source_type or "file"
    db_info = None
    if source_type == "db" and ds.connection_json:
        try:
            conn = json.loads(ds.connection_json)
            db_info = {
                "db_type": conn.get("db_type"),
                "host": conn.get("host"),
                "port": conn.get("port"),
                "database": conn.get("database"),
                "schema": conn.get("schema"),
                "table": conn.get("table"),
            }
        except Exception:
            db_info = None
    return {
        "id": ds.id,
        "name": ds.name,
        "file_name": ds.file_name,
        "file_type": ds.file_type,
        "file_size": ds.file_size,
        "row_count": ds.row_count,
        "column_count": ds.column_count,
        "status": ds.status,
        "created_at": ds.created_at,
        "source_type": source_type,
        "db_info": db_info,
        "columns": [
            DatasetColumnOut(
                name=c.name, type=c.dtype, position=c.position,
                stats=json.loads(c.stats_json) if c.stats_json else {},
            )
            for c in ds.columns
        ],
    }


def to_detail(ds: Dataset) -> dict[str, Any]:
    summary = _to_summary(ds)
    summary["profile"] = json.loads(ds.profile_json) if ds.profile_json else {}
    summary["preview"] = json.loads(ds.preview_json) if ds.preview_json else []
    return summary


async def create_dataset(
    session: AsyncSession,
    *,
    user_id: str,
    name: str,
    file_name: str,
    file_type: str,
    file_size: int,
    storage_path: str,
    profile: dict[str, Any],
    preview: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    source_type: str = "file",
    connection_json: str = "{}",
) -> Dataset:
    ds = Dataset(
        user_id=user_id,
        name=name,
        file_name=file_name,
        file_type=file_type,
        file_size=file_size,
        storage_path=storage_path,
        source_type=source_type,
        connection_json=connection_json,
        row_count=profile.get("row_count", 0),
        column_count=profile.get("column_count", 0),
        profile_json=json.dumps(profile, default=str),
        preview_json=json.dumps(preview, default=str),
        status="ready",
    )
    ds.columns = [
        DatasetColumn(
            position=c["position"],
            name=c["name"],
            dtype=c["type"],
            stats_json=json.dumps(c.get("stats", {}), default=str),
        )
        for c in columns
    ]
    session.add(ds)
    await session.commit()
    # Eagerly load the relationship within the async session so callers can
    # serialize without triggering a lazy (greenlet) load.
    await session.refresh(ds, attribute_names=["columns"])
    return ds


async def get_dataset(session: AsyncSession, dataset_id: str) -> Dataset | None:
    res = await session.execute(
        select(Dataset)
        .where(Dataset.id == dataset_id)
        .options(selectinload(Dataset.columns))
    )
    return res.scalar_one_or_none()


async def list_datasets(session: AsyncSession, user_id: str) -> Sequence[Dataset]:
    res = await session.execute(
        select(Dataset)
        .where(Dataset.user_id == user_id)
        .options(selectinload(Dataset.columns))
        .order_by(Dataset.created_at.desc())
    )
    return res.scalars().all()


async def delete_dataset(session: AsyncSession, ds: Dataset) -> None:
    await session.delete(ds)
    await session.commit()
