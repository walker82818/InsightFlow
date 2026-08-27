"""Insight Discovery node (2.0, P0 InsightNode).

Deterministic, rule-based detectors that turn the dataset's own data into
"active insights" available right after upload (no user question required).
Each detector emits structured Insights (kind/title/conclusion/metric/
dimensions/evidence/confidence/severity/sql), mirroring the model in
``app.models.insight``.

Detectors (six kinds):
  - trend              : metric grouped over a time dimension -> monotonic rise/fall
  - anomaly            : IQR outlier spikes per metric (reuses profiler2)
  - distribution_shift : first-half vs second-half mean shift of a metric
  - top_contribution   : dominant category's share of a metric (Pareto)
  - correlation        : strong Pearson pairs among metric columns
  - quality            : data quality findings (missing / duplicates / low score)

No LLM is required; conclusions are synthesized from the numbers. Best-effort:
any detector that fails is skipped rather than raising.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.services import profiler2

KIND_TREND = "trend"
KIND_ANOMALY = "anomaly"
KIND_SHIFT = "distribution_shift"
KIND_CONTRIBUTION = "top_contribution"
KIND_CORRELATION = "correlation"
KIND_QUALITY = "quality"

_SEVERITY_HIGH = "high"
_SEVERITY_MEDIUM = "medium"
_SEVERITY_LOW = "low"

# Minimum abs correlation to report a pair.
_CORR_THRESHOLD = 0.7
# Time keywords to detect a date-like dimension when role is not time.
_TIME_HINTS = ("date", "time", "day", "month", "quarter", "year", "日期", "时间")


def _fmt(v: Any) -> str:
    """Compact human-friendly formatting for numbers in conclusions."""
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f) and abs(f) < 1e15:
        return f"{int(f):,}"
    return f"{f:,.2f}"


def _pct(a: float, b: float) -> str:
    if b == 0:
        return "—"
    return f"{a / b * 100:.1f}%"


def _parse_time_series(series: pd.Series) -> pd.Series:
    """Best-effort coercion of a column to a sortable datetime series."""
    try:
        return pd.to_datetime(series, errors="coerce")
    except Exception:  # noqa: BLE001
        return series


def _pick_metric(schema: dict[str, Any]) -> str | None:
    """Return the first metric column from the role schema."""
    roles = schema.get("roles", {})
    for col, role in roles.items():
        if role == profiler2.ROLE_METRIC:
            return str(col)
    return None


def _pick_time(schema: dict[str, Any]) -> str | None:
    roles = schema.get("roles", {})
    for col, role in roles.items():
        if role == profiler2.ROLE_TIME:
            return str(col)
    # Fallback: a column whose name looks like a time field.
    for col in roles:
        if any(k in str(col).lower() for k in _TIME_HINTS):
            return str(col)
    return None


def _pick_dimension(schema: dict[str, Any]) -> str | None:
    """Pick the first categorical dimension (non-time)."""
    roles = schema.get("roles", {})
    for col, role in roles.items():
        if role == profiler2.ROLE_DIMENSION:
            return str(col)
    return None


def _detect_trend(df: pd.DataFrame, schema: dict[str, Any]) -> list[dict[str, Any]]:
    metric = _pick_metric(schema)
    time_col = _pick_time(schema)
    if metric is None or time_col is None:
        return []
    try:
        work = df[[time_col, metric]].dropna()
        if work.empty:
            return []
        work = work.copy()
        work[time_col] = _parse_time_series(work[time_col])
        work = work.sort_values(time_col)
        work[metric] = pd.to_numeric(work[metric], errors="coerce")
        work = work.dropna()
        # Aggregate per unique time bucket (avoid dupes).
        grouped = work.groupby(time_col, as_index=False)[metric].mean()
        if len(grouped) < 3:
            return []
        xs = list(range(len(grouped)))
        ys = grouped[metric].tolist()
        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        if var_x == 0:
            return []
        slope = cov / var_x
        # Normalize slope against the mean value for a relative magnitude.
        if mean_y == 0:
            return []
        rel = slope / mean_y
        if abs(rel) < 0.05:
            return []
        direction = "上升" if rel > 0 else "下降"
        first = grouped.iloc[0]
        last = grouped.iloc[-1]
        change = (last[metric] - first[metric]) / abs(first[metric]) if first[metric] else 0
        severity = (
            _SEVERITY_HIGH if abs(change) >= 0.5 else
            (_SEVERITY_MEDIUM if abs(change) >= 0.2 else _SEVERITY_LOW)
        )
        return [
            {
                "kind": KIND_TREND,
                "title": f"{metric} 整体{('上升' if change > 0 else '下降')}趋势",
                "conclusion": (
                    f"按 {time_col} 分组后，{metric} 呈{('上升' if change > 0 else '下降')}趋势："
                    f"从 {_fmt(first[metric])} 变化到 {_fmt(last[metric])}，"
                    f"累计变化 {_pct(change, 1)}，方向斜率约 {rel:+.2f}/期。"
                ),
                "metric": metric,
                "dimensions": [time_col],
                "evidence": {
                    "claim": f"{metric} 随 {time_col} {direction}",
                    "result": f"{_fmt(first[metric])} → {_fmt(last[metric])} ({_pct(change, 1)})",
                    "confidence": round(min(0.95, 0.5 + abs(rel)), 2),
                },
                "confidence": round(min(0.95, 0.5 + abs(rel)), 2),
                "severity": severity,
                "sql": (
                    f"SELECT {time_col}, AVG({metric}) AS {metric} FROM dataset "
                    f"GROUP BY {time_col} ORDER BY {time_col}"
                ),
            }
        ]
    except Exception:  # noqa: BLE001
        return []


def _detect_anomaly(df: pd.DataFrame, schema: dict[str, Any]) -> list[dict[str, Any]]:
    roles = schema.get("roles", {})
    out: list[dict[str, Any]] = []
    for col, role in roles.items():
        if role != profiler2.ROLE_METRIC:
            continue
        try:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(series) < 8:
                continue
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outliers = series[(series < lower) | (series > upper)]
            if outliers.empty:
                continue
            mean_v = series.mean()
            peak = outliers.abs().idxmax()
            peak_val = series.loc[peak]
            severity = _SEVERITY_HIGH if abs(peak_val - mean_v) / abs(mean_v) > 1 else (
                _SEVERITY_MEDIUM if abs(peak_val - mean_v) / abs(mean_v) > 0.5 else _SEVERITY_LOW
            )
            out.append(
                {
                    "kind": KIND_ANOMALY,
                    "title": f"{col} 存在异常离群值",
                    "conclusion": (
                        f"通过 IQR 规则检测到 {col} 有 {len(outliers)} 个离群点，"
                        f"峰值 {_fmt(peak_val)}，而均值约为 {_fmt(mean_v)}，"
                        f"偏离均值 {_pct(abs(peak_val - mean_v), abs(mean_v))}。"
                    ),
                    "metric": col,
                    "dimensions": [],
                    "evidence": {
                        "claim": f"{col} 存在离群点",
                        "result": f"离群 {len(outliers)} 个，峰值 {_fmt(peak_val)}，均值 {_fmt(mean_v)}",
                        "confidence": 0.9,
                    },
                    "confidence": 0.9,
                    "severity": severity,
                    "sql": (
                        f"SELECT * FROM dataset WHERE {col} < {lower:g} OR {col} > {upper:g}"
                    ),
                }
            )
        except Exception:  # noqa: BLE001
            continue
    return out


def _detect_shift(df: pd.DataFrame, schema: dict[str, Any]) -> list[dict[str, Any]]:
    metric = _pick_metric(schema)
    time_col = _pick_time(schema)
    if metric is None or time_col is None:
        return []
    try:
        work = df[[time_col, metric]].dropna()
        if len(work) < 10:
            return []
        work = work.copy()
        work[time_col] = _parse_time_series(work[time_col])
        work = work.sort_values(time_col)
        work[metric] = pd.to_numeric(work[metric], errors="coerce")
        work = work.dropna()
        half = len(work) // 2
        if half == 0:
            return []
        first, second = work.iloc[:half], work.iloc[half:]
        m1, m2 = first[metric].mean(), second[metric].mean()
        if m1 == 0:
            return []
        rel = (m2 - m1) / abs(m1)
        if abs(rel) < 0.3:
            return []
        direction = "上升" if rel > 0 else "下降"
        severity = _SEVERITY_HIGH if abs(rel) >= 0.8 else (
            _SEVERITY_MEDIUM if abs(rel) >= 0.5 else _SEVERITY_LOW
        )
        return [
            {
                "kind": KIND_SHIFT,
                "title": f"{metric} 分布前后半段发生{('抬升' if rel > 0 else '下滑')}",
                "conclusion": (
                    f"按时间排序后，{metric} 前半段均值 {_fmt(m1)}，后半段均值 {_fmt(m2)}，"
                    f"分布偏移 {_pct(rel, 1)}。这可能意味着量级或经营环境发生了阶段性变化。"
                ),
                "metric": metric,
                "dimensions": [time_col],
                "evidence": {
                    "claim": f"{metric} 前后半段分布显著变化",
                    "result": f"{_fmt(m1)} → {_fmt(m2)} ({_pct(rel, 1)})",
                    "confidence": round(0.5 + min(0.4, abs(rel) * 0.5), 2),
                },
                "confidence": round(0.5 + min(0.4, abs(rel) * 0.5), 2),
                "severity": severity,
                "sql": (
                    f"SELECT AVG({metric}) FROM dataset WHERE {time_col} <= ... "
                    f"UNION ALL SELECT AVG({metric}) FROM dataset WHERE {time_col} > ..."
                ),
            }
        ]
    except Exception:  # noqa: BLE001
        return []


def _detect_contribution(
    df: pd.DataFrame, schema: dict[str, Any]
) -> list[dict[str, Any]]:
    metric = _pick_metric(schema)
    dim = _pick_dimension(schema)
    if metric is None or dim is None:
        return []
    try:
        work = df[[dim, metric]].dropna()
        if work.empty:
            return []
        work[metric] = pd.to_numeric(work[metric], errors="coerce")
        work = work.dropna()
        total = work[metric].sum()
        if total == 0:
            return []
        grouped = work.groupby(dim, as_index=False)[metric].sum().sort_values(metric, ascending=False)
        if grouped.empty:
            return []
        top = grouped.iloc[0]
        share = top[metric] / total
        # Only report a meaningful concentration (>= 30%).
        if share < 0.3:
            return []
        severity = (
            _SEVERITY_HIGH if share >= 0.7 else
            (_SEVERITY_MEDIUM if share >= 0.5 else _SEVERITY_LOW)
        )
        return [
            {
                "kind": KIND_CONTRIBUTION,
                "title": f"{dim} 中 {top[dim]} 占比最高",
                "conclusion": (
                    f"按 {dim} 汇总 {metric}，最高的是 {top[dim]}，贡献 {_fmt(top[metric])}，"
                    f"占总量 {_pct(share, 1)}。该维度存在明显的头部集中效应。"
                ),
                "metric": metric,
                "dimensions": [dim],
                "evidence": {
                    "claim": f"{dim}={top[dim]} 贡献最高",
                    "result": f"{_fmt(top[metric])} / 总 {_fmt(total)} ({_pct(share, 1)})",
                    "confidence": round(0.5 + share * 0.4, 2),
                },
                "confidence": round(0.5 + share * 0.4, 2),
                "severity": severity,
                "sql": (
                    f"SELECT {dim}, SUM({metric}) AS v FROM dataset "
                    f"GROUP BY {dim} ORDER BY v DESC"
                ),
            }
        ]
    except Exception:  # noqa: BLE001
        return []


def _detect_correlation(
    df: pd.DataFrame, schema: dict[str, Any]
) -> list[dict[str, Any]]:
    roles = schema.get("roles", {})
    metric_cols = [str(c) for c, r in roles.items() if r == profiler2.ROLE_METRIC]
    if len(metric_cols) < 2:
        return []
    try:
        nums = pd.to_numeric(df[metric_cols].stack(), errors="coerce").unstack()
        corr = nums.corr()
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for a in corr.columns:
            for b in corr.columns:
                if a == b:
                    continue
                key = tuple(sorted((a, b)))
                if key in seen:
                    continue
                seen.add(key)
                v = corr.loc[a, b]
                if not math.isfinite(v):
                    continue
                if abs(v) >= _CORR_THRESHOLD:
                    pos = v > 0
                    severity = _SEVERITY_HIGH if abs(v) >= 0.9 else _SEVERITY_MEDIUM
                    out.append(
                        {
                            "kind": KIND_CORRELATION,
                            "title": f"{a} 与 {b} 高度{('正' if pos else '负')}相关",
                            "conclusion": (
                                f"{a} 与 {b} 的 Pearson 相关系数为 {v:.2f}，"
                                f"呈{('正相关：一者上升另一者通常同步上升' if pos else '负相关：一者上升另一者通常下降')}。"
                            ),
                            "metric": "",
                            "dimensions": [a, b],
                            "evidence": {
                                "claim": f"{a} 与 {b} 相关",
                                "result": f"Pearson r = {v:.2f}",
                                "confidence": round(min(0.95, abs(v)), 2),
                            },
                            "confidence": round(min(0.95, abs(v)), 2),
                            "severity": severity,
                            "sql": f"SELECT CORR({a}, {b}) FROM dataset",
                        }
                    )
        return out[:3]
    except Exception:  # noqa: BLE001
        return []


def _detect_quality(
    df: pd.DataFrame, base_profile: dict[str, Any]
) -> list[dict[str, Any]]:
    try:
        report = profiler2.quality_report(df, base_profile)
    except Exception:  # noqa: BLE001
        return []
    score = report.get("quality_score", 100)
    issues = report.get("issues", [])
    findings: list[dict[str, Any]] = []
    if score < 100:
        # Summarize into up to 2 issues.
        top = sorted(issues, key=lambda i: -i.get("severity", 0))[:2]
        for i in top:
            sev = i.get("severity", 0)
            severity = (
                _SEVERITY_HIGH if sev >= 3 else
                (_SEVERITY_MEDIUM if sev >= 2 else _SEVERITY_LOW)
            )
            findings.append(
                {
                    "kind": KIND_QUALITY,
                    "title": i.get("title") or "数据质量问题",
                    "conclusion": i.get("description") or i.get("title") or "存在数据质量问题。",
                    "metric": str(i.get("column") or ""),
                    "dimensions": [],
                    "evidence": {
                        "claim": i.get("title"),
                        "result": f"质量分 {score}/100，命中 {i.get('detail', '')}",
                        "confidence": 0.9,
                    },
                    "confidence": 0.9,
                    "severity": severity,
                    "sql": "",
                }
            )
    # Always emit a score headline unless it's a clean perfect dataset and no
    # other quality issue exists; keep output meaningful.
    if not findings:
        return []
    return findings


def run_insight_node(
    df: pd.DataFrame,
    schema: dict[str, Any],
    base_profile: dict[str, Any],
    max_insights: int = 12,
) -> list[dict[str, Any]]:
    """Run all six detectors and return the deduped, ranked insight dicts."""
    detectors = [
        _detect_trend,
        _detect_anomaly,
        _detect_shift,
        _detect_contribution,
        _detect_correlation,
        _detect_quality,
    ]
    results: list[dict[str, Any]] = []
    for detector in detectors:
        try:
            if detector is _detect_quality:
                results.extend(detector(df, base_profile))
            else:
                results.extend(detector(df, schema))
        except Exception:  # noqa: BLE001
            continue
    # Dedup by (kind, title).
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for r in results:
        key = (r["kind"], r["title"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    # Rank: high > medium > low, then confidence desc.
    order = {_SEVERITY_HIGH: 0, _SEVERITY_MEDIUM: 1, _SEVERITY_LOW: 2}
    deduped.sort(key=lambda r: (order.get(r.get("severity"), 3), -r.get("confidence", 0)))
    return deduped[:max_insights]
