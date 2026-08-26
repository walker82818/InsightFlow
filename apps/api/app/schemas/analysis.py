"""Analysis API schemas (Phase 2)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AnalysisCreate(BaseModel):
    dataset_id: str | None = Field(
        None,
        description="Backward-compatible single dataset id (prefer dataset_ids).",
    )
    dataset_ids: list[str] = Field(
        default_factory=list,
        description="Dataset ids for the (multi-document) analysis. Required if dataset_id is omitted.",
    )
    query: str = Field(..., min_length=1, max_length=2000)


class AnalysisOut(BaseModel):
    id: str
    dataset_id: str
    dataset_ids: list[str] = Field(default_factory=list)
    query: str
    status: str
    answer: str = ""
    result: dict = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnalysisSummaryOut(BaseModel):
    id: str
    dataset_id: str
    dataset_ids: list[str] = Field(default_factory=list)
    query: str
    status: str
    answer: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
