"""Optional Langfuse observability exporter (Phase 6).

This is a *best-effort* exporter: it is a no-op unless Langfuse credentials are
configured via env (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`,
`LANGFUSE_HOST`) **and** the `langfuse` package is installed. The analysis
pipeline never depends on Langfuse being present.

The exporter targets the Langfuse **v4** Python SDK API (event / observation
based). Each analysis run becomes a top-level trace whose steps and tool calls
are nested child observations, so the Langfuse UI shows the full agent DAG
(agents, tools, token usage, latency, cost) instead of a flat list.

The export is wrapped in try/except and never raises: observability must never
break the analysis response.
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings


def _usage_details(step: dict[str, Any]) -> dict[str, int] | None:
    """Map an agent step's token count to Langfuse usage_details."""
    tokens = int(step.get("tokens") or 0)
    if tokens <= 0:
        return None
    return {"input": tokens, "output": 0}


def export_trace(
    run: dict[str, Any],
    steps: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
) -> None:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return
    try:
        from langfuse import Langfuse
    except ImportError:
        return

    client: Any = None
    try:
        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host or "https://cloud.langfuse.com",
        )

        trace_meta = {
            "analysis_id": run.get("analysis_id"),
            "thread_id": run.get("thread_id"),
            "status": run.get("status"),
            "prompt_tokens": run.get("prompt_tokens"),
            "completion_tokens": run.get("completion_tokens"),
            "cost": run.get("cost"),
            "latency_ms": run.get("latency_ms"),
            "retries": run.get("retries"),
            "created_at": run.get("created_at"),
            "finished_at": run.get("finished_at"),
        }
        # Root trace spanning the whole run. Its body is supplied via
        # set_current_trace_io once the observation context is entered.
        with client.start_as_current_observation(
            name="analysis",
            as_type="span",
            input={"analysis_id": run.get("analysis_id"), "query": None},
            metadata=trace_meta,
        ):
            # Keep the exported body minimal; full answer lives in the DB.
            try:
                client.set_current_trace_io(
                    input={
                        "analysis_id": run.get("analysis_id"),
                        "thread_id": run.get("thread_id"),
                    },
                    output={
                        "status": run.get("status"),
                        "answer_tokens": run.get("completion_tokens"),
                    },
                )
            except Exception:  # noqa: BLE001
                pass

            # One nested observation per agent step / message / chart / error.
            for step in steps:
                _export_step(client, step)

            # Tool invocations as nested tool observations.
            for call in tool_calls:
                _export_tool(client, call)

        client.flush()
    except Exception:  # noqa: BLE001
        # Never let observability break the analysis response.
        return
    finally:
        if client is not None:
            try:
                client.shutdown()
            except Exception:  # noqa: BLE001
                pass


def _export_step(client: Any, step: dict[str, Any]) -> None:
    """Emit one nested observation for an agent step."""
    agent = step.get("agent") or "system"
    step_type = step.get("step_type") or "agent"
    status = step.get("status") or "ok"
    name = f"{agent}/{step_type}"
    metadata = {
        "agent": agent,
        "step_type": step_type,
        "status": status,
        "duration_ms": step.get("duration_ms"),
        "ts_ms": step.get("ts_ms"),
        "order_idx": step.get("order_idx"),
        "content": step.get("content"),
    }
    usage = _usage_details(step)
    kwargs: dict[str, Any] = {
        "name": name,
        "input": step.get("input"),
        "output": step.get("output"),
        "metadata": metadata,
    }
    if usage:
        kwargs["usage_details"] = usage
    # Agent turns become "agent" observations; errors carry the level.
    if step_type in ("agent", "message"):
        kwargs["as_type"] = "agent"
    elif step_type == "chart":
        kwargs["as_type"] = "chain"
    else:
        kwargs["as_type"] = "span"
    if status == "error":
        kwargs["level"] = "ERROR"
    try:
        with client.start_as_current_observation(**kwargs):
            pass
    except Exception:  # noqa: BLE001
        pass


def _export_tool(client: Any, call: dict[str, Any]) -> None:
    """Emit one nested tool observation."""
    status = call.get("status") or "success"
    kwargs: dict[str, Any] = {
        "name": f"tool/{call.get('tool')}",
        "as_type": "tool",
        "input": call.get("input"),
        "output": call.get("output"),
        "metadata": {
            "tool": call.get("tool"),
            "status": status,
            "duration_ms": call.get("duration_ms"),
            "ts_ms": call.get("ts_ms"),
        },
    }
    if status == "error":
        kwargs["level"] = "ERROR"
    try:
        with client.start_as_current_observation(**kwargs):
            pass
    except Exception:  # noqa: BLE001
        pass
