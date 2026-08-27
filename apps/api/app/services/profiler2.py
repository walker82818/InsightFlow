"""Data Profiler 2.0 (P0).

Derives the upgraded, standalone ``DatasetProfile`` fields from the base profile
(``profiling.profile_dataframe``) plus the source DataFrame:

- quality report: deterministic 0-100 score + per-issue findings
- field roles: id / time dimension / dimension / metric / numeric dimension / text
- relation hints: heuristic FK/same-name joins (suggested only, never auto-joined)
- anomaly detection: future dates, negatives where non-negative expected, IQR spikes

This module is pure & deterministic (no LLM); it is consumed by ``profile_node``
and feeds the Semantic Layer (``semantic_node``) and Insight Discovery later.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.profiling import _infer_type, _native

# Field roles exposed to the rest of the system.
ROLE_ID = "id"
ROLE_TIME = "time"
ROLE_DIMENSION = "dimension"
ROLE_METRIC = "metric"
ROLE_NUMERIC_DIMENSION = "numeric_dimension"
ROLE_TEXT = "text"

# A low-cardinality numeric column (e.g. a 1-5 rating) is treated as a numeric
# dimension rather than a metric.
_NUMERIC_DIM_MAX_UNIQUE = 20

# Quality weights per issue category (penalties subtracted from 100).
_WEIGHTS = {
    "missing": 8,
    "duplicate": 6,
    "anomaly": 10,
    "format": 6,
    "constant": 4,
    "skew": 5,
}


def _norm(name: str) -> str:
    """Normalize a column name for same-name matching across tables."""
    import re

    s = str(name).lower()
    s = re.sub(r"[_\s\-]+", "", s)
    s = re.sub(r"(id)$", "", s)  # strip trailing "id"
    return s


# --------------------------------------------------------------------------- #
# 2.2  Quality report
# --------------------------------------------------------------------------- #
def quality_report(
    df: pd.DataFrame, columns: list[dict[str, Any]]
) -> tuple[float, list[dict[str, Any]]]:
    """Return (quality_score, issues[]). Deterministic & explainable."""
    issues: list[dict[str, Any]] = []
    total = max(int(len(df)), 1)
    cells = max(total * max(len(df.columns), 1), 1)

    # Dataset-level: duplicate rows.
    dup = int(df.duplicated().sum())
    if dup:
        issues.append(
            {
                "column": "*",
                "category": "duplicate",
                "severity": "medium" if dup / total < 0.05 else "high",
                "message": f"发现 {dup} 行重复（占比 {dup / total:.1%}）",
                "suggestion": "去重或确认数据源是否允许重复记录",
            }
        )

    col_names = [str(c["name"]) for c in columns]
    df_renamed = df.copy()
    df_renamed.columns = col_names

    for c in columns:
        name = str(c["name"])
        series = df_renamed[name]
        stats = c.get("stats", {})
        dtype = c.get("type", "string")
        total_col = max(int(len(series)), 1)

        # Missing.
        miss_ratio = stats.get("missing_ratio", 0.0)
        if miss_ratio >= 0.5:
            issues.append(
                {
                    "column": name,
                    "category": "missing",
                    "severity": "high",
                    "message": f"缺失率 {miss_ratio:.0%}，列信息价值低",
                    "suggestion": "考虑删除该列或用业务默认值填充",
                }
            )
        elif miss_ratio >= 0.1:
            issues.append(
                {
                    "column": name,
                    "category": "missing",
                    "severity": "medium",
                    "message": f"缺失率 {miss_ratio:.0%}",
                    "suggestion": "确认缺失是否业务常态，必要时填充",
                }
            )

        # Constant column (low information).
        if stats.get("distinct", 1) <= 1 and miss_ratio < 1:
            issues.append(
                {
                    "column": name,
                    "category": "constant",
                    "severity": "low",
                    "message": "列值恒定，无分析区分度",
                    "suggestion": "分组/分析时可忽略该列",
                }
            )

        # Numeric: negatives, spikes (IQR).
        if dtype in ("integer", "float"):
            nums = pd.to_numeric(series, errors="coerce").dropna()
            if len(nums):
                if (nums < 0).any():
                    issues.append(
                        {
                            "column": name,
                            "category": "anomaly",
                            "severity": "medium",
                            "message": "数值含负值，可能超出业务合理范围",
                            "suggestion": "核实负值是否合法（如退款/差额）",
                        }
                    )
                q1, q3 = nums.quantile(0.25), nums.quantile(0.75)
                iqr = q3 - q1
                if iqr > 0:
                    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                    out = int(((nums < lo) | (nums > hi)).sum())
                    if out and out / len(nums) > 0.01:
                        issues.append(
                            {
                                "column": name,
                                "category": "anomaly",
                                "severity": "medium",
                                "message": f"检出 {out} 个 IQR 离群值（占比 {out / len(nums):.1%}）",
                                "suggestion": "核对离群值是否真实业务事件",
                            }
                        )

        # Date: future dates.
        if dtype == "date":
            dts = pd.to_datetime(series, errors="coerce").dropna()
            if len(dts):
                now = pd.Timestamp.now(tz=dts.iloc[0].tz)
                future = int((dts > now).sum())
                if future:
                    issues.append(
                        {
                            "column": name,
                            "category": "anomaly",
                            "severity": "medium",
                            "message": f"存在 {future} 个未来日期",
                            "suggestion": "确认日期是否因时区/录入错误超前",
                        }
                    )

        # Format: empty-string / unparseable for date columns.
        if dtype == "date":
            parse_ok = pd.to_datetime(series, errors="coerce").notna().sum()
            bad = total_col - parse_ok
            if bad and bad / total_col > 0.05:
                issues.append(
                    {
                        "column": name,
                        "category": "format",
                        "severity": "medium",
                        "message": f"{bad} 个值无法解析为日期",
                        "suggestion": "统一日期格式后再分析",
                    }
                )

    # Aggregate score.
    score = 100.0
    for iss in issues:
        score -= _WEIGHTS.get(iss["category"], 5)
    score = max(0.0, min(100.0, round(score, 1)))

    # Rank issues by severity.
    _sev = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: _sev.get(x["severity"], 3))
    return score, issues


# --------------------------------------------------------------------------- #
# 2.3  Field role inference
# --------------------------------------------------------------------------- #
def infer_roles(columns: list[dict[str, Any]]) -> dict[str, str]:
    """Map each column to a role using deterministic heuristics."""
    roles: dict[str, str] = {}
    for c in columns:
        name = str(c["name"]).lower()
        dtype = c.get("type", "string")
        stats = c.get("stats", {})
        distinct = stats.get("distinct", 0)
        total = max(stats.get("count", 0), 1)
        miss = stats.get("missing_ratio", 0.0)
        uniq_ratio = distinct / total if total else 0.0

        # id: high uniqueness + low missing + id-like name (numeric metrics that
        # happen to be all-unique should stay metrics unless named like an id).
        id_name = any(
            k in name for k in ("id", "key", "_no", "code", "编号", "number")
        )
        if (
            uniq_ratio >= 0.95
            and miss < 0.5
            and dtype in ("integer", "string")
            and (dtype == "string" or id_name)
        ):
            roles[str(c["name"])] = ROLE_ID
            continue

        if dtype == "date":
            roles[str(c["name"])] = ROLE_TIME
            continue

        if dtype == "boolean":
            roles[str(c["name"])] = ROLE_DIMENSION
            continue

        if dtype == "category":
            roles[str(c["name"])] = ROLE_DIMENSION
            continue

        if dtype == "string":
            # Names that look like time buckets are dimensions; otherwise text.
            if any(k in name for k in ("date", "time", "month", "year", "day", "week")):
                roles[str(c["name"])] = ROLE_DIMENSION
            else:
                roles[str(c["name"])] = ROLE_TEXT
            continue

        if dtype in ("integer", "float"):
            # Low-cardinality numeric => numeric dimension (e.g. rating 1-5).
            # A column is a numeric dimension when EITHER
            #   (a) it is a small bounded integer scale (max - min <= 20), e.g. 1-5,
            #       regardless of row count; OR
            #   (b) distinct count is small both in absolute terms and relative to
            #       row count.
            # This keeps high-cardinality metrics like `amount` as metrics while
            # correctly classifying ratings/scales.
            rel_ratio = distinct / total if total else 1.0
            stats = c.get("stats", {})
            vmin = stats.get("min")
            vmax = stats.get("max")
            bounded_scale = (
                isinstance(vmin, (int, float))
                and isinstance(vmax, (int, float))
                and (vmax - vmin) <= _NUMERIC_DIM_MAX_UNIQUE
            )
            if (
                (bounded_scale or (distinct <= _NUMERIC_DIM_MAX_UNIQUE and rel_ratio <= 0.1))
                and miss < 0.5
            ):
                roles[str(c["name"])] = ROLE_NUMERIC_DIMENSION
            else:
                roles[str(c["name"])] = ROLE_METRIC
            continue

        roles[str(c["name"])] = ROLE_TEXT
    return roles


# --------------------------------------------------------------------------- #
# 2.4  Relation hints
# --------------------------------------------------------------------------- #
def infer_relations(
    columns: list[dict[str, Any]], df: pd.DataFrame
) -> list[dict[str, Any]]:
    """Heuristic join hints based on same-name + value-domain overlap.

    P0 is deliberately conservative: returns ``relation_type="suggested_join"``
    with a strength score, never auto-joins across tables.
    """
    relations: list[dict[str, Any]] = []
    normalized: dict[str, list[str]] = {}
    for c in columns:
        name = str(c["name"])
        normalized.setdefault(_norm(name), []).append(name)

    col_names = [str(c["name"]) for c in columns]
    df_renamed = df.copy()
    df_renamed.columns = col_names

    for norm, names in normalized.items():
        if len(names) < 2:
            continue
        # Pairwise overlap among same-normalized-name columns.
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                col_a = df_renamed[a]
                col_b = df_renamed[b]
                if not (col_a.dtype.kind in "if" or col_b.dtype.kind in "if"):
                    continue
                na = pd.to_numeric(col_a, errors="coerce").dropna()
                nb = pd.to_numeric(col_b, errors="coerce").dropna()
                if na.empty or nb.empty:
                    continue
                lo = max(na.min(), nb.min())
                hi = min(na.max(), nb.max())
                if lo > hi:
                    continue
                overlap_a = ((na >= lo) & (na <= hi)).mean()
                overlap_b = ((nb >= lo) & (nb <= hi)).mean()
                strength = round(min(overlap_a, overlap_b), 3)
                if strength >= 0.5:
                    relations.append(
                        {
                            "left_col": a,
                            "right_col": b,
                            "relation_type": "suggested_join",
                            "strength": strength,
                        }
                    )
    return relations


# --------------------------------------------------------------------------- #
# 2.5  Anomaly detection (dataset-level summary)
# --------------------------------------------------------------------------- #
def detect_anomalies(
    df: pd.DataFrame, columns: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Reusable anomaly list for the profile (and later insight ``anomaly`` kind)."""
    anomalies: list[dict[str, Any]] = []
    col_names = [str(c["name"]) for c in columns]
    df_renamed = df.copy()
    df_renamed.columns = col_names

    for c in columns:
        name = str(c["name"])
        dtype = c.get("type", "string")
        series = df_renamed[name]
        if dtype in ("integer", "float"):
            nums = pd.to_numeric(series, errors="coerce").dropna()
            if len(nums) < 4:
                continue
            q1, q3 = nums.quantile(0.25), nums.quantile(0.75)
            iqr = q3 - q1
            if iqr <= 0:
                continue
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            idx = nums[(nums < lo) | (nums > hi)].index
            if len(idx):
                anomalies.append(
                    {
                        "column": name,
                        "kind": "outlier",
                        "severity": "medium",
                        "count": int(len(idx)),
                        "value": _native(nums.loc[idx].head(3).tolist()),
                        "message": f"检出 {len(idx)} 个离群值",
                    }
                )
        elif dtype == "date":
            dts = pd.to_datetime(series, errors="coerce").dropna()
            if len(dts):
                now = pd.Timestamp.now(tz=dts.iloc[0].tz)
                n_future = int((dts > now).sum())
                if n_future:
                    anomalies.append(
                        {
                            "column": name,
                            "kind": "future_date",
                            "severity": "medium",
                            "count": n_future,
                            "value": _native(dts[dts > now].max()),
                            "message": f"存在 {n_future} 个未来日期",
                        }
                    )
    return anomalies


# --------------------------------------------------------------------------- #
#  Build a full DatasetProfile dict from DataFrame + base profile
# --------------------------------------------------------------------------- #
def build_profile(
    df: pd.DataFrame, base_profile: dict[str, Any]
) -> dict[str, Any]:
    """Compose the 2.0 profile payload persisted to ``dataset_profiles``."""
    columns: list[dict[str, Any]] = base_profile.get("columns", [])

    quality_score, issues = quality_report(df, columns)
    roles = infer_roles(columns)
    relations = infer_relations(columns, df)
    anomalies = detect_anomalies(df, columns)

    schema_json = {
        "roles": roles,
        "relations": relations,
        "columns": columns,
    }
    return {
        "quality_score": quality_score,
        "issues": issues,
        "schema_json": schema_json,
        "anomalies": anomalies,
    }
