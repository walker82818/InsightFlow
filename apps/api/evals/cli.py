"""CLI entry point for the evaluation harness.

Usage::
    cd apps/api
    python -m evals.cli                 # run all golden datasets
    python -m evals.cli basic complex   # run only selected datasets
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from .runner import run_all

_RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


async def main() -> None:
    names = sys.argv[1:] or None
    out = await run_all(dataset_names=names)

    print("=" * 64)
    print("InsightFlow Evaluation — Metrics")
    print("=" * 64)
    for k, v in out["metrics"].items():
        print(f"  {k:22}: {v}")
    print("-" * 64)
    for r in out["cases"]:
        print(
            f"  {r['dataset']:12} {r['case_id']:12} "
            f"success={str(r['task_success']):5} overall={r['overall']:<6} [{r['status']}]"
        )
        for sk, sv in r["scores"].items():
            print(f"      - {sk:12}: score={sv['score']}  {sv['detail']}")

    os.makedirs(_RESULTS_DIR, exist_ok=True)
    path = os.path.join(_RESULTS_DIR, "latest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
