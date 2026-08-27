"""DatasetProfile domain model (2.0 Data Profiler).

Upgraded, standalone profile produced by ``profile_node`` after upload. Kept
separate from ``datasets.profile_json`` (which still holds the base column
stats) so the 2.0 quality score / field roles / relation hints / anomalies can
be queried independently and re-generated without touching the base profile.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DatasetProfile(Base):
    __tablename__ = "dataset_profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )

    # 0-100 deterministic quality score (see services/profiling.py).
    quality_score: Mapped[float] = mapped_column(Integer, default=0)
    # [{column, category, severity, message, suggestion}]
    issues: Mapped[str] = mapped_column(Text, default="[]")
    # {roles:{col: role}, relations:[{left_col,right_col,relation_type,strength}],
    #  columns:[{name, logical_type, cardinality, null_count, ...}]}
    schema_json: Mapped[str] = mapped_column(Text, default="{}")
    # [{column, kind, severity, value, message}]
    anomalies: Mapped[str] = mapped_column(Text, default="[]")

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
