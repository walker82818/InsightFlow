"""Evaluation 2.0 — evidence-based replay evaluation (Design §11.3).

Independent of the Phase 8 golden-dataset harness (``evals.runner``). For any
*historical completed* analysis, this replays the deterministic evidence checks
over the ``evidences`` table (confidence + data rows), asserts whether each
conclusion is backed by evidence, and produces a structured report.

Key differences vs. the live Reviewer 2.0:
  - Runs post-hoc over persisted ``evidences``, not inside the agent graph.
  - Adds a **confidence gate** (evidence rows below threshold are flagged).
  - Adds **per-conclusion coverage**: the answer is split into claim sentences;
    each numeric claim must be findable in some evidence's result rows.
  - Does NOT call the LLM and does NOT touch ``evals/`` / ``evaluations.py``.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis
from app.models.evidence import Evidence
from app.services.evidence_check import (
    check_evidence_sup,
    check_numeric_claims,
    check_sql_reproduce,
)

# Confidence threshold: any evidence below this is "low-confidence".
DEFAULT_MIN_CONFIDENCE = 0.6
# Coverage threshold: ratio of numeric conclusion sentences backed by evidence.
DEFAULT_MIN_COVERAGE = 0.5


def _load_evidence_rows(evidences: list[Evidence]) -> list[dict[str, Any]]:
    """Normalise Evidence rows into the same shape ``evidence_check`` expects."""
    rows: list[dict[str, Any]] = []
    for e in evidences:
        try:
            result = json.loads(e.result or "{}")
        except (TypeError, ValueError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        rows.append(
            {
                "result": result,
                "sql": e.sql or "",
                "metric": e.metric or "",
                "source": e.source or "sql",
                "confidence": e.confidence or 0.0,
                "claim": e.claim or "",
            }
        )
    return rows


def _split_claim_sentences(answer: str) -> list[str]:
    """Split the answer into per-claim sentences on Chinese/English punctuation."""
    answer = (answer or "").strip()
    if not answer:
        return []
    parts = re.split(r"[。！？!?；;\n]+", answer)
    return [p.strip() for p in parts if p.strip()]


def _sentence_numbers(text: str) -> set[int]:
    from app.services.evidence_check import _TRIVIAL_NUMBERS, _numbers_in_text

    return _numbers_in_text(text) - _TRIVIAL_NUMBERS


def _evidence_numbers(evidence_rows: list[dict[str, Any]]) -> set[int]:
    """All integer cell values across all evidence result rows."""
    out: set[int] = set()
    for row in evidence_rows:
        result = row.get("result") or {}
        for v in result.get("rows", []):
            for cell in v:
                try:
                    f = float(cell)
                except (TypeError, ValueError):
                    continue
                if f == int(f) and abs(f) < 1e9:
                    out.add(int(f))
    return out


def _coverage_assert(answer: str, evidence_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-conclusion coverage: each numeric claim sentence must be backed by a
    number that exists in some evidence's result rows."""
    sentences = _split_claim_sentences(answer)
    evidence_nums = _evidence_numbers(evidence_rows)
    claims: list[dict[str, Any]] = []
    numeric_count = 0
    backed = 0
    for s in sentences:
        nums = _sentence_numbers(s)
        if not nums:
            claims.append(
                {"sentence": s[:120], "claim_numbers": [], "backed": None, "note": "无数字断言，跳过"}
            )
            continue
        numeric_count += 1
        found = sorted(nums & evidence_nums)
        ok = bool(found)
        backed += 1 if ok else 0
        claims.append(
            {
                "sentence": s[:120],
                "claim_numbers": sorted(nums),
                "backed": ok,
                "matched_numbers": found,
            }
        )
    coverage = round(backed / numeric_count, 3) if numeric_count else 1.0
    return {"claims": claims, "numeric_claims": numeric_count, "backed": backed, "coverage": coverage}


def _confidence_assert(evidence_rows: list[dict[str, Any]], min_conf: float) -> dict[str, Any]:
    """Confidence gate: flag evidence rows below ``min_conf``."""
    low = [
        {"source": r["source"], "confidence": r["confidence"], "claim": (r["claim"] or "")[:120]}
        for r in evidence_rows
        if (r.get("confidence") or 0.0) < min_conf
    ]
    return {
        "min_confidence": min_conf,
        "low_confidence_count": len(low),
        "low_confidence": low[:20],
        "passed": len(low) == 0,
    }


async def evaluate_analysis(
    session: AsyncSession,
    analysis_id: str,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> dict[str, Any]:
    """Evaluate one historical analysis against its persisted evidence chain.

    Returns a structured report (no LLM, deterministic and reproducible).
    """
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        return {"error": "analysis not found", "analysis_id": analysis_id}

    result_json = json.loads(analysis.result_json or "{}") if analysis.result_json else {}
    answer = result_json.get("answer") or analysis.answer or ""

    evidences = (
        (await session.execute(select(Evidence).where(Evidence.analysis_id == analysis_id)))
        .scalars()
        .all()
    )
    evidence_rows = _load_evidence_rows(evidences)

    # 1) Replay the three hard rules over persisted evidence rows.
    checks = [
        check_evidence_sup(evidence_rows),
        check_numeric_claims(answer, evidence_rows),
        check_sql_reproduce(evidence_rows),
    ]
    rules_passed = all(c["passed"] for c in checks)

    # 2) Confidence gate.
    conf = _confidence_assert(evidence_rows, min_confidence)

    # 3) Per-conclusion coverage.
    cov = _coverage_assert(answer, evidence_rows)

    # Verdict: all hard rules pass AND confidence gate pass AND coverage meets bar.
    coverage_ok = cov["coverage"] >= min_coverage
    if not rules_passed:
        verdict = "fail"
    elif not conf["passed"] or not coverage_ok:
        verdict = "warn"
    else:
        verdict = "pass"

    return {
        "analysis_id": analysis_id,
        "query": analysis.query,
        "status": analysis.status,
        "evidence_count": len(evidence_rows),
        "answer": answer[:500],
        "checks": checks,
        "rules_passed": rules_passed,
        "confidence_gate": conf,
        "coverage": cov,
        "verdict": verdict,
        "min_coverage": min_coverage,
    }


async def list_replayable(
    session: AsyncSession,
    *,
    limit: int = 50,
    only_with_evidence: bool = True,
) -> list[dict[str, Any]]:
    """List completed analyses that can be replayed, newest first."""
    stmt = (
        select(Analysis)
        .where(Analysis.status == "completed")
        .order_by(Analysis.created_at.desc())
        .limit(limit)
    )
    analyses = (await session.execute(stmt)).scalars().all()
    out: list[dict[str, Any]] = []
    for a in analyses:
        ev_count = (
            await session.execute(
                select(Evidence.id).where(Evidence.analysis_id == a.id).limit(1)
            )
        ).scalar_one_or_none()
        has_evidence = ev_count is not None
        if only_with_evidence and not has_evidence:
            continue
        out.append(
            {
                "analysis_id": a.id,
                "query": a.query,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "has_evidence": has_evidence,
            }
        )
    return out
