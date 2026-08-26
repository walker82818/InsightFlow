"""Evaluation scorers for Phase 8.

Each synchronous evaluator exposes ``evaluate(case, result, trace) -> dict``
returning ``{"score": 0..1, "detail": str, ...}``. The report evaluator is
async (it calls the LLM to generate a report) and is only invoked when a case
opt-in via ``evaluate_report: true``.
"""
from .tool_usage import evaluate as tool_usage
from .correctness import evaluate as correctness
from .visualization import evaluate as visualization

__all__ = ["tool_usage", "correctness", "visualization"]
