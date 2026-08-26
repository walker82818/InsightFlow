"""Pydantic schemas for the Dataset API (Phase 1)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DatasetColumnOut(BaseModel):
    name: str
    type: str
    position: int
    stats: dict[str, Any] = {}


class DbInfoOut(BaseModel):
    """直连数据库的连接摘要（脱敏，不含密码）。"""

    model_config = ConfigDict(from_attributes=True)

    db_type: str
    host: str | None = None
    port: int | None = None
    database: str | None = None
    schema: str | None = None
    table: str


class DatasetSummaryOut(BaseModel):
    """Lightweight representation for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    file_name: str
    file_type: str
    file_size: int
    row_count: int
    column_count: int
    status: str
    created_at: datetime
    columns: list[DatasetColumnOut] = []
    source_type: str = "file"
    db_info: DbInfoOut | None = None


class DatasetDetailOut(DatasetSummaryOut):
    """Full representation including profile + preview."""

    profile: dict[str, Any] = {}
    preview: list[dict[str, Any]] = []


class DatasetUploadResponse(BaseModel):
    dataset: DatasetDetailOut


class DBConnectRequest(BaseModel):
    """直连数据库并导入为数据集的请求。"""

    name: str
    db_type: str  # postgres | mysql | sqlite
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    database: str | None = None  # 库名（postgres/mysql）或文件路径（sqlite）
    schema: str | None = "public"
    table: str
