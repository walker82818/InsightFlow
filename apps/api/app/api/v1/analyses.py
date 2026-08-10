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

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import DatasetRef, run_analysis
from app.core.config import settings
from app.db.session import AsyncSessionLocal, get_session
from app.models.analysis import Analysis as AnalysisModel
from app.models.dataset import Dataset, DatasetColumn
from app.repositories import analysis as repo
from app.schemas.analysis import AnalysisCreate, AnalysisOut, AnalysisSummaryOut
from app.services.duckdb import table_name

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
) -> AnalysisOut:
    ds = await session.get(Dataset, payload.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    row = await repo.create_analysis(
        session,
        user_id=settings.default_user_id,
        dataset_id=payload.dataset_id,
        query=payload.query,
    )
    return AnalysisOut(**repo.to_detail(row))


@router.get("", response_model=list[AnalysisSummaryOut])
async def list_analyses(
    session: AsyncSession = Depends(get_session),
) -> list[AnalysisSummaryOut]:
    rows = await repo.list_analyses(session, settings.default_user_id)
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
    ds = await session.get(Dataset, row.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")

    cols = (
        await session.execute(
            select(DatasetColumn)
            .where(DatasetColumn.dataset_id == row.dataset_id)
            .order_by(DatasetColumn.position)
        )
    ).scalars().all()

    ref = DatasetRef(
        id=ds.id,
        name=ds.name,
        storage_path=ds.storage_path,
        file_type=ds.file_type,
        table_name=table_name(ds.id),
        schema_text=_schema_text(list(cols)),
    )

    await repo.set_running(session, row)
    query_text = row.query

    async def event_gen() -> AsyncGenerator[str, None]:
        async with AsyncSessionLocal() as s:
            arow = await s.get(AnalysisModel, analysis_id)
            try:
                async for ev in run_analysis(ref, query_text):
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    if ev["type"] == "agent_end":
                        await repo.finish_analysis(
                            s,
                            arow,
                            status="completed",
                            answer=ev["result"]["answer"],
                            result=ev["result"],
                            prompt_tokens=ev["result"]["prompt_tokens"],
                            completion_tokens=ev["result"]["completion_tokens"],
                        )
                    elif ev["type"] == "error":
                        await repo.finish_analysis(
                            s,
                            arow,
                            status="error",
                            result={"error": ev["message"]},
                        )
            except Exception as exc:  # noqa: BLE001
                await repo.finish_analysis(
                    s, arow, status="error", result={"error": str(exc)}
                )
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
