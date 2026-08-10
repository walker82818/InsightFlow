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


class DatasetDetailOut(DatasetSummaryOut):
    """Full representation including profile + preview."""

    profile: dict[str, Any] = {}
    preview: list[dict[str, Any]] = []


class DatasetUploadResponse(BaseModel):
    dataset: DatasetDetailOut
