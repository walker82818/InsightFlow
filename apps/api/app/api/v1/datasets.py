"""Dataset API (Phase 1).

Endpoints:
    POST   /api/v1/datasets        upload + validate + store + profile
    GET    /api/v1/datasets        list (current user)
    GET    /api/v1/datasets/{id}   detail (schema + profile + preview)
    DELETE /api/v1/datasets/{id}   delete record + storage object
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.db.session import AsyncSessionLocal, get_session
from app.models.user import User
from app.repositories import dataset as repo
from app.schemas.dataset import DBConnectRequest, DatasetDetailOut, DatasetSummaryOut
from app.services import dataset_insight, dataset_profile, duckdb
from app.services.profiling import (
    ProfilingError,
    profile_bytes,
    profile_dataframe,
    read_dataframe,
)
from app.services.storage import StorageBackend, StorageError, build_storage

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


@lru_cache
def _storage() -> StorageBackend:
    return build_storage()


def _validate_upload(file: UploadFile, size: int) -> str:
    if size == 0:
        raise HTTPException(status_code=400, detail="empty file")
    if size > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"file too large: {size} > {settings.max_upload_size} bytes",
        )
    ext = os.path.splitext(file.filename or "")[1].lstrip(".").lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported extension '.{ext}'. "
            f"allowed: {settings.allowed_extensions}",
        )
    return ext


@router.post("", response_model=DatasetDetailOut, status_code=201)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
) -> DatasetDetailOut:
    data = await file.read()
    ext = _validate_upload(file, len(data))
    file_size = len(data)

    # Build a unique storage key and persist bytes.
    from app.services.storage import make_storage_key, uuid_key

    storage_key = make_storage_key(f"{uuid_key()}_{file.filename}")
    try:
        await _storage().save(
            storage_key, data, file.content_type or "application/octet-stream"
        )
    except StorageError as exc:
        raise HTTPException(status_code=500, detail=f"storage failed: {exc}") from exc

    try:
        # 文件解析与画像都是 CPU 密集的 pandas 运算，丢到线程池避免阻塞 event loop。
        df = await asyncio.to_thread(read_dataframe, data, ext)
        result = await asyncio.to_thread(profile_dataframe, df)
    except ProfilingError as exc:
        # Roll back stored bytes on profiling failure.
        await _storage().delete(storage_key)
        raise HTTPException(status_code=422, detail=f"cannot parse file: {exc}") from exc

    ds = await repo.create_dataset(
        session,
        user_id=user.id,
        name=name or (file.filename or "untitled"),
        file_name=file.filename or "untitled",
        file_type=ext,
        file_size=file_size,
        storage_path=storage_key,
        profile=result["profile"],
        preview=result["preview"],
        columns=result["columns"],
    )
    dataset_id = ds.id

    # 2.0: deterministic profiler runs synchronously (available immediately).
    schema_json = await dataset_profile.persist_profile(
        session, dataset_id=dataset_id, df=df, base_profile=result
    )
    # 2.0: deterministic insight node runs synchronously (fast, no LLM).
    await dataset_insight.persist_insights(
        session, dataset_id=dataset_id, df=df, schema_json=schema_json, base_profile=result
    )
    # 2.0: LLM-backed semantic suggestion runs in the background.
    background_tasks.add_task(_run_semantic_background, dataset_id, schema_json)

    return DatasetDetailOut(**repo.to_detail(ds))


@router.post("/connect", response_model=DatasetDetailOut, status_code=201)
async def connect_database(
    payload: DBConnectRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DatasetDetailOut:
    """直连数据库并把指定表物化为可分析的数据集（Agent 后续可像普通数据集一样查询）。"""
    dataset_id = str(uuid.uuid4())
    conn = {
        "db_type": payload.db_type,
        "host": payload.host,
        "port": payload.port,
        "username": payload.username,
        "password": payload.password,
        "database": payload.database,
        "schema": payload.schema,
        "table": payload.table,
    }
    try:
        # DB 扫描 / 采样 / 画像均为同步阻塞调用，丢到线程池避免阻塞 event loop。
        info = await asyncio.to_thread(
            duckdb.register_db_dataset,
            dataset_id,
            payload.db_type,
            conn,
            payload.table,
            payload.schema or "public",
        )
        df = await asyncio.to_thread(duckdb.sample_table, info["table"])
        prof = await asyncio.to_thread(profile_dataframe, df)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=422, detail=f"连接或导入数据库失败：{exc}"
        ) from exc

    ds = await repo.create_dataset(
        session,
        user_id=user.id,
        name=payload.name,
        file_name=payload.table,
        file_type=payload.db_type,
        file_size=0,
        storage_path="",
        profile=prof["profile"],
        preview=prof["preview"],
        columns=[
            {
                "name": c["name"],
                "type": c["type"],
                "position": c["position"],
                "stats": c["stats"],
            }
            for c in prof["columns"]
        ],
        source_type="db",
        connection_json=json.dumps(conn, default=str),
    )
    # 2.0: deterministic profiler sync (semantic suggestion background not wired
    # for DB imports in this batch to avoid blocking on DB sampling).
    await dataset_profile.persist_profile(
        session, dataset_id=ds.id, df=df, base_profile=prof
    )
    return DatasetDetailOut(**repo.to_detail(ds))


@router.get("", response_model=list[DatasetSummaryOut])
async def list_datasets(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[DatasetSummaryOut]:
    rows = await repo.list_datasets(session, user.id)
    return [DatasetSummaryOut(**repo._to_summary(d)) for d in rows]


@router.get("/{dataset_id}", response_model=DatasetDetailOut)
async def get_dataset(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),
) -> DatasetDetailOut:
    ds = await repo.get_dataset(session, dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return DatasetDetailOut(**repo.to_detail(ds))


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    ds = await repo.get_dataset(session, dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    storage_key = ds.storage_path
    await repo.delete_dataset(session, ds)
    try:
        await _storage().delete(storage_key)
    except StorageError:
        # Storage cleanup is best-effort; record already gone.
        pass


async def _run_semantic_background(
    dataset_id: str, schema_json: dict[str, Any]
) -> None:
    """Run the LLM-backed semantic suggestion in a fresh session (background)."""
    async with AsyncSessionLocal() as session:
        try:
            await dataset_profile.suggest_and_persist_semantic(
                session, dataset_id=dataset_id, schema_json=schema_json
            )
        except Exception:  # noqa: BLE001
            # Best-effort: a failed semantic suggestion must never break upload.
            pass


@router.get("/{dataset_id}/profile")
async def get_dataset_profile(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the 2.0 profile (quality score / issues / schema / anomalies)."""
    from app.models.dataset_profile import DatasetProfile

    prof = (
        await session.execute(
            select(DatasetProfile).where(DatasetProfile.dataset_id == dataset_id)
        )
    ).scalar_one_or_none()
    if prof is None:
        raise HTTPException(status_code=404, detail="2.0 profile not found (re-upload?)")
    return {
        "dataset_id": dataset_id,
        "quality_score": prof.quality_score,
        "issues": json.loads(prof.issues or "[]"),
        "schema": json.loads(prof.schema_json or "{}"),
        "anomalies": json.loads(prof.anomalies or "[]"),
        "generated_at": prof.generated_at.isoformat() if prof.generated_at else None,
    }


@router.get("/{dataset_id}/semantics")
async def get_dataset_semantics(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the semantic layer (metrics + dimensions) for a dataset."""
    from app.models.semantic import Dimension, Metric

    metrics = (
        await session.execute(
            select(Metric)
            .where(Metric.dataset_id == dataset_id)
            .order_by(Metric.status, Metric.created_at)
        )
    ).scalars().all()
    dimensions = (
        await session.execute(
            select(Dimension)
            .where(Dimension.dataset_id == dataset_id)
            .order_by(Dimension.status, Dimension.created_at)
        )
    ).scalars().all()
    return {
        "dataset_id": dataset_id,
        "metrics": [
            {
                "id": m.id,
                "name": m.name,
                "column": m.column,
                "aggregation": m.aggregation,
                "sql_expr": m.sql_expr,
                "unit": m.unit,
                "description": m.description,
                "status": m.status,
            }
            for m in metrics
        ],
        "dimensions": [
            {
                "id": d.id,
                "name": d.name,
                "column": d.column,
                "is_time": d.is_time,
                "granularity": d.granularity,
                "description": d.description,
                "status": d.status,
            }
            for d in dimensions
        ],
    }


@router.patch("/{dataset_id}/semantics/{item_type}/{item_id}/confirm")
async def confirm_semantic_item(
    dataset_id: str,
    item_type: str,
    item_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Human confirmation of a semantic-layer item (Design §0 #1 / §2).

    ``item_type`` ∈ {"metric","dimension"}. Flips ``status`` → ``confirmed`` so
    it becomes part of the agent's authoritative vocabulary (injected into the
    analysis state and used by Reviewer 2.0's semantic-alignment check).
    """
    from app.models.semantic import Dimension, Metric

    if item_type not in ("metric", "dimension"):
        raise HTTPException(status_code=400, detail="item_type must be metric|dimension")
    model = Metric if item_type == "metric" else Dimension
    item = await session.get(model, item_id)
    if item is None or str(item.dataset_id) != dataset_id:
        raise HTTPException(status_code=404, detail=f"{item_type} not found")
    item.status = "confirmed"
    await session.commit()
    return {"id": item_id, "type": item_type, "status": item.status}


@router.get("/{dataset_id}/insights")
async def get_dataset_insights(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the active insights (trend / anomaly / shift / contribution / ...)."""
    insights = await dataset_insight.load_insights(session, dataset_id)
    return {"dataset_id": dataset_id, "insights": insights}
