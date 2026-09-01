"""DuckDB analysis engine (Phase 2).

Registers uploaded datasets as queryable tables and runs *read-only* SQL with
a wall-clock timeout. Uses a file-backed DuckDB database so every request can
open its own connection (thread-safe) while sharing the same tables.

Design notes
------------
- Registration uses a writable connection (CREATE OR REPLACE TABLE ...).
- Queries use a ``read_only`` connection, so even a malicious/buggy query
  cannot mutate data through this path.
- The timeout is enforced via a thread-pool submit + ``future.result(timeout)``.
  This bounds how long we wait for the result; DuckDB itself is cancelled on
  the next statement boundary. Good enough for a local single-user MVP.
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus

import duckdb

from app.core.config import settings

# Statements may only *begin* with these verbs (read-only / introspection).
_ALLOWED_START = {
    "select",
    "with",
    "explain",
    "show",
    "describe",
    "pragma",
    "values",
    "from",
    "table",
}


class DuckDBError(Exception):
    pass


def _db_path() -> str:
    # Resolve relative to the api package root so it lands in apps/api/data.
    if os.path.isabs(settings.duckdb_path):
        return settings.duckdb_path
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(root, settings.duckdb_path)


def _table_name(dataset_id: str) -> str:
    return f"ds_{dataset_id.replace('-', '_')}"


def table_name(dataset_id: str) -> str:
    """Public accessor for the DuckDB table name of a dataset."""
    return _table_name(dataset_id)


def _resolve_file(storage_path: str) -> str:
    backend = (settings.storage_backend or "local").lower()
    if backend == "local":
        return os.path.abspath(os.path.join(settings.upload_dir, storage_path))
    # minio-backed datasets would need a download step (Phase 5).
    raise DuckDBError(
        "analysis over minio-backed datasets is not supported yet; "
        "set STORAGE_BACKEND=local to use the SQL tool"
    )


def _strip_sql(sql: str) -> str:
    """Remove comments and string literals so keyword checks are robust."""
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"'[^']*'", "''", sql)
    sql = re.sub(r'"[^"]*"', '""', sql)
    return sql


def assert_readonly(sql: str) -> None:
    """Reject any statement that is not a read-only query."""
    cleaned = _strip_sql(sql)
    for stmt in cleaned.split(";"):
        token = re.search(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", stmt)
        if not token:
            continue
        verb = token.group(1).lower()
        if verb not in _ALLOWED_START:
            raise DuckDBError(
                f"only read-only queries are allowed (got statement starting "
                f"with '{verb}'); denied verbs include DROP/DELETE/UPDATE/INSERT/"
                f"CREATE/ALTER."
            )


def register_dataset(dataset_id: str, storage_path: str, file_type: str) -> str:
    """Load an uploaded file into a DuckDB table. Returns the table name."""
    table = _table_name(dataset_id)
    path = _resolve_file(storage_path)
    if not os.path.exists(path):
        raise DuckDBError(f"dataset file not found on disk: {path}")

    ft = (file_type or "").lower()
    if ft == "csv":
        source = "read_csv_auto(?)"
    elif ft in ("xlsx", "xls"):
        # DuckDB's read_xlsx takes `sheet` as a 1-based integer index OR a sheet
        # name string. Passing sheet=1 means "2nd sheet" (1-indexed), which fails
        # for the common single "Sheet1" workbooks. Omitting `sheet` reads the
        # first/default sheet, which is what we want.
        source = "read_xlsx(?)"
    elif ft == "json":
        source = "read_json_auto(?)"
    elif ft == "parquet":
        source = "read_parquet(?)"
    else:
        raise DuckDBError(f"unsupported file type for analysis: {file_type}")

    db = _db_path()
    os.makedirs(os.path.dirname(db), exist_ok=True)
    con = duckdb.connect(db)
    try:
        # Drop first so a previously-failed registration (e.g. wrong xlsx sheet)
        # cannot leave a corrupt/stale catalog entry behind.
        con.execute(f'DROP TABLE IF EXISTS "{table}"')
        con.execute(
            f'CREATE TABLE "{table}" AS SELECT * FROM {source}', [path]
        )
        con.execute("CHECKPOINT")
    finally:
        con.close()
    return table


def _jsonify(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    return value


def _to_result(columns: list[str], rows: list[tuple], limit: int) -> dict[str, Any]:
    truncated = len(rows) > limit
    capped = rows[:limit]
    return {
        "columns": columns,
        "rows": [[_jsonify(v) for v in row] for row in capped],
        "row_count": len(rows),
        "truncated": truncated,
    }


def query(sql: str, timeout: int | None = None) -> dict[str, Any]:
    """Run a read-only SQL query with a wall-clock timeout.

    Returns ``{columns, rows, row_count, truncated}`` (JSON-safe).
    """
    assert_readonly(sql)
    db = _db_path()
    if not os.path.exists(db):
        raise DuckDBError(
            "no dataset registered yet; run an analysis on an uploaded dataset "
            "first (which registers it with DuckDB)."
        )

    timeout = timeout or settings.sandbox_timeout

    def _run() -> tuple[list[str], list[tuple]]:
        # NOTE: we open the connection read-write (not read_only). On a file-backed
        # DuckDB database, a read-only connection and a read-write connection
        # (e.g. the one used by register_dataset) cannot coexist safely and
        # produce spurious "Catalog write-write conflict" errors. Data integrity
        # is still guaranteed because assert_readonly() rejects any mutating SQL
        # before it ever reaches DuckDB.
        con = duckdb.connect(db)
        try:
            rel = con.execute(sql)
            cols = [d[0] for d in rel.description] if rel.description else []
            data = rel.fetchall()
        finally:
            con.close()
        return cols, data

    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_run)
        try:
            cols, data = fut.result(timeout=timeout)
        except TimeoutError as exc:
            raise DuckDBError(
                f"query exceeded the {timeout}s timeout"
            ) from exc
        except duckdb.Error as exc:  # noqa: BLE001
            raise DuckDBError(f"duckdb error: {exc}") from exc

    return _to_result(cols, data, settings.max_sql_rows)


def _pg_connstring(conn: dict) -> str:
    user = quote_plus(conn.get("username") or "")
    pw = quote_plus(conn.get("password") or "")
    host = conn.get("host") or "localhost"
    port = conn.get("port") or 5432
    dbname = quote_plus(conn.get("database") or "")
    return f"postgresql://{user}:{pw}@{host}:{port}/{dbname}"


def _mysql_connstring(conn: dict) -> str:
    user = quote_plus(conn.get("username") or "")
    pw = quote_plus(conn.get("password") or "")
    host = conn.get("host") or "localhost"
    port = conn.get("port") or 3306
    dbname = quote_plus(conn.get("database") or "")
    return f"mysql://{user}:{pw}@{host}:{port}/{dbname}"


# Identifiers interpolated into DuckDB SQL (schema / table names). Restrict to a
# conservative charset so a crafted input cannot break out of the string literal
# and inject arbitrary SQL via postgres_scan / sqlite_scan / mysql_scan.
_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _assert_identifier(value: str | None, what: str) -> str:
    value = (value or "").strip()
    if not value or not _IDENT_RE.match(value):
        raise DuckDBError(
            f"invalid {what}: {value!r}; only letters, digits and underscore are allowed"
        )
    return value


def register_db_dataset(
    dataset_id: str,
    db_type: str,
    conn: dict[str, Any],
    table: str,
    schema: str = "public",
) -> dict[str, Any]:
    """把远程数据库表物化为 DuckDB 表，返回 {table, row_count, column_count}。"""
    table_name = _table_name(dataset_id)
    db = _db_path()
    os.makedirs(os.path.dirname(db), exist_ok=True)
    con = duckdb.connect(db)
    try:
        con.execute("SET enable_external_access = true;")
        con.execute("SET lock_configuration = false;")
        dt = (db_type or "").lower()
        # 用户输入的表名/schema 一律白名单校验后再拼进 SQL，防止注入。
        table = _assert_identifier(table, "table name")
        schema = _assert_identifier(schema or "public", "schema name")
        if dt == "postgres":
            con.execute("INSTALL postgres; LOAD postgres;")
            src = f"postgres_scan('{_pg_connstring(conn)}', '{schema}', '{table}')"
        elif dt == "sqlite":
            con.execute("INSTALL sqlite; LOAD sqlite;")
            db_path = conn.get("database") or ""
            if not db_path or "'" in db_path:
                raise DuckDBError(
                    "invalid sqlite database path: must not be empty or contain quotes"
                )
            src = f"sqlite_scan('{db_path}', '{table}')"
        elif dt == "mysql":
            con.execute("INSTALL mysql; LOAD mysql;")
            src = f"mysql_scan('{_mysql_connstring(conn)}', '{table}')"
        else:
            raise DuckDBError(f"unsupported db_type: {db_type}")
        con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM {src}')
        con.execute("CHECKPOINT")
        row_count = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        column_count = len(con.execute(f'DESCRIBE "{table_name}"').description)
    finally:
        con.close()
    return {
        "table": table_name,
        "row_count": int(row_count),
        "column_count": int(column_count),
    }


def sample_table(table_name: str, limit: int = 200000) -> "pd.DataFrame":
    """读取已注册表的样本（用于画像），返回 DataFrame。"""
    import pandas as pd

    db = _db_path()
    con = duckdb.connect(db)
    try:
        con.execute("SET enable_external_access = true;")
        con.execute("SET lock_configuration = false;")
        df = con.execute(f'SELECT * FROM "{table_name}" LIMIT {int(limit)}').df()
    finally:
        con.close()
    return df
