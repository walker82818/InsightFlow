"""Visualization evaluator: was a chart of the expected type generated, and
does it carry real data?"""
from __future__ import annotations

from typing import Any


def _same_field(xf: Any, target: str) -> bool:
    if xf == target:
        return True
    if isinstance(xf, list):
        return target in xf
    return False


def evaluate(case: dict, result: dict, trace: dict | None) -> dict[str, Any]:
    charts = result.get("visualizations") or []
    exp = case.get("expected_chart")
    if not exp:
        return {"score": 1.0, "detail": "no chart expectation", "matched": None}

    ctype = exp.get("type")
    xf = exp.get("xField")
    candidates = [c for c in charts if c.get("type") == ctype]
    match = None
    if xf:
        match = next((c for c in candidates if _same_field(c.get("xField"), xf)), None)
    if match is None:
        match = candidates[0] if candidates else None

    if match is None:
        return {
            "score": 0.0,
            "detail": f"expected {ctype} not found; got {[c.get('type') for c in charts]}",
            "matched": None,
        }

    data_ok = len(match.get("data") or []) > 0
    score = 1.0 if data_ok else 0.5
    return {
        "score": round(score, 3),
        "detail": f"matched {ctype} xField={match.get('xField')} rows={len(match.get('data') or [])}",
        "matched": ctype,
        "data_ok": data_ok,
    }
