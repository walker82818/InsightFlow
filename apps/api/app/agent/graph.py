"""LangGraph orchestration graph (Phase 3).

Topology (design §6.1):

    START → planner → analysis → visualization → reviewer → (retry) analysis / END

``reviewer`` conditionally routes back to ``analysis`` when the review fails
and we have retries left. State is checkpointed with an in-memory saver keyed
by ``thread_id`` (the execution can be resumed by re-invoking with the same
thread id — Phase 7 will swap in a PostgreSQL-backed saver).
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
