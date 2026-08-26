"""InsightFlow evaluation harness (Phase 8).

Golden datasets + deterministic evaluators that score the *real* analysis
pipeline (reusing ``app.agent.single_agent.run_analysis``). Run with::

    cd apps/api && python -m evals.cli

The heavy ``runner`` (which imports the whole app) is imported explicitly by
``cli.py`` and the API router, so this package stays light to import.
"""
from __future__ import annotations

__all__: list[str] = []
