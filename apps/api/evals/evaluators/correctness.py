"""Correctness evaluator: does the final answer reference the expected facts
and did the SQL return enough rows?"""
from __future__ import annotations

from typing import Any


def _max_rows(result: dict) -> int:
    mx = 0
    for r in (result.get("sql_results") or []):
        res = r.get("result") or {}
        rc = res.get("row_count")
        if rc is None:
            rc = len(res.get("rows") or [])
        if isinstance(rc, int):
            mx = max(mx, rc)
    return mx


def evaluate(case: dict, result: dict, trace: dict | None) -> dict[str, Any]:
    answer = (result.get("answer") or "").lower()
    substrings = case.get("expected_answer_substrings") or []
    if substrings:
        hit = sum(1 for s in substrings if s.lower() in answer)
        ans_cov = hit / len(substrings)
    else:
        ans_cov = 1.0 if answer.strip() else 0.0

    max_rows = _max_rows(result)
    min_rows = case.get("expected_min_rows", 0) or 0
    rows_ok = (max_rows >= min_rows) if min_rows else True

    score = ans_cov * 0.7 + (1.0 if rows_ok else 0.0) * 0.3
    detail = (
        f"answer {hit if substrings else '-'}/{len(substrings) if substrings else '-'}; "
        f"max_rows={max_rows} need>={min_rows} ok={rows_ok}"
    )
    return {
        "score": round(score, 3),
        "detail": detail,
        "answer_coverage": round(ans_cov, 3),
        "rows_ok": rows_ok,
        "max_rows": max_rows,
    }
