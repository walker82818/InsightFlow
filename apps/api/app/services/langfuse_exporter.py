"""Optional Langfuse observability exporter (Phase 6).

This is a *best-effort* exporter: it is a no-op unless Langfuse credentials are
configured via env (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`,
`LANGFUSE_HOST`) **and** the `langfuse` package is installed. The analysis
pipeline never depends on Langfuse being present.
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings


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

    try:
        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        trace = client.trace(
            name="analysis",
            id=run.get("id"),
            input={"analysis_id": run.get("analysis_id")},
            output={"answer_tokens": run.get("completion_tokens")},
            metadata={
                "prompt_tokens": run.get("prompt_tokens"),
                "completion_tokens": run.get("completion_tokens"),
                "cost": run.get("cost"),
                "latency_ms": run.get("latency_ms"),
                "tool_calls": run.get("tool_calls"),
                "retries": run.get("retries"),
            },
        )
        for step in steps:
            trace.span(
                name=f"{step.get('agent')}/{step.get('step_type')}",
                input=step.get("input"),
                output=step.get("output"),
                metadata={"status": step.get("status"), "duration_ms": step.get("duration_ms")},
            )
        for call in tool_calls:
            trace.span(
                name=f"tool/{call.get('tool')}",
                input=call.get("input"),
                output=call.get("output"),
                metadata={"status": call.get("status"), "duration_ms": call.get("duration_ms")},
            )
        client.flush()
    except Exception:  # noqa: BLE001
        # Never let observability break the analysis response.
        return
