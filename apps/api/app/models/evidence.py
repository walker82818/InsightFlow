"""Evidence domain model (2.0 evidence-driven core).

A normalized node in the evidence chain: every claim (insight, root-cause
factor, reviewer check, analysis conclusion) is backed by one or more Evidence
rows. ``parent_id`` is reserved for the P1 evidence graph.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(Base):
    __tablename__ = "evidences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    # Null for upload-time insights; set for per-question evidence.
    analysis_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=True,
        index=True,
    )
    # Reserved for P1 evidence graph.
    parent_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    claim: Mapped[str] = mapped_column(Text, default="")
    metric: Mapped[str] = mapped_column(String(200), default="")
    dimensions: Mapped[str] = mapped_column(Text, default="[]")
    # sql | python | profile | semantic | llm_reasoning
    source: Mapped[str] = mapped_column(String(40), default="sql")
    sql: Mapped[str] = mapped_column(Text, default="")
    # {rows:[...], n, ...}
    result: Mapped[str] = mapped_column(Text, default="{}")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
