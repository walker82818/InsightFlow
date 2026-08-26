"""Analysis domain model (Phase 2).

One analysis = one natural-language question against one dataset. The agent
result (answer + steps + sql results + token usage) is persisted as JSON so it
can be reloaded without re-running the agent.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    # JSON array of dataset ids participating in this (possibly multi-document)
    # analysis. `dataset_id` above is the representative/primary dataset (== the
    # first id in this list).
    dataset_ids: Mapped[str] = mapped_column(Text, default="[]")

    query: Mapped[str] = mapped_column(Text)
    # pending -> running -> completed | error
    status: Mapped[str] = mapped_column(String(20), default="pending")

    answer: Mapped[str] = mapped_column(Text, default="")
    # Full agent result (steps, sql_results, token usage) as JSON text.
    result_json: Mapped[str] = mapped_column(Text, default="{}")

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
