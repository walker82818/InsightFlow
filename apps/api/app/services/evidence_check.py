"""Reviewer 2.0 rule channel (deterministic, no LLM).

Complements the LLM semantic channel. These checks run on the same material the
LLM sees, but are deterministic and reproducible:
  - check_evidence_sup   : at least one successful SQL/Python result exists.
  - check_numeric_claims : a "real" number from the conclusion appears in the
                           evidence results (spans per-row / aggregate values).
  - check_sql_reproduce  : every executed SQL returned without error.

Design decision: the rule channel is the *hard gate*. If any rule fails, the
reviewer must be marked failed (safe-fail), regardless of what the LLM says.
This prevents "confident but unsupported" conclusions from passing.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

# Numbers that are too generic to be meaningful evidence (deltas of rounding).
_TRIVIAL_NUMBERS = {0, 1, 2, 3, 5, 10, 100, 1000}


def _numbers_in_text(text: str) -> set[int]:
    """Extract plain-integer tokens from text (percent-style handled separately)."""
    out: set[int] = set()
    for m in re.finditer(r"\d[\d,]*", text):
        try:
            out.add(int(m.group(0).replace(",", "")))
        except ValueError:
            continue
    return out


def _numbers_in_evidence(evidence_rows: list[dict[str, Any]]) -> set[int]:
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


def _has_error(evidence_rows: list[dict[str, Any]]) -> bool:
    for row in evidence_rows:
        result = row.get("result")
        if isinstance(result, dict) and result.get("error"):
            return True
    return False


def check_numeric_claims(answer: str, evidence_rows: list[dict[str, Any]]) -> dict:
    claims = _numbers_in_text(answer)
    meaningful = claims - _TRIVIAL_NUMBERS
    if not meaningful:
        # No concrete number cited → cannot verify numerically; treat as weak
        # (not a hard failure, the LLM channel can still assess).
        return {
            "check": "numeric_claims",
            "passed": True,
            "detail": "结论未引用具体数字，跳过数值核对",
        }
    available = _numbers_in_evidence(evidence_rows)
    if not available:
        return {
            "check": "numeric_claims",
            "passed": False,
            "detail": f"结论引用了数字 {sorted(meaningful)}，但证据中没有可核对的行数据",
        }
    hits = meaningful & available
    if not hits:
        return {
            "check": "numeric_claims",
            "passed": False,
            "detail": f"结论中的数字 {sorted(meaningful)} 未在证据结果中找到对应值",
        }
    return {
        "check": "numeric_claims",
        "passed": True,
        "detail": f"结论中的数字 {sorted(hits)} 能在证据结果中找到对应值",
    }


def check_evidence_sup(evidence_rows: list[dict[str, Any]]) -> dict:
    n = len(evidence_rows)
    if n == 0:
        return {
            "check": "evidence_sup",
            "passed": False,
            "detail": "没有执行成功的 SQL/Python 查询，结论缺乏证据支撑",
        }
    return {
        "check": "evidence_sup",
        "passed": True,
        "detail": f"存在 {n} 条证据",
    }


def check_sql_reproduce(evidence_rows: list[dict[str, Any]]) -> dict:
    if _has_error(evidence_rows):
        return {
            "check": "sql_reproduce",
            "passed": False,
            "detail": "存在执行失败的查询，证据链不可靠",
        }
    return {
        "check": "sql_reproduce",
        "passed": True,
        "detail": "所有查询均执行成功",
    }


def check_semantic_alignment(
    evidence_rows: list[dict[str, Any]], semantic_metrics: list[str]
) -> dict:
    """Design §6.1 rule #4 — advisory: did the analysis stay within the semantic
    layer vocabulary (confirmed metric names/columns)?

    This is deliberately advisory ("提示", not a hard failure): a mismatch should
    prompt the user to add the metric to the semantic layer, but must not block a
    factually-supported conclusion.
    """
    if not semantic_metrics:
        return {
            "check": "semantic_alignment",
            "passed": True,
            "detail": "暂无已确认的语义口径，跳过对齐校验",
        }
    vocab = {str(m).strip().lower() for m in semantic_metrics if m}
    referenced: set[str] = set()
    for row in evidence_rows:
        m = row.get("metric")
        if m:
            referenced.add(str(m).strip().lower())
        sql = row.get("sql") or ""
        for m in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)", sql):
            referenced.add(m.lower())
    aligned = referenced & vocab
    if not aligned and referenced:
        return {
            "check": "semantic_alignment",
            "passed": False,
            "detail": (
                "结论引用的字段未出现在已确认的语义口径中"
                f"（已确认：{sorted(vocab)}），建议补充到语义层"
            ),
        }
    return {
        "check": "semantic_alignment",
        "passed": True,
        "detail": "引用口径与语义层对齐",
    }


def run_rule_checks(
    answer: str,
    sql_results: list[dict[str, Any]],
    python_results: list[dict[str, Any]],
    semantic_metrics: list[str] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Run the deterministic rule channel over the analysis results.

    Returns (checks, all_passed). ``all_passed`` is the hard gate for Reviewer 2.0.

    Design §6.1 四条规则：
      1. check_evidence_sup       （硬）
      2. check_numeric_claims     （硬）
      3. check_sql_reproduce      （硬）
      4. check_semantic_alignment （advisory「提示」——不阻断通过，只提示补充语义口径）
    """
    evidence_rows: list[dict[str, Any]] = []
    for r in sql_results:
        result = r.get("result")
        if isinstance(result, dict):
            evidence_rows.append(
                {"result": result, "sql": r.get("sql", ""), "metric": r.get("metric", "")}
            )
    for r in python_results:
        result = r.get("result")
        if isinstance(result, dict):
            evidence_rows.append({"result": result, "metric": r.get("metric", "")})

    # 硬规则（前三条）：
    checks: list[dict[str, Any]] = [
        check_evidence_sup(evidence_rows),
        check_numeric_claims(answer, evidence_rows),
        check_sql_reproduce(evidence_rows),
    ]
    all_passed = all(c["passed"] for c in checks)

    # 第 4 条：语义对齐 —— advisory，不进入硬闸门。
    align = check_semantic_alignment(evidence_rows, semantic_metrics or [])
    align["severity"] = "warning" if not align["passed"] else "info"
    checks.append(align)
    return checks, all_passed
