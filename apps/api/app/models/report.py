from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Report(Base):
    """Persisted analysis report (one per analysis).

    content_json stores the structured report (summary / findings / evidence /
    charts / recommendations). html stores a standalone, self-contained HTML
    document for export / print.
    """

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("analyses.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    format: Mapped[str] = mapped_column(String, default="html")
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    html: Mapped[str] = mapped_column(Text, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "analysis_id": self.analysis_id,
            "format": self.format,
            "content": self.content_json,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
