"""RootCause domain model (2.0 Root Cause Analysis).

Result of the root-cause subgraph for a "why" question. The deterministic
core is the contribution decomposition (per-factor share of the change) which
is reproducible and auditable; the LLM only frames hypotheses & wording.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RootCause(Base):
    __tablename__ = "root_causes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text, default="")
    # {metric, delta, base_value, current_value, significant, reason}
    change: Mapped[str] = mapped_column(Text, default="{}")
    # [{hypothesis, status, evidence_ids}]
    hypotheses: Mapped[str] = mapped_column(Text, default="[]")
    # [{factor, contribution, contribution_pct, metric, evidence_ids}]
    contributions: Mapped[str] = mapped_column(Text, default="[]")
    conclusion: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # Top contributing factors, JSON array.
    factors: Mapped[str] = mapped_column(Text, default="[]")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
