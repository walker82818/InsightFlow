"""Semantic Layer domain models (2.0).

Business metrics & dimensions, auto-suggested by ``semantic_node`` from the
profile (status=auto) and confirmable/editable by the user (status=confirmed).
Confirmed definitions take precedence over auto ones when injected into the
planner / analysis context.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    # Business name, e.g. "销售额".
    name: Mapped[str] = mapped_column(String(200))
    # Column(s) backing the metric.
    column: Mapped[str] = mapped_column(String(200))
    # Aggregation: sum | avg | count | count_distinct | min | max.
    aggregation: Mapped[str] = mapped_column(String(40), default="sum")
    # Optional expression override, e.g. "SUM(amount) * 1.13".
    sql_expr: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(40), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    # auto | confirmed
    status: Mapped[str] = mapped_column(String(20), default="auto")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Dimension(Base):
    __tablename__ = "dimensions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    column: Mapped[str] = mapped_column(String(200))
    is_time: Mapped[bool] = mapped_column(default=False)
    # For time dimensions: day | month | quarter | year | week.
    granularity: Mapped[str] = mapped_column(String(20), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    # auto | confirmed
    status: Mapped[str] = mapped_column(String(20), default="auto")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
