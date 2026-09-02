"""Evidence-driven report export (2.0).

Turns a completed analysis into a professional, standalone deliverable that
goes beyond the plain narrative report by folding in the *differentiating*
2.0 components:

- Root-cause analysis (RootCause model): contribution decomposition, factors,
  conclusion & confidence.
- Full persisted evidence chain (evidences table): multi-hop DAG with per-node
  claims, metrics, confidence and SQL.
- Evaluation 2.0 replay (eval_replay.evaluate_analysis): deterministic,
  confidence-gated assertion of whether each conclusion is actually supported
  by evidence.

Two renderers are provided:

- ``render_markdown_export`` -> portable Markdown (works everywhere, easy to
  paste into Notion / Word / Obsidian).
- ``render_html_export`` -> a print-ready standalone HTML (browser print -> PDF).
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.root_cause import RootCause
from app.services.md import codehilite_css, highlight_code, md_to_html


# ---------------------------------------------------------------------------
# Data aggregation
# ---------------------------------------------------------------------------


async def load_root_cause(
    session: AsyncSession, analysis_id: str
) -> dict[str, Any] | None:
    """Return the persisted root-cause analysis for an analysis, or None."""
    row = (
        await session.execute(
            select(RootCause).where(RootCause.analysis_id == analysis_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    def _parse(raw: str, default: Any) -> Any:
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return default

    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "question": row.question,
        "change": _parse(row.change, {}),
        "contributions": _parse(row.contributions, []),
        "factors": _parse(row.factors, []),
        "hypotheses": _parse(row.hypotheses, []),
        "conclusion": row.conclusion,
        "confidence": row.confidence,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def load_eval_report(
    session: AsyncSession, analysis_id: str
) -> dict[str, Any] | None:
    """Replay the deterministic evaluation (Evaluation 2.0) for an analysis.

    Returns None when the analysis has no persisted evidence (nothing to
    replay), so the report can gracefully omit the section.
    """
    from app.services.eval_replay import evaluate_analysis

    try:
        result = await evaluate_analysis(session, analysis_id)
    except Exception:  # noqa: BLE001 - never block the export on eval failure
        return None
    if not result or result.get("error") or not result.get("evidence_count"):
        return None
    return result


async def build_export_data(
    session: AsyncSession,
    analysis_id: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the full evidence-driven export payload.

    ``report`` is the persisted report dict (report.content_json). We layer the
    2.0 components on top of it.
    """
    from app.services.evidence import load_evidence_graph, load_evidences

    data: dict[str, Any] = {
        "query": report.get("query") or "",
        "dataset_name": report.get("dataset_name") or "",
        "generated_at": report.get("generated_at") or "",
        "executive_summary": report.get("executive_summary") or "",
        "key_findings": report.get("key_findings") or [],
        "recommendations": report.get("recommendations") or [],
        "limitations": report.get("limitations"),
        "charts": report.get("charts") or [],
        "evidence": report.get("evidence") or [],
        "metrics": report.get("metrics") or {},
    }

    data["root_cause"] = await load_root_cause(session, analysis_id)
    data["evidence_graph"] = await load_evidence_graph(
        session, analysis_id=analysis_id
    )
    data["evidences"] = await load_evidences(session, analysis_id=analysis_id)
    data["eval"] = await load_eval_report(session, analysis_id)
    return data


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _fmt_pct(x: float | None) -> str:
    try:
        return f"{float(x or 0) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_number(x: Any) -> str:
    try:
        return f"{float(x):,}"
    except (TypeError, ValueError):
        return str(x or "-")


def _confidence_badge(conf: float | None) -> str:
    try:
        c = float(conf or 0)
    except (TypeError, ValueError):
        c = 0.0
    if c >= 0.9:
        return "高"
    if c >= 0.7:
        return "中"
    return "低"


def render_markdown_export(data: dict[str, Any]) -> str:
    """Render the full evidence-driven report as professional Markdown."""
    L: list[str] = []
    add = L.append

    title = data.get("dataset_name") or "数据分析"
    add(f"# {title} · 分析报告\n")

    meta: list[str] = []
    if data.get("query"):
        meta.append(f"- **分析目标**：{data['query']}")
    if data.get("generated_at"):
        meta.append(f"- **生成时间**：{data['generated_at']}")
    if meta:
        add("\n".join(meta))
        add("")

    # Executive summary
    add("## 执行摘要\n")
    add((data.get("executive_summary") or "").strip() or "（无）")
    add("")

    # Root cause (2.0 differentiator)
    rc = data.get("root_cause")
    if rc:
        add("## 根因分析\n")
        change = rc.get("change") or {}
        if change:
            delta = change.get("delta")
            metric = change.get("metric") or ""
            sign = "+" if isinstance(delta, (int, float)) and delta >= 0 else ""
            add(
                f"- **关注指标**：{metric}（变化 {sign}{_fmt_number(delta)}，"
                f"基期 {_fmt_number(change.get('base_value'))} → 当期 {_fmt_number(change.get('current_value'))}）"
            )
            if change.get("significant") is not None:
                add(f"- **显著性**：{'显著' if change.get('significant') else '不显著'}")
            if change.get("reason"):
                add(f"- **变化说明**：{change['reason']}")
        add("")
        factors = rc.get("factors") or []
        if factors:
            add("**主要影响因素**：")
            for i, f in enumerate(factors, 1):
                add(f"{i}. {f}")
            add("")
        contributions = rc.get("contributions") or []
        if contributions:
            add("**贡献分解**：")
            for c in contributions:
                factor = c.get("factor") or ""
                pct = _fmt_pct(c.get("contribution_pct"))
                metric = c.get("metric") or ""
                line = f"- {factor}：贡献 {pct}"
                if metric:
                    line += f"（{metric}）"
                add(line)
            add("")
        if rc.get("hypotheses"):
            add("**假设验证**：")
            for h in rc.get("hypotheses") or []:
                status = h.get("status") or ""
                mark = "✅" if status == "confirmed" else "❌" if status in ("rejected", "refuted") else "🔸"
                add(f"- {mark} {h.get('hypothesis')}（{status}）")
            add("")
        if rc.get("conclusion"):
            add(f"**结论**：{rc['conclusion']}\n")
        conf = rc.get("confidence")
        if conf is not None:
            add(f"**根因置信度**：{_fmt_pct(conf)}（{_confidence_badge(conf)}）\n")

    # Key findings
    findings = data.get("key_findings") or []
    add("## 关键发现\n")
    if findings:
        for f in findings:
            add(f"- {f}")
    else:
        add("（无）")
    add("")

    # Evidence chain (2.0 differentiator)
    evidences = data.get("evidences") or []
    if evidences:
        add("## 证据链\n")
        add(
            "> 以下证据从持久化 evidences 表提取，按推理层级排列；每条包含声明、"
            "指标、置信度及支撑 SQL。\n"
        )
        # group by level using the graph (node.level) if available
        nodes = (data.get("evidence_graph") or {}).get("nodes") or []
        if nodes:
            by_id = {n["id"]: n for n in nodes}
        else:
            by_id = {}
        for ev in evidences:
            level = by_id.get(ev.get("id"), {}).get("level", 0)
            claim = (ev.get("claim") or "").strip()
            metric = ev.get("metric") or ""
            conf = ev.get("confidence")
            source = ev.get("source") or ""
            sql = (ev.get("sql") or "").strip()
            badge = _confidence_badge(conf) if conf is not None else ""
            add(f"### L{level} · {claim}")
            add("")
            bits: list[str] = []
            if metric:
                bits.append(f"指标：`{metric}`")
            if conf is not None:
                bits.append(f"置信度：{_fmt_pct(conf)}（{badge}）")
            if source:
                bits.append(f"来源：`{source}`")
            if bits:
                add("- " + " | ".join(bits))
            if sql:
                add("")
                add("```sql")
                add(sql)
                add("```")
            add("")
    else:
        add("## 证据链\n")
        add("（本次分析未持久化证据，请先运行分析后再导出。）\n")

    # Charts
    charts = data.get("charts") or []
    if charts:
        add("## 可视化图表\n")
        for i, spec in enumerate(charts, 1):
            st = spec.get("type") or ""
            t = spec.get("title") or f"图表 {i}"
            snap = spec.get("_snapshot")
            if snap:
                add(f"### {t}\n![]({snap})\n")
                continue
            rows = spec.get("rows") or []
            if rows:
                add(f"### {t}（{st}，{len(rows)} 条）")
                cols = spec.get("columns") or (list(rows[0].keys()) if isinstance(rows[0], dict) else [])
                if cols:
                    add("| " + " | ".join(str(c) for c in cols) + " |")
                    add("|" + "---|" * len(cols))
                    for r in rows[:30]:
                        if isinstance(r, dict):
                            add("| " + " | ".join(_fmt_number(r.get(c)) if isinstance(r.get(c), (int, float)) else str(r.get(c, "")) for c in cols) + " |")
                        else:
                            add("| " + " | ".join(str(v) for v in r) + " |")
                    add("")
            else:
                add(f"### {t}（{st}）\n")
    else:
        add("## 可视化图表\n（本次分析未生成图表）\n")

    # Evaluation 2.0 (differentiator)
    evalr = data.get("eval")
    if evalr:
        add("## 证据链评估（Evaluation 2.0）\n")
        verdict = evalr.get("verdict") or ""
        verdict_label = {"pass": "通过", "warn": "需关注", "fail": "未通过"}.get(verdict, verdict)
        mark = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(verdict, "")
        add(
            f"**结论**：{mark} 整体评估 **{verdict_label}**"
            f"（证据数 {evalr.get('evidence_count') or 0}，"
            f"规则通过 {'是' if evalr.get('rules_passed') else '否'}）"
        )
        add("")
        checks = evalr.get("checks") or []
        if checks:
            add("**硬规则回放**：")
            for c in checks:
                passed = "✅" if c.get("passed") else "❌"
                detail = c.get("detail") or ""
                add(f"- {passed} {c.get('name') or c.get('rule') or '规则'}")
                if detail and not c.get("passed"):
                    add(f"  - {detail}")
            add("")
        conf_gate = evalr.get("confidence_gate") or {}
        if conf_gate:
            add(
                f"**置信度门控**：{_fmt_pct(conf_gate.get('mean_confidence'))}"
                f"（{'通过' if conf_gate.get('passed') else '未通过'}，阈值 {_fmt_pct(evalr.get('min_confidence'))}）"
            )
            add("")
        cov = evalr.get("coverage") or {}
        if cov:
            add(
                f"**结论覆盖率**：{_fmt_pct(cov.get('coverage'))}"
                f"（{cov.get('covered') or 0}/{cov.get('total') or 0} 条结论被证据覆盖）"
            )
            add("")
    else:
        add("## 证据链评估（Evaluation 2.0）\n（无持久化证据，跳过评估。）\n")

    # Recommendations
    recs = data.get("recommendations") or []
    add("## 行动建议\n")
    if recs:
        for r in recs:
            add(f"- {r}")
    else:
        add("（无）")
    add("")

    # Limitations
    limits = data.get("limitations")
    if limits:
        add("## 局限与说明\n")
        add(str(limits))
        add("")

    # Metrics
    m = data.get("metrics") or {}
    if m:
        add("## 运行指标\n")
        add(
            f"- Prompt Tokens：{m.get('prompt_tokens', 0)}"
            f"\n- Completion Tokens：{m.get('completion_tokens', 0)}"
            f"\n- 工具调用：{m.get('tool_calls', 0)}"
            f"\n- 耗时：{(m.get('latency_ms') or 0) / 1000:.1f}s"
            f"\n- 预估成本：${float(m.get('cost', 0) or 0):.4f}"
        )
        add("")

    add("---")
    add("*由 InsightFlow AI 数据分析平台生成 · 证据驱动报告*")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# HTML rendering (print-ready, browser -> PDF)
# ---------------------------------------------------------------------------

_EXTRA_CSS = """
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;}
.badge-high{background:#ecfdf5;color:#059669;border:1px solid #a7f3d0;}
.badge-mid{background:#fffbeb;color:#d97706;border:1px solid #fde68a;}
.badge-low{background:#fef2f2;color:#dc2626;border:1px solid #fecaca;}
.verdict{display:inline-block;padding:2px 12px;border-radius:12px;font-weight:700;color:#fff;}
.verdict-pass{background:#10b981;}
.verdict-warn{background:#f59e0b;}
.verdict-fail{background:#ef4444;}
.evchain{padding-left:18px;border-left:2px solid var(--line);}
.evchain .evnode{margin-bottom:12px;}
.evchain .evlvl{color:var(--accent);font-weight:700;font-size:12px;}
.evchain pre{margin-top:6px;}
.evclaim .md p{display:inline;margin:0;}
.evclaim .md{display:inline;}
ul.checks{list-style:none;padding:0;margin:0;}
ul.checks li{padding:6px 10px;background:#f8fafc;border:1px solid var(--line);border-radius:8px;margin-bottom:6px;font-size:13px;}
table.evtable td,table.evtable th{font-size:12px;}
"""


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def render_html_export(data: dict[str, Any]) -> str:
    """Render the full evidence-driven report as a print-ready HTML document."""
    from app.services.report import _CSS

    esc = html.escape
    title = esc(data.get("dataset_name") or "数据分析") + " · 证据驱动分析报告"

    # ---- Root cause section ----
    rc = data.get("root_cause")
    rc_html = ""
    if rc:
        parts: list[str] = []
        change = rc.get("change") or {}
        if change:
            delta = change.get("delta")
            sign = "+" if isinstance(delta, (int, float)) and delta >= 0 else ""
            parts.append(
                f"<p class='summary'>关注指标：<b>{esc(change.get('metric'))}</b>"
                f"（变化 {sign}{_fmt_number(delta)}，基期 {_fmt_number(change.get('base_value'))}"
                f" → 当期 {_fmt_number(change.get('current_value'))}）</p>"
            )
        factors = rc.get("factors") or []
        if factors:
            parts.append(
                "<p class='summary'><b>主要影响因素：</b>"
                + "；".join(f"{i+1}. {esc(f)}" for i, f in enumerate(factors))
                + "</p>"
            )
        contributions = rc.get("contributions") or []
        if contributions:
            rows = "".join(
                "<tr>"
                f"<td>{esc(c.get('factor'))}</td>"
                f"<td>{_fmt_pct(c.get('contribution_pct'))}</td>"
                f"<td>{esc(c.get('metric') or '-')}</td>"
                "</tr>"
                for c in contributions
            )
            parts.append(
                "<table><thead><tr><th>因素</th><th>贡献占比</th><th>指标</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>"
            )
        if rc.get("conclusion"):
            parts.append(f"<div class='summary'><b>结论：</b>{md_to_html(rc['conclusion'])}</div>")
        if rc.get("confidence") is not None:
            conf = rc.get("confidence")
            badge_cls = "badge-high" if conf >= 0.9 else "badge-mid" if conf >= 0.7 else "badge-low"
            parts.append(
                f"<p class='summary'>根因置信度：<b>{_fmt_pct(conf)}</b>"
                f" <span class='badge {badge_cls}'>{_confidence_badge(conf)}</span></p>"
            )
        rc_html = (
            "<section><h2>根因分析</h2>" + "".join(parts) + "</section>"
        )

    # ---- Evidence chain section ----
    evidences = data.get("evidences") or []
    nodes = (data.get("evidence_graph") or {}).get("nodes") or []
    by_id = {n["id"]: n for n in nodes}
    if evidences:
        ev_items: list[str] = []
        for ev in evidences:
            level = by_id.get(ev.get("id"), {}).get("level", 0)
            claim = (ev.get("claim") or "").strip()
            conf = ev.get("confidence")
            badge = ""
            if conf is not None:
                cls = "badge-high" if conf >= 0.9 else "badge-mid" if conf >= 0.7 else "badge-low"
                badge = f" <span class='badge {cls}'>{_confidence_badge(conf)} {_fmt_pct(conf)}</span>"
            metric = ev.get("metric") or ""
            metric_html = f"<span>指标：<code>{esc(metric)}</code></span>" if metric else ""
            sql = (ev.get("sql") or "").strip()
            sql_html = highlight_code(sql, "sql") if sql else ""
            # result rows (small sample)
            res = ev.get("result") or {}
            tbl = ""
            if res.get("rows"):
                cols = res.get("columns") or []
                head = "<tr>" + "".join(f"<th>{esc(str(c))}</th>" for c in cols) + "</tr>"
                body = "".join(
                    "<tr>" + "".join(f"<td>{_esc(v)}</td>" for v in r) + "</tr>"
                    for r in res["rows"][:20]
                )
                tbl = f"<table class='evtable'><thead>{head}</thead><tbody>{body}</tbody></table>"
            ev_items.append(
                f"<div class='evnode'>"
                f"<span class='evlvl'>L{level}</span> "
                f"<div class='evclaim'>{md_to_html(claim)}</div>{badge}"
                f"<div>{metric_html}</div>"
                f"{sql_html}{tbl}"
                f"</div>"
            )
        ev_html = (
            "<section><h2>证据链</h2>"
            "<p class='summary'>以下证据来自持久化 evidences 表，按推理层级排列，"
            "每条含声明、置信度与支撑 SQL。</p>"
            f"<div class='evchain'>{''.join(ev_items)}</div></section>"
        )
    else:
        ev_html = "<section><h2>证据链</h2><p class='summary'>（本次分析未持久化证据）</p></section>"

    # ---- Evaluation 2.0 section ----
    eval_html = ""
    evalr = data.get("eval")
    if evalr:
        verdict = evalr.get("verdict") or ""
        vlabel = {"pass": "通过", "warn": "需关注", "fail": "未通过"}.get(verdict, verdict)
        vcls = f"verdict-{verdict}"
        checks_rows = ""
        for c in evalr.get("checks") or []:
            mk = "✅" if c.get("passed") else "❌"
            detail = c.get("detail") or ""
            detail_html = f"<div style='color:var(--muted);font-size:12px'>{md_to_html(detail)}</div>" if detail and not c.get("passed") else ""
            checks_rows += f"<li>{mk} {esc(c.get('name') or c.get('rule') or '规则')}{detail_html}</li>"
        conf_gate = evalr.get("confidence_gate") or {}
        cov = evalr.get("coverage") or {}
        eval_html = (
            "<section><h2>证据链评估（Evaluation 2.0）</h2>"
            f"<p class='summary'>整体评估：<span class='verdict {vcls}'>{vlabel}</span>"
            f"（证据数 {evalr.get('evidence_count') or 0}，规则通过 {'是' if evalr.get('rules_passed') else '否'}）</p>"
            "<p class='summary'><b>硬规则回放：</b></p>"
            f"<ul class='checks'>{checks_rows}</ul>"
            f"<p class='summary'>置信度门控：<b>{_fmt_pct(conf_gate.get('mean_confidence'))}</b>"
            f"（{'通过' if conf_gate.get('passed') else '未通过'}，阈值 {_fmt_pct(evalr.get('min_confidence'))}）</p>"
            f"<p class='summary'>结论覆盖率：<b>{_fmt_pct(cov.get('coverage'))}</b>"
            f"（{cov.get('covered') or 0}/{cov.get('total') or 0} 条结论被证据覆盖）</p>"
            "</section>"
        )

    # ---- Reuse existing narrative / evidence / chart rendering ----
    from app.services.report import render_html_report

    base = render_html_report(
        {
            "dataset_name": data.get("dataset_name") or "",
            "query": data.get("query") or "",
            "generated_at": data.get("generated_at") or "",
            "executive_summary": data.get("executive_summary") or "",
            "key_findings": data.get("key_findings") or [],
            "recommendations": data.get("recommendations") or [],
            "limitations": data.get("limitations"),
            "charts": data.get("charts") or [],
            "evidence": data.get("evidence") or [],
            "metrics": data.get("metrics") or {},
        },
        data.get("dataset_name") or "",
        data.get("query") or "",
    )

    # Inject the extra sections + CSS into the base HTML document.
    base = base.replace("<style>{_CSS}</style>", f"<style>{_CSS}</style>", 1)  # no-op
    # Add extra CSS right after the base <style> block.
    marker_css = "<style>"
    insert_css = f"<style>{_EXTRA_CSS}\n{codehilite_css()}</style>"
    base = base.replace(marker_css, marker_css, 1).replace("</head>", insert_css + "</head>", 1)

    # Insert root-cause / evidence-chain / eval sections after the executive
    # summary section and before the charts section.
    chart_marker = "  <section>\n    <h2>可视化图表</h2>"
    insert_sections = rc_html + "\n\n" + ev_html + "\n\n" + eval_html
    base = base.replace(chart_marker, insert_sections + "\n\n" + chart_marker, 1)

    # Update the title.
    base = base.replace(
        esc(data.get("dataset_name") or "数据分析") + " · 分析报告",
        title,
        1,
    )
    return base
