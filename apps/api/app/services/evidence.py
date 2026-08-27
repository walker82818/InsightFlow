"""Evidence persistence service (2.0 evidence-driven core).

Every analysis run persists its successful tool results as ``Evidence`` rows
so the conclusion is backed by an auditable chain (the deterministic material
that Reviewer 2.0's rule channel re-checks). Upload-time insights and semantic
profiles also write evidence rows with ``analysis_id IS NULL``.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import Evidence


def _result_payload(result: Any) -> str:
    try:
        return json.dumps(result, ensure_ascii=False, default=str)[:4000]
    except Exception:  # noqa: BLE001
        return "{}"


def _claim_from_result(result: Any) -> str:
    """Derive a short human claim from a tool result for the evidence chain."""
    if not isinstance(result, dict):
        return ""
    if "error" in result:
        return f"查询出错：{result['error']}"
    cols = result.get("columns")
    rows = result.get("rows")
    if isinstance(cols, list) and isinstance(rows, list):
        rc = result.get("row_count", len(rows))
        preview = (
            " | ".join(str(v) for v in rows[0]) if rows else ""
        )
        return f"查询返回 {rc} 行，列 {cols}" + (f"；首行 {preview}" if preview else "")
    return f"查询结果：{json.dumps(result, ensure_ascii=False)[:120]}"


async def persist_analysis_evidences(
    session: AsyncSession,
    *,
    analysis_id: str,
    dataset_id: str,
    sql_results: list[dict[str, Any]],
    python_results: list[dict[str, Any]],
) -> int:
    """Persist one Evidence row per successful tool result for an analysis.

    Replaces any previous evidence rows for this analysis (re-run is idempotent).
    Returns the number of evidence rows written.
    """
    await session.execute(
        delete(Evidence).where(Evidence.analysis_id == analysis_id)
    )

    added = 0
    for r in sql_results:
        sql = str(r.get("sql") or "")
        result = r.get("result")
        if not isinstance(result, dict) or "error" in result:
            continue
        session.add(
            Evidence(
                dataset_id=dataset_id,
                analysis_id=analysis_id,
                claim=_claim_from_result(result),
                source="sql",
                sql=sql,
                result=_result_payload(result),
                confidence=0.9,
            )
        )
        added += 1

    for r in python_results:
        result = r.get("result")
        if not isinstance(result, dict) or result.get("error"):
            continue
        session.add(
            Evidence(
                dataset_id=dataset_id,
                analysis_id=analysis_id,
                claim=_claim_from_result(result),
                source="python",
                result=_result_payload(result),
                confidence=0.8,
            )
        )
        added += 1

    await session.commit()
    return added


async def _find_supporting_evidence(
    session: AsyncSession,
    *,
    analysis_id: str,
    factor: str,
) -> str | None:
    """Return the id of the first raw evidence row whose result cells contain the
    factor value — used to build the P1 evidence-graph parent chain
    (root-cause factor → supporting SQL/python data)."""
    rows = (await session.execute(select(Evidence).where(Evidence.analysis_id == analysis_id))).scalars().all()
    needle = str(factor).strip()
    # 1) Prefer an exact cell match (dimension value appears in a query result).
    if needle:
        for e in rows:
            try:
                result = json.loads(e.result or "{}")
            except Exception:  # noqa: BLE001
                continue
            for row in result.get("rows", []):
                for cell in row:
                    if str(cell).strip() == needle:
                        return e.id
    # 2) Fall back to the first raw (sql/python) evidence of the analysis — the
    # aggregate that the root cause explains, so the factor still traces to data.
    for e in rows:
        if e.parent_id is None and e.source in ("sql", "python"):
            return e.id
    return None


async def persist_factor_evidences(
    session: AsyncSession,
    *,
    analysis_id: str,
    dataset_id: str,
    contributions: list[dict[str, Any]],
) -> int:
    """Write one *derived* evidence row per root-cause factor (source=llm_reasoning),
    linked via ``parent_id`` to the raw evidence that supports it. Enables the
    multi-hop traceability of the P1 evidence graph (conclusion → data).
    """
    added = 0
    for c in contributions:
        factor = str(c.get("factor") or "")
        if not factor:
            continue
        parent = await _find_supporting_evidence(
            session, analysis_id=analysis_id, factor=factor
        )
        session.add(
            Evidence(
                dataset_id=dataset_id,
                analysis_id=analysis_id,
                parent_id=parent,
                claim=(
                    f"根因因素「{factor}」贡献 "
                    f"{c.get('contribution_pct', 0) * 100:.1f}%"
                ),
                source="llm_reasoning",
                metric=c.get("metric") or "",
                result=_result_payload({"factor": factor, "pct": c.get("contribution_pct", 0)}),
                confidence=0.7,
            )
        )
        added += 1
    if added:
        await session.commit()
    return added


async def load_evidence_graph(
    session: AsyncSession,
    *,
    analysis_id: str,
) -> dict[str, Any]:
    """Build the P1 evidence graph (multi-hop DAG) for an analysis.

    Returns ``{"nodes": [...], "edges": [{from, to}]}``. A node is either a raw
    tool result (root of the graph, parent_id is None) or a derived node
    (e.g. root-cause factor) whose ``parent_id`` points to the evidence that
    supports it. ``level`` = distance from a root (0 = raw data).
    """
    stmt = select(Evidence).where(Evidence.analysis_id == analysis_id)
    rows = (await session.execute(stmt)).scalars().all()

    node_map: dict[str, dict[str, Any]] = {}
    for e in rows:
        try:
            result = json.loads(e.result or "{}")
        except Exception:  # noqa: BLE001
            result = {}
        node_map[e.id] = {
            "id": e.id,
            "claim": e.claim,
            "metric": e.metric,
            "source": e.source,
            "sql": e.sql,
            "confidence": e.confidence,
            "parent_id": e.parent_id,
            "result": result,
        }

    # Compute levels by walking parents (raw nodes are level 0).
    def _level(nid: str, seen: set[str]) -> int:
        if nid in seen:
            return 0
        seen.add(nid)
        parent = node_map[nid]["parent_id"]
        if not parent or parent not in node_map:
            return 0
        return _level(parent, seen) + 1

    nodes = []
    for nid, n in node_map.items():
        n["level"] = _level(nid, set())
        nodes.append(n)
    nodes.sort(key=lambda n: (n["level"], n["id"]))

    edges = [
        {"from": n["parent_id"], "to": n["id"]}
        for n in node_map.values()
        if n["parent_id"] and n["parent_id"] in node_map
    ]
    return {"nodes": nodes, "edges": edges}


async def load_evidences(
    session: AsyncSession,
    *,
    analysis_id: str | None = None,
    dataset_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load evidence rows, optionally filtered by analysis and/or dataset."""
    stmt = select(Evidence)
    if analysis_id is not None:
        stmt = stmt.where(Evidence.analysis_id == analysis_id)
    elif dataset_id is not None:
        stmt = stmt.where(Evidence.dataset_id == dataset_id)
    rows = (await session.execute(stmt.order_by(Evidence.created_at))).scalars().all()
    out = []
    for e in rows:
        try:
            result = json.loads(e.result or "{}")
        except Exception:  # noqa: BLE001
            result = {}
        out.append(
            {
                "id": e.id,
                "dataset_id": e.dataset_id,
                "analysis_id": e.analysis_id,
                "parent_id": e.parent_id,
                "claim": e.claim,
                "metric": e.metric,
                "dimensions": json.loads(e.dimensions or "[]"),
                "source": e.source,
                "sql": e.sql,
                "result": result,
                "confidence": e.confidence,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
        )
    return out
