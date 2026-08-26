"""Report API schemas (Phase 7)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ReportOut(BaseModel):
    id: str
    analysis_id: str
    format: str
    content: dict[str, Any]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_at: str | None = None

    model_config = {"from_attributes": True}
