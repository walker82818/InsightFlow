"""LangGraph orchestration graph (Phase 3).

Topology (design §6.1):

    START → planner → analysis → visualization → reviewer → (retry) analysis / END

``reviewer`` conditionally routes back to ``analysis`` when the review fails
and we have retries left.

Checkpointing: an in-memory ``MemorySaver`` keyed by ``thread_id``.
``run_analysis`` (single_agent.py) currently generates a **fresh thread_id per
run**, so every execution gets its own checkpoint namespace and resume is not
exercised today. Pinning the thread_id (e.g. to ``analysis_id``) would allow
inspecting / resuming an interrupted run, but a new run would then inherit the
previous checkpoint — only enable that together with an explicit
"start a new run" reset. Phase 7 will swap in a PostgreSQL-backed saver.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agent import nodes
from app.core.config import settings


def _route_after_review(state: dict) -> str:
    review = state.get("review_result") or {}
    if review.get("passed"):
        return END
    if (state.get("retries", 0) or 0) >= settings.agent_max_retries:
        return END
    return "analysis"


def build_graph():
    g = StateGraph(nodes.AgentState)
    g.add_node("planner", nodes.planner_node)
    g.add_node("analysis", nodes.analysis_node)
    g.add_node("visualization", nodes.visualization_node)
    g.add_node("reviewer", nodes.reviewer_node)

    g.add_edge(START, "planner")
    g.add_edge("planner", "analysis")
    g.add_edge("analysis", "visualization")
    g.add_edge("visualization", "reviewer")
    g.add_conditional_edges(
        "reviewer", _route_after_review, {"analysis": "analysis", END: END}
    )
    return g.compile(checkpointer=MemorySaver())
