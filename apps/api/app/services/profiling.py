"""Dataset profiling (Phase 1).

Reads an uploaded file's bytes into a pandas DataFrame and derives:
- per-column logical type (string | integer | float | date | category | boolean)
- per-column statistics
- dataset-level profile (missing totals, duplicate rows)
- a small preview (first N rows)
"""
from __future__ import annotations

import io
from typing import Any

import pandas as pd

from app.core.config import settings

# Logical types we expose to the rest of the system.
LOGICAL_TYPES = {"string", "integer", "float", "date", "category", "boolean"}

_CATEGORY_MAX_RATIO = 0.5
_CATEGORY_MAX_UNIQUE = 60
_DATE_PARSE_MIN_RATIO = 0.8


class ProfilingError(Exception):
    pass


def _read_dataframe(data: bytes, file_type: str) -> pd.DataFrame:
    buf = io.BytesIO(data)
    ft = file_type.lower()
    if ft == "csv":
        return pd.read_csv(buf)
    if ft in ("xlsx", "xls"):
        return pd.read_excel(buf, engine="openpyxl")
    if ft == "json":
        return pd.read_json(buf)
    raise ProfilingError(f"unsupported file type: {file_type}")


def _infer_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"

    # object / string columns: try date, then category, then string.
    non_null = series.dropna()
    if len(non_null) == 0:
        return "string"

    try:
        parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
        if parsed.notna().sum() / len(non_null) >= _DATE_PARSE_MIN_RATIO:
            return "date"
    except Exception:  # noqa: BLE001
        pass

    nunique = non_null.nunique()
    if nunique / len(non_null) < _CATEGORY_MAX_RATIO and nunique <= _CATEGORY_MAX_UNIQUE:
        return "category"
    return "string"


def _column_stats(series: pd.Series, dtype: str) -> dict[str, Any]:
    total = len(series)
    non_null = int(series.notna().sum())
    missing = total - non_null
    stats: dict[str, Any] = {
        "count": non_null,
        "missing": missing,
        "missing_ratio": round(missing / total, 4) if total else 0.0,
        "distinct": int(series.nunique(dropna=True)),
    }

    if dtype in ("integer", "float"):
        numeric = series.dropna()
        if len(numeric):
            stats.update(
                {
                    "min": _native(numeric.min()),
                    "max": _native(numeric.max()),
                    "mean": round(float(numeric.mean()), 4),
                    "median": _native(numeric.median()),
                    "std": round(float(numeric.std()), 4),
                }
            )
    elif dtype == "date":
        dts = series.dropna()
        if len(dts):
            stats["min"] = _native(pd.Timestamp(dts.min()).date())
            stats["max"] = _native(pd.Timestamp(dts.max()).date())
    elif dtype in ("category", "boolean"):
        vc = series.value_counts(dropna=True).head(10)
        stats["top_values"] = [
            {"value": _native(k), "count": int(v)} for k, v in vc.items()
        ]
    elif dtype == "string":
        s = series.dropna().astype(str)
        if len(s):
            stats["avg_length"] = round(float(s.str.len().mean()), 2)
    return stats


def _native(v: Any) -> Any:
    """Convert numpy / pandas scalars & timestamps to JSON-native values."""
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:  # noqa: BLE001
            pass
    if hasattr(v, "item"):  # numpy scalar
        try:
            return v.item()
        except Exception:  # noqa: BLE001
            pass
    return v


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """对 DataFrame 做字段级画像，返回 {columns, profile, preview, row_count, column_count}。"""
    row_count = int(len(df))
    column_count = int(len(df.columns))

    columns: list[dict[str, Any]] = []
    total_missing = 0
    for pos, col in enumerate(df.columns):
        series = df[col]
        dtype = _infer_type(series)
        stats = _column_stats(series, dtype)
        total_missing += stats["missing"]
        columns.append({"name": str(col), "type": dtype, "position": pos, "stats": stats})

    duplicate_rows = int(df.duplicated().sum())
    cells = row_count * column_count if column_count else 0
    profile = {
        "row_count": row_count,
        "column_count": column_count,
        "duplicate_rows": duplicate_rows,
        "total_missing": total_missing,
        "missing_ratio": round(total_missing / cells, 4) if cells else 0.0,
    }

    preview = _preview(df)
    return {
        "columns": columns,
        "profile": profile,
        "preview": preview,
        "row_count": row_count,
        "column_count": column_count,
    }


def profile_bytes(data: bytes, file_type: str) -> dict[str, Any]:
    df = read_dataframe(data, file_type)
    return profile_dataframe(df)


def read_dataframe(data: bytes, file_type: str) -> pd.DataFrame:
    """Parse uploaded bytes into a DataFrame (public wrapper for profiling reuse)."""
    return _read_dataframe(data, file_type)


def _preview(df: pd.DataFrame) -> list[dict[str, Any]]:
    head = df.head(settings.preview_rows)
    records = head.where(pd.notnull(head), None).to_dict("records")
    return [{k: _native(v) for k, v in row.items()} for row in records]
