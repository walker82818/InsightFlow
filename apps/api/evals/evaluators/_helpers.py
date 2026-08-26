"""Shared helpers for evaluators."""
from __future__ import annotations

import re
from typing import Any

# Verbs that must never appear in an *executed* (successful) SQL statement.
FORBIDDEN_WRITE = {
    "drop",
    "delete",
    "update",
    "insert",
    "create",
    "alter",
    "truncate",
    "merge",
    "grant",
    "revoke",
    "replace",
}


def collect_sqls(result: dict, trace: dict | None) -> list[str]:
    sqls: list[str] = []
    for r in (result.get("sql_results") or []):
        s = (r.get("sql") or "").strip()
        if s:
            sqls.append(s)
    for tc in ((trace or {}).get("tool_calls") or []):
        inp = tc.get("input") or {}
        s = inp.get("sql") or inp.get("code") or ""
        if isinstance(s, str) and s.strip():
            sqls.append(s)
    return sqls


def collect_tools(result: dict, trace: dict | None) -> set[str]:
    tools: set[str] = set()
    for tc in ((trace or {}).get("tool_calls") or []):
        t = tc.get("tool")
        if t:
            tools.add(t)
    for _ in (result.get("sql_results") or []):
        tools.add("sql_execute")
    for _ in (result.get("python_results") or []):
        tools.add("python_execute")
    return tools


def first_verb(sql: str) -> str:
    m = re.search(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", sql or "")
    return m.group(1).lower() if m else ""
