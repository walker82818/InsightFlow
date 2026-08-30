"""Analysis API (Phase 2).

Endpoints:
    POST   /api/v1/analyses            create an analysis task
    GET    /api/v1/analyses            list (current user)
    GET    /api/v1/analyses/{id}       detail (status + answer + steps)
    DELETE /api/v1/analyses/{id}       delete
    POST   /api/v1/analyses/{id}/run   run the agent, streamed via SSE
                                        (also persists the final result)
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import DatasetRef, run_analysis
from app.api.v1.deps import get_current_user
from app.db.session import get_session
from app.models.analysis import Analysis
from app.models.dataset import Dataset, DatasetColumn
from app.models.user import User
from app.repositories import analysis as repo
from app.repositories import report as report_repo
from app.schemas.analysis import AnalysisCreate, AnalysisOut, AnalysisSummaryOut
from app.schemas.artifact import (
    ArtifactRepairRequest,
    ArtifactRepairResponse,
    ArtifactSpec,
)
from app.schemas.report import ReportOut
from app.services.duckdb import table_name
from app.services.report import generate_report, render_html_report

router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])


def _schema_text(columns: list[DatasetColumn]) -> str:
    lines: list[str] = []
    for c in columns:
        try:
            stats = json.loads(c.stats_json) if c.stats_json else {}
        except json.JSONDecodeError:
            stats = {}
        bits = [f"{c.dtype}"]
        if "missing" in stats:
            bits.append(f"缺失={stats['missing']}")
        if "distinct" in stats:
            bits.append(f"唯一={stats['distinct']}")
        if "min" in stats:
            bits.append(f"min={stats['min']}")
        if "max" in stats:
            bits.append(f"max={stats['max']}")
        lines.append(f"- {c.name} ({', '.join(bits)})")
    return "\n".join(lines)


@router.post("", response_model=AnalysisOut, status_code=201)
async def create_analysis(
    payload: AnalysisCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AnalysisOut:
    ids = payload.dataset_ids or ([payload.dataset_id] if payload.dataset_id else [])
    if not ids:
        raise HTTPException(status_code=422, detail="at least one dataset id is required")
    for did in ids:
        ds = await session.get(Dataset, did)
        if ds is None:
            raise HTTPException(status_code=404, detail=f"dataset not found: {did}")
    row = await repo.create_analysis(
        session,
        user_id=user.id,
        dataset_ids=ids,
        query=payload.query,
    )
    return AnalysisOut(**repo.to_detail(row))


@router.get("", response_model=list[AnalysisSummaryOut])
async def list_analyses(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    dataset_id: str | None = Query(default=None, description="按数据集过滤"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AnalysisSummaryOut]:
    rows = await repo.list_analyses(
        session, user.id, limit=limit, dataset_id=dataset_id
    )
    return [AnalysisSummaryOut(**repo.to_summary(r)) for r in rows]


@router.get("/{analysis_id}", response_model=AnalysisOut)
async def get_analysis(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> AnalysisOut:
    row = await repo.get_analysis(session, analysis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return AnalysisOut(**repo.to_detail(row))


@router.delete("/{analysis_id}", status_code=204)
async def delete_analysis(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    row = await repo.get_analysis(session, analysis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    await session.delete(row)
    await session.commit()


@router.post("/{analysis_id}/run")
async def run_analysis_stream(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Run the single-agent analysis and stream events as SSE.

    Emits AgentEvent dicts (design §10.4). The final ``agent_end`` (and any
    ``error``) is persisted to the analysis row.
    """
    row = await repo.get_analysis(session, analysis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    ids = json.loads(row.dataset_ids) if row.dataset_ids else [row.dataset_id]
    refs: list[DatasetRef] = []
    for did in ids:
        ds = await session.get(Dataset, did)
        if ds is None:
            raise HTTPException(status_code=404, detail=f"dataset not found: {did}")
        cols = (
            await session.execute(
                select(DatasetColumn)
                .where(DatasetColumn.dataset_id == did)
                .order_by(DatasetColumn.position)
            )
        ).scalars().all()
        refs.append(
            DatasetRef(
                id=ds.id,
                name=ds.name,
                storage_path=ds.storage_path,
                file_type=ds.file_type,
                table_name=table_name(did),
                schema_text=_schema_text(list(cols)),
            )
        )

    # 并发拦截：已有 run 在进行中则拒绝，避免重复触发 agent。
    # 「置 running 态」的职责已统一移交 run_analysis（含崩溃恢复），此处不再 set_running。
    if row.status == "running":
        raise HTTPException(status_code=409, detail="analysis is already running")
    query_text = row.query

    async def event_gen() -> AsyncGenerator[str, None]:
        try:
            async for ev in run_analysis(refs, query_text, analysis_id):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            # Disable proxy / framework level buffering so events flush immediately.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{analysis_id}/trace")
async def get_analysis_trace(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the structured Agent execution trace for an analysis (Phase 6)."""
    trace = await repo.get_trace(session, analysis_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found (run the analysis first)")
    return trace


@router.get("/{analysis_id}/evidences")
async def get_analysis_evidences(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the persisted evidence chain for an analysis (2.0 evidence core)."""
    from app.services.evidence import load_evidences

    evidences = await load_evidences(session, analysis_id=analysis_id)
    return {"analysis_id": analysis_id, "evidences": evidences}


@router.get("/{analysis_id}/evidence-graph")
async def get_analysis_evidence_graph(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the multi-hop evidence DAG for an analysis (P1 evidence graph)."""
    from app.services.evidence import load_evidence_graph

    graph = await load_evidence_graph(session, analysis_id=analysis_id)
    return {"analysis_id": analysis_id, **graph}


@router.get("/{analysis_id}/root-cause")
async def get_analysis_root_cause(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the persisted root-cause analysis for an analysis, if any."""
    from sqlalchemy import select as _select
    from app.models.root_cause import RootCause

    row = (
        await session.execute(
            _select(RootCause).where(RootCause.analysis_id == analysis_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return {"analysis_id": analysis_id, "root_cause": None}
    return {
        "analysis_id": analysis_id,
        "root_cause": {
            "id": row.id,
            "dataset_id": row.dataset_id,
            "question": row.question,
            "change": json.loads(row.change or "{}"),
            "contributions": json.loads(row.contributions or "[]"),
            "factors": json.loads(row.factors or "[]"),
            "hypotheses": json.loads(row.hypotheses or "[]"),
            "conclusion": row.conclusion,
            "confidence": row.confidence,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    }


@router.post("/{analysis_id}/artifact-repair", response_model=ArtifactRepairResponse)
async def repair_analysis_artifact(
    analysis_id: str,
    payload: ArtifactRepairRequest,
) -> ArtifactRepairResponse:
    """Agent2UI 自愈：根据 iframe 渲染报错修复 ArtifactSpec。

    前端在收到 iframe 的 ``error`` 事件后调用（最多 3 轮，attempt 由前端计数）。
    服务端加载该次分析的上下文（query / 字段 / 数据集），连同上次代码与报错
    一起交给 LLM 修复，返回新的 ArtifactSpec。
    """
    from app.services.artifact_repair import repair_artifact as _repair

    outcome = await _repair(
        analysis_id,
        payload.spec.model_dump(mode="json"),
        payload.error.model_dump(),
    )
    if not outcome.get("repaired"):
        return ArtifactRepairResponse(
            repaired=False, spec=None, reason=outcome.get("reason")
        )
    return ArtifactRepairResponse(
        repaired=True, spec=ArtifactSpec(**outcome["spec"]), reason=None
    )


# ---------------------------------------------------------------------------
# Phase 7: report generation / export
# ---------------------------------------------------------------------------

@router.post("/{analysis_id}/report", response_model=ReportOut)
async def create_report(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> ReportOut:
    """Generate (or regenerate) a structured report for an analysis and persist it."""
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    # 仅在分析完成后生成报告；running 时结论尚不完整，生成弱报告无意义。
    if analysis.status == "running":
        raise HTTPException(
            status_code=409,
            detail="analysis is still running; wait for it to finish before generating a report",
        )
    if not (analysis.result_json or "").strip():
        raise HTTPException(
            status_code=409,
            detail=f"analysis is not ready (status={analysis.status}); run it first",
        )

    ids = json.loads(analysis.dataset_ids) if analysis.dataset_ids else [analysis.dataset_id]
    names: list[str] = []
    for did in ids:
        d = await session.get(Dataset, did)
        if d:
            names.append(d.name)
    dataset_name = "、".join(names)
    try:
        result = json.loads(analysis.result_json or "{}")
    except json.JSONDecodeError:
        result = {}

    trace = await repo.get_trace(session, analysis_id)
    run_summary = trace.get("run") if trace else None
    # trace 缺失兜底：用 analysis 行的 token 估算成本，保证 metrics 字段始终完整。
    if run_summary is None:
        pt = analysis.prompt_tokens or 0
        ct = analysis.completion_tokens or 0
        run_summary = {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "cost": round(
                (pt / 1000) * settings.trace_cost_per_1k_prompt
                + (ct / 1000) * settings.trace_cost_per_1k_completion,
                6,
            ),
            "latency_ms": None,
            "tool_calls": None,
        }

    report = await generate_report(
        result,
        dataset_name=dataset_name,
        query=analysis.query,
        run_summary=run_summary,
        analysis_prompt_tokens=analysis.prompt_tokens,
        analysis_completion_tokens=analysis.completion_tokens,
    )
    html = render_html_report(report, dataset_name, analysis.query)

    saved = await report_repo.save_report(
        session,
        analysis_id=analysis_id,
        content=report,
        html=html,
        prompt_tokens=report["metrics"]["prompt_tokens"],
        completion_tokens=report["metrics"]["completion_tokens"],
    )
    return ReportOut(**saved.to_dict())


@router.get("/{analysis_id}/report", response_model=ReportOut)
async def get_report(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> ReportOut:
    """Return the persisted report for an analysis (404 if not generated yet)."""
    report = await report_repo.get_report(session, analysis_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found (generate it first)")
    return ReportOut(**report.to_dict())


@router.get("/{analysis_id}/report/export")
async def export_report(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
    format: str = Query("html", description="导出格式：html | markdown"),
    inline: bool = Query(False, description="true 在浏览器内联打开，否则作为附件下载"),
):
    """Export the report as a standalone deliverable.

    Formats:
      - ``html``     : self-contained HTML (open in browser / print to PDF).
      - ``markdown`` : portable Markdown for Notion / Word / Obsidian.
    """
    from fastapi.responses import PlainTextResponse

    from app.services.eval_replay import evaluate_analysis
    from app.services.evidence import load_evidence_graph, load_evidences
    from app.services.report_export import (
        build_export_data,
        render_html_export,
        render_markdown_export,
    )

    report = await report_repo.get_report(session, analysis_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found (generate it first)")

    # report.content_json may be None/legacy; normalize to dict.
    content = report.content_json if isinstance(report.content_json, dict) else {}

    if format == "markdown":
        data = await build_export_data(session, analysis_id, content)
        md = render_markdown_export(data)
        disposition = "inline" if inline else "attachment"
        filename = f"report_{analysis_id}.md"
        return PlainTextResponse(
            content=md,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
        )

    # Default: html (standalone, print-ready, evidence-driven).
    html_doc = report.html
    try:
        data = await build_export_data(session, analysis_id, content)
        html_doc = render_html_export(data)
    except Exception:  # noqa: BLE001 - fall back to the stored HTML on any error
        if not html_doc:
            html_doc = render_html_report(content, "", analysis_id)

    disposition = "inline" if inline else "attachment"
    filename = f"report_{analysis_id}.html"
    return HTMLResponse(
        content=html_doc,
        media_type="text/html",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
