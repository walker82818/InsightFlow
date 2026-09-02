"""Agent execution Trace models (Phase 6).

Stores a structured record of every analysis run so the frontend can render a
full Agent execution timeline (agents / tools / retries / tokens / latency).

- ``AgentRun``: one per analysis run (summary: tokens, cost, latency, retries).
- ``AgentStep``: each visible step (agent turn / message / chart / tool / error).
- ``ToolCall``: each SQL / Python tool invocation with input, output, duration.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid4())


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # ondelete=CASCADE：删除 analysis 时级联清理 run（与 evidence/report/root_cause 一致）。
    analysis_id: Mapped[str] = mapped_column(
        String, ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    thread_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="running")

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "analysis_id": self.analysis_id,
            "thread_id": self.thread_id,
            "status": self.status,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "tool_calls": self.tool_calls,
            "retries": self.retries,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    agent: Mapped[str] = mapped_column(String, default="system")
    step_type: Mapped[str] = mapped_column(String, default="agent")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    input: Mapped[Any] = mapped_column(JSON, nullable=True)
    output: Mapped[Any] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="ok")
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ts_ms: Mapped[int] = mapped_column(Integer, default=0)
    order_idx: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "step_type": self.step_type,
            "content": self.content,
            "input": self.input,
            "output": self.output,
            "status": self.status,
            "tokens": self.tokens,
            "duration_ms": self.duration_ms,
            "ts_ms": self.ts_ms,
            "order_idx": self.order_idx,
        }


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    tool: Mapped[str] = mapped_column(String)
    input: Mapped[Any] = mapped_column(JSON, nullable=True)
    output: Mapped[Any] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="success")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ts_ms: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "input": self.input,
            "output": self.output,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "ts_ms": self.ts_ms,
        }
