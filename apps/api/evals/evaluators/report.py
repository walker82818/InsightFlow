"""Report-quality evaluator (optional, async).

Generates a report from the analysis result and checks that it is non-empty,
has findings, and is *grounded* in the real SQL evidence (the report's evidence
SQLs reference queries that were actually executed).
"""
from __future__ import annotations

from typing import Any


async def evaluate(
    case: dict,
    result: dict,
    trace: dict | None,
    run_summary: dict | None = None,
) -> dict[str, Any]:
    from app.services.report import generate_report

    report = await generate_report(
        result,
        dataset_name=case.get("_dataset_name", "eval"),
        query=case.get("question", ""),
        run_summary=run_summary,
    )

    ok_summary = bool((report.get("executive_summary") or "").strip())
    ok_findings = len(report.get("key_findings") or []) > 0

    sql_set = {
        (r.get("sql") or "").strip().lower()
        for r in (result.get("sql_results") or [])
        if (r.get("sql") or "").strip()
    }
    ev_sqls = [
        (e.get("sql") or "").strip().lower() for e in (report.get("evidence") or [])
    ]
    grounded = True
    if sql_set:
        grounded = any(any(s and s in ev for s in sql_set) for ev in ev_sqls)

    score = (
        (0.4 if ok_summary else 0.0)
        + (0.3 if ok_findings else 0.0)
        + (0.3 if grounded else 0.0)
    )
    return {
        "score": round(score, 3),
        "detail": f"summary={ok_summary} findings={ok_findings} grounded={grounded}",
        "grounded": grounded,
    }
