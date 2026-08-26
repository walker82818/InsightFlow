"""Phase 8: Evaluation API.

Exposes the golden-dataset evaluation harness over HTTP so it can be triggered
and inspected without the CLI. Running a full evaluation hits the LLM for every
case (and every ``evaluate_report`` case), so ``POST /run`` runs in the
background and ``GET`` returns the latest result.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter

from evals.runner import run_all

router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])

_STATE: dict[str, Any] = {"running": False, "result": None}


def _datasets_dir() -> str:
    # evaluations.py lives in apps/api/app/api/v1 -> go up 4 levels to apps/api
    api_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    return os.path.join(api_root, "evals", "datasets")


@router.get("")
async def list_evaluations() -> dict[str, Any]:
    """List available golden datasets and their case counts."""
    from evals.runner import _load_datasets

    datasets = _load_datasets(_datasets_dir())
    return {
        "running": _STATE["running"],
        "datasets": [
            {"name": name, "cases": len(ds.get("cases", []))}
            for name, ds in datasets.items()
        ],
        "last_result": _STATE["result"],
    }


@router.post("/run")
async def run_evaluations(names: list[str] | None = None) -> dict[str, Any]:
    """Trigger a (background) evaluation run over the golden datasets."""
    if _STATE["running"]:
        return {"status": "already_running"}

    async def _job() -> None:
        _STATE["running"] = True
        try:
            _STATE["result"] = await run_all(dataset_names=names)
        finally:
            _STATE["running"] = False

    asyncio.create_task(_job())
    return {
        "status": "started",
        "note": "evaluation is running in the background; poll GET /api/v1/evaluations for results",
    }
