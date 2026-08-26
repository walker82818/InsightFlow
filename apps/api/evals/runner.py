"""Evaluation runner (Phase 8).

Materialises a golden dataset into DuckDB, drives the *real* analysis pipeline
(``app.agent.single_agent.run_analysis``) for each case, scores the outputs with
the deterministic evaluators, and aggregates the design-doc metrics.
"""
from __future__ import annotations

import csv
import json
import os
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.single_agent import DatasetRef, run_analysis
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models.analysis import Analysis
from app.models.dataset import Dataset
from app.repositories import analysis as repo
from app.services.duckdb import register_dataset
from app.core.config import settings

from .evaluators.correctness import evaluate as eval_correctness
from .evaluators.tool_usage import evaluate as eval_tool_usage
from .evaluators.visualization import evaluate as eval_visualization
from .evaluators.report import evaluate as eval_report

# Fixed default user id (auth is disabled in this phase).
EVAL_USER_ID = "00000000-0000-0000-0000-000000000000"
_SCORE_THRESHOLD = 0.6


async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _load_datasets(datasets_dir: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fn in sorted(os.listdir(datasets_dir)):
        if fn.endswith(".json"):
            with open(os.path.join(datasets_dir, fn), encoding="utf-8") as f:
                out[fn[:-5]] = json.load(f)
    return out


def _guess_type(rows: list[list], i: int) -> str:
    for r in rows:
        v = r[i]
        if v is None:
            continue
        if isinstance(v, bool):
            return "boolean"
        if isinstance(v, float):
            return "float"
        if isinstance(v, int):
            return "integer"
        if isinstance(v, str):
            s = v.strip()
            try:
                float(s)
                return "float"
            except ValueError:
                return "string"
    return "string"


def _materialize(dataset: dict) -> tuple[str, str, str, str]:
    """Write the inline rows to a CSV and register it with DuckDB.

    Returns ``(dataset_id, table_name, storage_path, schema_text)``.
    """
    ds_id = "eval_" + uuid.uuid4().hex[:12]
    cols = dataset["columns"]
    rows = dataset["rows"]
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    fname = f"{ds_id}.csv"
    fpath = os.path.join(upload_dir, fname)
    with open(fpath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
    table = register_dataset(ds_id, fname, "csv")
    schema_text = "columns: " + ", ".join(
        f"{c}({_guess_type(rows, i)})" for i, c in enumerate(cols)
    )
    return ds_id, table, fname, schema_text


async def run_case(
    dataset: dict,
    case: dict,
    dataset_id: str,
    table: str,
    storage_path: str,
    schema_text: str,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        ds_row = Dataset(
            id=dataset_id,
            user_id=EVAL_USER_ID,
            name=dataset["name"],
            file_name=storage_path,
            file_type="csv",
            storage_path=storage_path,
            row_count=len(dataset["rows"]),
            column_count=len(dataset["columns"]),
            profile_json="{}",
            preview_json="[]",
            status="ready",
        )
        session.add(ds_row)
        analysis = Analysis(
            dataset_id=dataset_id,
            query=case["question"],
            status="pending",
            answer="",
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)
        analysis_id = analysis.id

    ref = DatasetRef(
        id=dataset_id,
        name=dataset["name"],
        storage_path=storage_path,
        file_type="csv",
        table_name=table,
        schema_text=schema_text,
    )

    try:
        async for _ in run_analysis(ref, case["question"], analysis_id):
            pass
    except Exception:  # noqa: BLE001
        pass

    async with AsyncSessionLocal() as session:
        analysis = await session.get(Analysis, analysis_id)
        result = json.loads(analysis.result_json or "{}") if analysis else {}
        trace = await repo.get_trace(session, analysis_id)
    run_summary = (trace or {}).get("run")

    scores = {
        "tool_usage": eval_tool_usage(case, result, trace),
        "correctness": eval_correctness(case, result, trace),
        "visualization": eval_visualization(case, result, trace),
    }
    if case.get("evaluate_report"):
        try:
            scores["report"] = await eval_report(case, result, trace, run_summary)
        except Exception as exc:  # noqa: BLE001
            scores["report"] = {"score": 0.0, "detail": f"report eval error: {exc}"}

    core = [scores["tool_usage"], scores["correctness"], scores["visualization"]]
    if case.get("expected_safe"):
        task_success = all(s["score"] >= _SCORE_THRESHOLD for s in core) and scores[
            "tool_usage"
        ].get("safe", False)
    else:
        task_success = all(s["score"] >= _SCORE_THRESHOLD for s in core)
    overall = sum(s["score"] for s in core) / len(core)

    return {
        "dataset": None,  # filled by run_all
        "case_id": case["id"],
        "question": case["question"],
        "status": analysis.status if analysis else "unknown",
        "scores": scores,
        "task_success": task_success,
        "overall": round(overall, 3),
        "latency_ms": (run_summary or {}).get("latency_ms") or 0,
        "cost": (run_summary or {}).get("cost") or 0.0,
    }


def _aggregate(results: list[dict]) -> dict[str, Any]:
    n = len(results)
    if n == 0:
        return {"metrics": {}, "cases": results}
    success = sum(1 for r in results if r["task_success"])
    tool_scores = [r["scores"]["tool_usage"]["score"] for r in results]
    corr_scores = [r["scores"]["correctness"]["score"] for r in results]
    viz_scores = [r["scores"]["visualization"]["score"] for r in results]
    report_scores = [r["scores"]["report"]["score"] for r in results if "report" in r["scores"]]
    lat = [r["latency_ms"] for r in results if r["latency_ms"]]
    cost = [r["cost"] for r in results if r["cost"]]

    metrics = {
        "total_cases": n,
        "task_success_rate": round(success / n, 3),
        "tool_success_rate": round(sum(tool_scores) / n, 3),
        "analysis_correctness": round(sum(corr_scores) / n, 3),
        "chart_correctness": round(sum(viz_scores) / n, 3),
        "report_quality": round(sum(report_scores) / len(report_scores), 3)
        if report_scores
        else None,
        "avg_latency_ms": round(sum(lat) / len(lat)) if lat else 0,
        "avg_cost": round(sum(cost) / len(cost), 6) if cost else 0.0,
    }
    return {"metrics": metrics, "cases": results}


async def run_all(
    datasets_dir: str | None = None,
    dataset_names: list[str] | None = None,
) -> dict[str, Any]:
    datasets_dir = datasets_dir or os.path.join(os.path.dirname(__file__), "datasets")
    datasets = _load_datasets(datasets_dir)
    if dataset_names:
        datasets = {k: v for k, v in datasets.items() if k in dataset_names}

    await ensure_tables()

    results: list[dict] = []
    for name, dataset in datasets.items():
        ds_id, table, storage_path, schema_text = _materialize(dataset)
        for case in dataset.get("cases", []):
            case = dict(case)
            case["_dataset_name"] = dataset["name"]
            rec = await run_case(dataset, case, ds_id, table, storage_path, schema_text)
            rec["dataset"] = name
            results.append(rec)
    return _aggregate(results)
