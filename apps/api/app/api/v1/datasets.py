"""Dataset API (Phase 1).

Endpoints:
    POST   /api/v1/datasets        upload + validate + store + profile
    GET    /api/v1/datasets        list (current user)
    GET    /api/v1/datasets/{id}   detail (schema + profile + preview)
    DELETE /api/v1/datasets/{id}   delete record + storage object
"""
from __future__ import annotations

import json
import os
import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.repositories import dataset as repo
from app.schemas.dataset import DBConnectRequest, DatasetDetailOut, DatasetSummaryOut
from app.services import duckdb
from app.services.profiling import ProfilingError, profile_bytes, profile_dataframe
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
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
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
        result = profile_bytes(data, ext)
    except ProfilingError as exc:
        # Roll back stored bytes on profiling failure.
        await _storage().delete(storage_key)
        raise HTTPException(status_code=422, detail=f"cannot parse file: {exc}") from exc

    ds = await repo.create_dataset(
        session,
        user_id=settings.default_user_id,
        name=name or (file.filename or "untitled"),
        file_name=file.filename or "untitled",
        file_type=ext,
        file_size=file_size,
        storage_path=storage_key,
        profile=result["profile"],
        preview=result["preview"],
        columns=result["columns"],
    )
    return DatasetDetailOut(**repo.to_detail(ds))


@router.post("/connect", response_model=DatasetDetailOut, status_code=201)
async def connect_database(
    payload: DBConnectRequest,
    session: AsyncSession = Depends(get_session),
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
        info = duckdb.register_db_dataset(
            dataset_id,
            payload.db_type,
            conn,
            payload.table,
            payload.schema or "public",
        )
        df = duckdb.sample_table(info["table"])
        prof = profile_dataframe(df)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=422, detail=f"连接或导入数据库失败：{exc}"
        ) from exc

    ds = await repo.create_dataset(
        session,
        user_id=settings.default_user_id,
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
    return DatasetDetailOut(**repo.to_detail(ds))


@router.get("", response_model=list[DatasetSummaryOut])
async def list_datasets(
    session: AsyncSession = Depends(get_session),
) -> list[DatasetSummaryOut]:
    rows = await repo.list_datasets(session, settings.default_user_id)
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
