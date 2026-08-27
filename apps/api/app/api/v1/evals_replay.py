"""Evaluation 2.0 — evidence replay endpoints.

Independent of the Phase 8 golden-dataset harness (``evaluations.py``). Lets you
replay the evidence-based checks over any historical completed analysis:
  - ``GET /api/v1/evals/replay``           → list replayable analyses
  - ``GET /api/v1/evals/replay/{id}``      → replay-evaluate one analysis
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.session import AsyncSessionLocal
from app.services.eval_replay import evaluate_analysis, list_replayable

router = APIRouter(prefix="/api/v1/evals/replay", tags=["evals-replay"])


@router.get("")
async def replay_list(limit: int = 50) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        items = await list_replayable(session, limit=limit)
    return {"replayable": items, "count": len(items)}


@router.get("/{analysis_id}")
async def replay_one(analysis_id: str, min_confidence: float = 0.6, min_coverage: float = 0.5) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        report = await evaluate_analysis(
            session,
            analysis_id,
            min_confidence=min_confidence,
            min_coverage=min_coverage,
        )
    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])
    return report
