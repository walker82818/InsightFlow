"""Analysis orchestration: drives the LangGraph ``GRAPH`` and streams SSE events.

Phase 6: every run also persists a structured :class:`AgentRun` trace
(steps + tool calls + tokens + latency + cost) so the frontend can render a
full Agent execution timeline via ``GET /api/v1/analyses/{id}/trace``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, TypedDict
from uuid import uuid4

from sqlalchemy import func, select

from app.agent.graph import build_graph
from app.agent import nodes
from app.core.config import settings

logger = logging.getLogger(__name__)

# Sentinel pushed onto the live stream queue to mark graph completion.
_STREAM_SENTINEL = object()

# Compiled graph instance (Phase 3 topology: planner→analysis→visualization→reviewer).
GRAPH = build_graph()
from app.db.session import AsyncSessionLocal
from app.models.analysis import Analysis
from app.models.trace import AgentRun, AgentStep, ToolCall


class DatasetRef(TypedDict):
    """Reference to a dataset, passed from the API to the agent runner."""

    id: str
    name: str
    storage_path: str
    file_type: str
    table_name: str
    schema_text: str

# Mapping node -> Chinese label (for SSE agent_activity frames)
_ACTIVITY_STATUS = {
    "planner": "规划中",
    "analysis": "分析中",
    "visualization": "可视化中",
    "reviewer": "审查中",
}


def _build_trace(events: list[dict]) -> tuple[list[dict], list[dict]]:
    """Turn fine-grained SSE events into (steps, tool_calls) trace records."""
    steps: list[dict] = []
    tool_calls: list[dict] = []
    stack: list[dict] = []
    order = 0

    times = [e.get("ts", 0) for e in events if isinstance(e.get("ts"), (int, float))]
    base = min(times) if times else 0

    for e in events:
        order += 1
        ts = (e.get("ts", 0) or 0) - base
        t = e.get("type")
        if t == "agent_activity":
            steps.append(
                dict(
                    agent=e.get("agent", "system"),
                    step_type="agent",
                    content=e.get("content"),
                    ts_ms=ts,
                    order_idx=order,
                    status="ok",
                )
            )
        elif t == "message":
            steps.append(
                dict(
                    agent="analysis",
                    step_type="message",
                    content=(e.get("content") or "")[:800],
                    ts_ms=ts,
                    order_idx=order,
                    status="ok",
                )
            )
        elif t == "chart":
            spec = e.get("spec") or {}
            steps.append(
                dict(
                    agent="visualization",
                    step_type="chart",
                    content=f"{spec.get('title', '')} [{spec.get('type')}]",
                    input={"renderer": spec.get("renderer"), "type": spec.get("type")},
                    ts_ms=ts,
                    order_idx=order,
                    status="ok",
                )
            )
        elif t == "tool_start":
            stack.append({"tool": e.get("tool"), "input": e.get("input"), "start": ts})
        elif t == "tool_end":
            started = stack.pop() if stack else None
            dur = ts - started["start"] if started else 0
            out = e.get("result")
            tool = (started or {}).get("tool") or e.get("tool")
            status = "error" if isinstance(out, dict) and out.get("error") else "success"
            tc = dict(
                tool=tool,
                input=(started or {}).get("input"),
                output=out,
                status=status,
                duration_ms=max(0, int(dur)),
                ts_ms=ts,
            )
            tool_calls.append(tc)
            steps.append(
                dict(
                    agent="analysis",
                    step_type="tool",
                    content=f"{tool} 工具调用",
                    input=(started or {}).get("input"),
                    output=out,
                    status=status,
                    duration_ms=tc["duration_ms"],
                    ts_ms=ts,
                    order_idx=order,
                )
            )
        elif t == "error":
            steps.append(
                dict(
                    agent="system",
                    step_type="error",
                    content=e.get("message"),
                    ts_ms=ts,
                    order_idx=order,
                    status="error",
                )
            )
    return steps, tool_calls


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        (prompt_tokens / 1000) * settings.trace_cost_per_1k_prompt
        + (completion_tokens / 1000) * settings.trace_cost_per_1k_completion,
        6,
    )


async def run_analysis(
    refs, query: str, analysis_id: str
) -> AsyncGenerator[dict[str, Any], None]:
    """Run an analysis over one or more datasets and yield SSE frames.

    ``refs`` accepts a single :data:`DatasetRef` dict (backward compatible) or a
    list of them. This powers multi-document analysis where the agent may JOIN
    across the registered dataset tables.

    ``analysis_id`` links the persisted :class:`AgentRun` trace to the analysis
    row and is used to store the final result.
    """
    if isinstance(refs, dict):
        refs = [refs]
    if not refs:
        raise ValueError("run_analysis requires at least one DatasetRef")

    datasets = [
        {
            "id": r["id"],
            "name": r["name"],
            "storage_path": r["storage_path"],
            "file_type": r["file_type"],
            "table_name": r["table_name"],
            "schema_text": r["schema_text"],
        }
        for r in refs
    ]
    schema_text = "\n\n".join(r["schema_text"] for r in refs)

    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    input_state = {
        "user_query": query,
        "datasets": datasets,
        "schema_text": schema_text,
    }

    # Create the run row up-front (status=running) so /trace is queryable early.
    # 同时负责「置运行态」的统一职责 + 崩溃恢复：
    # - 把本 analysis 任何遗留 status="running" 的 AgentRun 标为 error（interrupted），
    #   避免进程崩溃后 run 永久挂起。
    # - 把 Analysis.status 置为 running（路由层不再重复 set_running）。
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        stale = (
            await db.execute(
                select(AgentRun).where(
                    AgentRun.analysis_id == analysis_id, AgentRun.status == "running"
                )
            )
        ).scalars().all()
        for r in stale:
            r.status = "error"
            r.finished_at = now

        analysis = await db.get(Analysis, analysis_id)
        if analysis is not None:
            analysis.status = "running"

        run = AgentRun(analysis_id=analysis_id, thread_id=thread_id, status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    started = datetime.utcnow()
    final: Any = None
    try:
        # Live streaming: nodes push every event onto this queue via _ev(), so we
        # can yield events to the SSE client as soon as they are produced instead
        # of buffering the whole graph run and dumping everything at the end.
        queue: asyncio.Queue = asyncio.Queue()
        stream_token = nodes._STREAM_QUEUE.set(queue)

        async def _run_graph() -> None:
            async def _consume_stream() -> None:
                async for _ in GRAPH.astream(input_state, config=config):
                    pass

            try:
                # ⑤ 全局墙钟超时：兜底 LLM 慢/工具死循环导致 SSE 无限挂起。
                # 超时后取消 graph 任务并抛出 TimeoutError（被外层 except 捕获为 error）。
                await asyncio.wait_for(
                    _consume_stream(), timeout=settings.agent_total_timeout
                )
            except asyncio.TimeoutError:
                queue.put_nowait(
                    nodes._ev(
                        "error",
                        message=f"分析超时（超过 {settings.agent_total_timeout}s），已终止",
                    )
                )
                raise
            finally:
                # Wake the drainer once the graph is done (or timed out).
                queue.put_nowait(_STREAM_SENTINEL)

        runner = asyncio.create_task(_run_graph())

        # Drain live events as nodes emit them.
        try:
            while True:
                ev = await queue.get()
                if ev is _STREAM_SENTINEL:
                    break
                if ev.get("type") == "agent_activity":
                    agent = ev.get("agent", "")
                    yield {
                        "type": "agent_activity",
                        "agent": agent,
                        "status": _ACTIVITY_STATUS.get(agent, agent),
                        "content": ev.get("content", ""),
                    }
                else:
                    yield ev

            # Surface any exception raised inside the graph task.
            await runner
        finally:
            nodes._STREAM_QUEUE.reset(stream_token)

        final = await GRAPH.aget_state(config)
        values = final.values if final else {}
        events = values.get("events", []) or []

        answer = values.get("answer", "")
        pt = int(values.get("prompt_tokens", 0) or 0)
        ct = int(values.get("completion_tokens", 0) or 0)
        retries = int(values.get("retries", 0) or 0)
        specs = values.get("visualizations", []) or []
        review = values.get("review_result")
        result = {
            "answer": answer,
            "plan": values.get("plan", []),
            "steps": values.get("analysis_results", []),
            "sql_results": values.get("sql_results", []),
            "python_results": values.get("python_results", []),
            "visualizations": specs,
            "review": review,
            "prompt_tokens": pt,
            "completion_tokens": ct,
        }
        finished = datetime.utcnow()
        latency_ms = int((finished - started).total_seconds() * 1000)
        cost = _estimate_cost(pt, ct)
        steps, tool_calls = _build_trace(events)

        async with AsyncSessionLocal() as db:
            analysis = await db.get(Analysis, analysis_id)
            analysis.status = "completed"
            analysis.result_json = json.dumps(result, ensure_ascii=False)
            analysis.answer = answer
            analysis.prompt_tokens = pt
            analysis.completion_tokens = ct

            run = await db.get(AgentRun, run_id)
            run.status = "completed"
            run.prompt_tokens = pt
            run.completion_tokens = ct
            run.cost = cost
            run.latency_ms = latency_ms
            run.tool_calls = len(tool_calls)
            run.retries = retries
            run.finished_at = finished

            run_steps = [
                AgentStep(run_id=run_id, **s) for s in steps
            ]
            run_tools = [
                ToolCall(run_id=run_id, **tc) for tc in tool_calls
            ]
            db.add_all(run_steps)
            db.add_all(run_tools)
            await db.commit()

        # Optional Langfuse export (no-op unless keys configured).
        try:
            from app.services.langfuse_exporter import export_trace

            export_trace(run.to_summary(), [s.to_dict() for s in run_steps], [tc.to_dict() for tc in run_tools])
        except Exception:  # noqa: BLE001
            pass

        yield {
            "type": "agent_end",
            "status": "completed",
            "answer": answer,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "tool_calls": len(tool_calls),
            "retries": retries,
            "latency_ms": latency_ms,
        }
    except Exception as exc:  # noqa: BLE001
        finished = datetime.utcnow()
        latency_ms = int((finished - started).total_seconds() * 1000)
        async with AsyncSessionLocal() as db:
            analysis = await db.get(Analysis, analysis_id)
            if analysis is not None:
                analysis.status = "error"
                analysis.result_json = json.dumps({"answer": "", "error": str(exc)}, ensure_ascii=False)
                analysis.answer = ""
            run = await db.get(AgentRun, run_id)
            if run is not None:
                run.status = "error"
                run.latency_ms = latency_ms
                run.finished_at = finished
            await db.commit()
        logger.exception("analysis %s failed", analysis_id)
        yield {
            "type": "error",
            "message": f"分析运行出错：{exc}",
        }
        yield {
            "type": "agent_end",
            "status": "error",
            "error": str(exc),
            "answer": "",
        }


async def get_existing_run_summary(analysis_id: str) -> dict[str, Any] | None:
    """Return the latest AgentRun summary for an analysis, if any."""
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(AgentRun)
                .where(AgentRun.analysis_id == analysis_id)
                .order_by(AgentRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return row.to_summary() if row else None
