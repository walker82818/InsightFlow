"""SQL execution tool backed by DuckDB (Phase 2).

The agent calls this with a SQL string; we ensure the dataset is registered
with DuckDB (idempotent) and run the read-only query.
"""
from __future__ import annotations

from typing import Any

from app.services import duckdb as duckdb_svc

# OpenAI-style function schema advertised to the LLM.
SQL_TOOL_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "sql_execute",
        "description": (
            "Run a read-only SQL query against the active dataset table using "
            "DuckDB. Only SELECT/WITH/SHOW/DESCRIBE/EXPLAIN are allowed; writes "
            "are rejected. Returns columns, rows, row_count and whether the "
            "result was truncated."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": (
                        "The SQL query to execute, e.g. "
                        "\"SELECT region, SUM(revenue) FROM <table> "
                        "GROUP BY region ORDER BY 2 DESC\"."
                    ),
                }
            },
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
}


def run_sql_tool(
    datasets: list[dict[str, Any]],
    sql: str,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Register every referenced dataset (idempotent) then run read-only SQL.

    ``datasets`` is a list of DatasetRef-style dicts (keys: id, storage_path,
    file_type). Registering all of them up front lets the SQL JOIN across tables,
    enabling multi-document analysis.
    """
    for d in datasets:
        duckdb_svc.register_dataset(d["id"], d["storage_path"], d["file_type"])
    return duckdb_svc.query(sql, timeout=timeout)
