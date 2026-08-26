"""Dataset domain models (Phase 1).

Two tables follow the design doc:
- ``datasets``          : dataset-level metadata + profile + preview
- ``dataset_columns``   : per-column schema + statistics (field-level)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True)

    name: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))  # csv | xlsx | xls | json | postgres | mysql | sqlite
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(Text)

    # 数据来源类型：file（上传文件）| db（直连数据库）
    source_type: Mapped[str] = mapped_column(String(16), default="file", nullable=False)
    # 直连数据库的连接信息（含密码，仅服务端使用，API 响应中脱敏）
    connection_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)

    # Dataset-level profile, stored as JSON (missing totals, duplicate rows ...)
    profile_json: Mapped[str] = mapped_column(Text, default="{}")
    # First N rows for preview, stored as JSON array of objects
    preview_json: Mapped[str] = mapped_column(Text, default="[]")

    status: Mapped[str] = mapped_column(String(20), default="ready")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    columns: Mapped[list["DatasetColumn"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetColumn.position",
    )


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"
    __table_args__ = (UniqueConstraint("dataset_id", "name", name="uq_dataset_column"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(255))
    # Our logical type: string | integer | float | date | category | boolean
    dtype: Mapped[str] = mapped_column(String(20))
    # Per-column statistics, stored as JSON
    stats_json: Mapped[str] = mapped_column(Text, default="{}")

    dataset: Mapped["Dataset"] = relationship(back_populates="columns")
