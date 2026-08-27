"""Insight domain model (2.0 Insight Discovery).

Active insights produced by ``insight_node`` after upload, independent of any
user question. Each insight carries structured evidence + a confidence score so
the frontend can render it with provenance.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    # trend | anomaly | distribution_shift | top_contribution | correlation | quality
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200), default="")
    conclusion: Mapped[str] = mapped_column(Text, default="")
    metric: Mapped[str] = mapped_column(String(200), default="")
    dimensions: Mapped[str] = mapped_column(Text, default="[]")
    # Normalized Evidence-ish object (claim/result/sql/confidence).
    evidence: Mapped[str] = mapped_column(Text, default="{}")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # high | medium | low
    severity: Mapped[str] = mapped_column(String(20), default="low")
    sql: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
