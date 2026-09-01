from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any

from app.core.llm import ModelSize, get_llm_client
from app.core.config import settings

SYSTEM_PROMPT = (
    "你是一名资深数据分析报告撰写助手。请根据给定的分析结果，撰写一份"
    "面向业务决策者的中文结构化报告。\n"
    "只输出一个 JSON 对象，不要使用 markdown 代码块，不要输出任何解释性文字。"
    "JSON 结构必须如下：\n"
    "{\n"
    '  "executive_summary": "2-4 句话的高层总结，直接回答分析目标",\n'
    '  "key_findings": ["3-6 条关键发现，每条 1-2 句，具体且可量化"],\n'
    '  "recommendations": ["2-4 条可落地的行动建议"],\n'
    '  "limitations": "数据或方法的局限性；若无明显局限则为 null"\n'
    "}\n"
    "要求：结论必须基于给定数据，不得编造数字；不要重复 SQL 或原始数据表。"
)

JSON_FIX_USER = (
    "请将上面的分析内容整理为报告 JSON，仅输出 JSON 对象（不要代码块、不要解释）。"
)


def _extract_json(text: str | None) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from an LLM response."""
    if not text:
        return {}
    t = text.strip()
    if t.startswith("```"):
        # drop the opening fence line
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start : end + 1]
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _build_context(result: dict[str, Any], query: str, dataset_name: str) -> str:
    """Compact, grounded context string for the LLM (keeps tokens low)."""
    parts: list[str] = []
    parts.append(f"数据集：{dataset_name}")
    parts.append(f"分析目标：{query}")
    answer = result.get("answer") or ""
    if answer:
        parts.append(f"\n分析结论：\n{answer[:2000]}")

    review = result.get("review")
    if isinstance(review, dict):
        rtext = review.get("review") or review.get("comment") or ""
        if rtext:
            parts.append(f"\n复核意见：\n{rtext[:800]}")

    sql_results = result.get("sql_results") or []
    if sql_results:
        parts.append("\n数据查询结果：")
        for i, entry in enumerate(sql_results[:6], 1):
            sql = (entry.get("sql") or "").strip()
            res = entry.get("result") or {}
            cols = res.get("columns") or []
            rows = res.get("rows") or []
            parts.append(f"\n[{i}] SQL: {sql}")
            if cols:
                parts.append("字段: " + ", ".join(str(c) for c in cols))
            if rows:
                shown = rows[:5]
                parts.append(
                    "样例: "
                    + " | ".join(
                        " / ".join(str(v) for v in r)[:80] for r in shown
                    )
                )
                parts.append(f"共 {len(rows)} 行")

    return "\n".join(parts)


def _build_evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []

    sql_results = result.get("sql_results") or []
    for i, entry in enumerate(sql_results, 1):
        res = entry.get("result") or {}
        evidence.append(
            {
                "title": f"数据查询 {i}",
                "sql": (entry.get("sql") or "").strip() or None,
                "columns": res.get("columns") or [],
                "rows": res.get("rows") or [],
            }
        )

    python_results = result.get("python_results") or []
    for i, entry in enumerate(python_results, 1):
        out = entry.get("output")
        if isinstance(out, (dict, list)):
            out_text = json.dumps(out, ensure_ascii=False)[:2000]
        else:
            out_text = str(out or "")[:2000]
        evidence.append(
            {
                "title": f"Python 计算 {i}",
                "sql": (entry.get("code") or "").strip() or None,
                "columns": ["output"],
                "rows": [[out_text]],
            }
        )

    return evidence


def _build_metrics(
    run_summary: dict[str, Any] | None,
    analysis_prompt_tokens: int,
    analysis_completion_tokens: int,
) -> dict[str, Any]:
    if run_summary:
        pt = run_summary.get("prompt_tokens") or 0
        ct = run_summary.get("completion_tokens") or 0
        latency = run_summary.get("latency_ms") or 0
        tools = run_summary.get("tool_calls") or 0
        cost = run_summary.get("cost")
        if cost is None:
            cost = round(
                pt / 1000 * settings.trace_cost_per_1k_prompt
                + ct / 1000 * settings.trace_cost_per_1k_completion,
                6,
            )
    else:
        pt = analysis_prompt_tokens
        ct = analysis_completion_tokens
        latency = 0
        tools = 0
        cost = round(
            pt / 1000 * settings.trace_cost_per_1k_prompt
            + ct / 1000 * settings.trace_cost_per_1k_completion,
            6,
        )
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "latency_ms": latency,
        "tool_calls": tools,
        "cost": cost,
    }


async def generate_report(
    result: dict[str, Any],
    *,
    dataset_name: str,
    query: str,
    run_summary: dict[str, Any] | None = None,
    analysis_prompt_tokens: int = 0,
    analysis_completion_tokens: int = 0,
) -> dict[str, Any]:
    """Generate the structured report.

    The narrative (summary / findings / recommendations / limitations) is
    produced by an LLM; evidence and charts are assembled deterministically
    from the stored analysis so the report stays grounded in real data.
    Falls back to a deterministic report if the LLM is unavailable.
    """
    answer = result.get("answer") or ""
    charts = result.get("visualizations") or []
    evidence = _build_evidence(result)
    metrics = _build_metrics(run_summary, analysis_prompt_tokens, analysis_completion_tokens)

    narrative: dict[str, Any] = {}
    try:
        client = get_llm_client(ModelSize.large)
        ctx = _build_context(result, query, dataset_name)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": ctx + "\n\n" + JSON_FIX_USER},
        ]
        resp = await client.chat(messages=messages, temperature=0.2)
        narrative = _extract_json(resp.content)
    except Exception:
        # Deterministic fallback: use the stored answer as the summary.
        narrative = {}

    report: dict[str, Any] = {
        "query": query,
        "dataset_name": dataset_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "executive_summary": narrative.get("executive_summary") or answer,
        "key_findings": narrative.get("key_findings") or [],
        "evidence": evidence,
        "charts": charts,
        "recommendations": narrative.get("recommendations") or [],
        "limitations": narrative.get("limitations"),
        "metrics": metrics,
    }
    return report


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_CHART_JS = """
function toEchartsOption(spec){
  var type=spec.type, title=spec.title||"", xField=spec.xField, yField=spec.yField;
  var data=spec.data||[];
  var xf = Array.isArray(xField)?xField[0]:xField;
  var yf = Array.isArray(yField)?yField[0]:yField;
  var cats = data.map(function(d){return String(d[xf]!=null?d[xf]:"");
});
  var vals = data.map(function(d){return Number(d[yf]!=null?d[yf]:0);});
  if(type==="pie"){
    return {title:{text:title,left:"center"},tooltip:{trigger:"item"},
      series:[{type:"pie",radius:["35%","65%"],data:cats.map(function(c,i){return {name:c,value:vals[i]};})}]};
  }
  var st=(type==="line"||type==="area")?"line":(type==="scatter")?"scatter":"bar";
  var series={type:st,data:vals,itemStyle:{color:"#4f7cff"}};
  if(type==="area"){series.areaStyle={opacity:0.18};}
  return {title:{text:title,left:"center"},grid:{left:60,right:24,top:48,bottom:70},
    tooltip:{trigger:"axis"},
    xAxis:{type:"category",data:cats,axisLabel:{interval:0,rotate:cats.length>6?30:0}},
    yAxis:{type:"value"},series:[series]};
}
window.addEventListener("load",function(){
  if(typeof REPORT_CHARTS==="undefined"){return;}
  REPORT_CHARTS.forEach(function(spec,i){
    if(spec.renderer==="r3f"){return;}
    var el=document.getElementById("chart-"+i);
    if(!el){return;}
    try{
      var chart=echarts.init(el);
      chart.setOption(toEchartsOption(spec));
      window.addEventListener("resize",function(){chart.resize();});
    }catch(e){}
  });
});
"""

_CSS = """
:root{--bg:#f6f8fc;--card:#fff;--ink:#1f2733;--muted:#64748b;--line:#e6ebf2;--brand:#4f7cff;--accent:#0ea5a4;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.7;}
.page{max-width:920px;margin:0 auto;padding:40px 28px 64px;}
header.report-head{border-bottom:3px solid var(--brand);padding-bottom:18px;margin-bottom:28px;}
header.report-head h1{margin:0 0 6px;font-size:26px;}
.meta{color:var(--muted);font-size:13px;}
.meta span{margin-right:16px;}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-bottom:20px;box-shadow:0 1px 2px rgba(16,24,40,.04);}
section h2{margin:0 0 14px;font-size:18px;display:flex;align-items:center;gap:8px;}
section h2::before{content:"";width:4px;height:18px;background:var(--brand);border-radius:2px;display:inline-block;}
.summary{font-size:15px;}
ul.findings,ul.recs{margin:0;padding-left:0;list-style:none;}
ul.findings li,ul.recs li{position:relative;padding:10px 14px 10px 38px;margin-bottom:8px;background:#f8fafc;border:1px solid var(--line);border-radius:10px;}
ul.findings li::before{content:counter(f);counter-increment:f;position:absolute;left:12px;top:10px;width:18px;height:18px;background:var(--brand);color:#fff;border-radius:50%;font-size:12px;display:flex;align-items:center;justify-content:center;}
ul.findings{counter-reset:f;}
ul.recs li::before{content:"▸";position:absolute;left:14px;top:9px;color:var(--accent);font-weight:700;}
.evidence-block{border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px;}
.evidence-block h3{margin:0 0 8px;font-size:15px;color:var(--ink);}
pre.code{background:#0f172a;color:#e2e8f0;padding:12px 14px;border-radius:8px;overflow:auto;font-size:12.5px;white-space:pre-wrap;word-break:break-word;}
table{border-collapse:collapse;width:100%;margin-top:8px;font-size:13px;}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;}
th{background:#f1f5f9;}
.chart{width:100%;height:340px;margin-top:6px;}
.metrics{display:flex;flex-wrap:wrap;gap:14px;}
.metric{flex:1 1 140px;background:#f8fafc;border:1px solid var(--line);border-radius:10px;padding:12px 14px;}
.metric .v{font-size:20px;font-weight:700;color:var(--brand);}
.metric .k{font-size:12px;color:var(--muted);}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:24px;}
@media print{body{background:#fff;}section{box-shadow:none;break-inside:avoid;}}
"""


def render_html_report(report: dict[str, Any], dataset_name: str, query: str) -> str:
    esc = html.escape
    title = esc(dataset_name or "数据分析") + " · 分析报告"

    summary = esc(report.get("executive_summary") or "")
    findings = report.get("key_findings") or []
    recs = report.get("recommendations") or []
    limitations = report.get("limitations")
    evidence = report.get("evidence") or []
    charts = report.get("charts") or []
    metrics = report.get("metrics") or {}

    findings_html = (
        "<ul class='findings'>"
        + "".join(f"<li>{esc(f)}</li>" for f in findings)
        + "</ul>"
        if findings
        else "<p class='summary'>（暂无）</p>"
    )
    recs_html = (
        "<ul class='recs'>"
        + "".join(f"<li>{esc(r)}</li>" for r in recs)
        + "</ul>"
        if recs
        else "<p class='summary'>（暂无）</p>"
    )

    # charts: render container divs (echarts) or a table fallback for r3f.
    # Agent2UI: ArtifactSpec（含 code）优先渲染 P2 截图服务生成的 PNG 快照，
    # 没有快照时回退到占位（交互渲染请查看分析页）。
    chart_blocks: list[str] = []
    non_r3f: list[dict[str, Any]] = []
    idx = 0
    for spec in charts:
        if spec.get("code"):
            snap = spec.get("_snapshot")
            if snap:
                chart_blocks.append(
                    f"<div class='evidence-block'><h3>{esc(spec.get('title','AI 图表'))}</h3>"
                    f"<img src='{snap}' alt='{esc(spec.get('title','AI 图表'))}' "
                    "style='max-width:100%;height:auto;border-radius:10px;border:1px solid var(--line);'/>"
                    "</div>"
                )
            else:
                chart_blocks.append(
                    f"<div class='evidence-block'><h3>{esc(spec.get('title','AI 图表'))}</h3>"
                    "<p class='summary'>AI 生成的可交互图表（TSX），静态导出中暂以占位呈现；"
                    "完整交互渲染请查看分析页。</p></div>"
                )
            continue
        if spec.get("renderer") == "r3f":
            cols = spec.get("columns") or []
            rows = spec.get("rows") or []
            tbl = "<table><thead><tr>" + "".join(
                f"<th>{esc(c)}</th>" for c in cols
            ) + "</tr></thead><tbody>" + "".join(
                "<tr>" + "".join(f"<td>{esc(str(v))}</td>" for v in r) + "</tr>" for r in rows[:50]
            ) + "</tbody></table>"
            chart_blocks.append(
                f"<div class='evidence-block'><h3>{esc(spec.get('title','3D 图表'))}</h3>"
                f"<p class='summary'>三维可视化，导出中以数据表呈现。</p>{tbl}</div>"
            )
        else:
            chart_blocks.append(
                f"<div class='evidence-block'><div id='chart-{idx}' class='chart'></div></div>"
            )
            non_r3f.append(spec)
            idx += 1
    charts_html = "\n".join(chart_blocks) if chart_blocks else "<p class='summary'>（本次分析未生成图表）</p>"

    # evidence blocks
    ev_blocks: list[str] = []
    for ev in evidence:
        inner = f"<h3>{esc(ev.get('title',''))}</h3>"
        sql = ev.get("sql")
        if sql:
            inner += f"<pre class='code'>{esc(sql)}</pre>"
        cols = ev.get("columns") or []
        rows = ev.get("rows") or []
        if cols and rows:
            head = "<tr>" + "".join(f"<th>{esc(c)}</th>" for c in cols) + "</tr>"
            body = "".join(
                "<tr>" + "".join(f"<td>{esc(str(v))}</td>" for v in r) + "</tr>"
                for r in rows[:50]
            )
            inner += f"<table><thead>{head}</thead><tbody>{body}</tbody></table>"
        elif rows and not cols:
            inner += f"<pre class='code'>{esc(rows[0][0] if rows and rows[0] else '')}</pre>"
        ev_blocks.append(f"<div class='evidence-block'>{inner}</div>")
    evidence_html = "\n".join(ev_blocks) if ev_blocks else "<p class='summary'>（无数据查询记录）</p>"

    limits_html = (
        f"<p class='summary'>{esc(limitations)}</p>" if limitations else ""
    )

    m = metrics
    metrics_html = (
        "<div class='metrics'>"
        f"<div class='metric'><div class='v'>{m.get('prompt_tokens',0)}</div><div class='k'>Prompt Tokens</div></div>"
        f"<div class='metric'><div class='v'>{m.get('completion_tokens',0)}</div><div class='k'>Completion Tokens</div></div>"
        f"<div class='metric'><div class='v'>{m.get('tool_calls',0)}</div><div class='k'>工具调用</div></div>"
        f"<div class='metric'><div class='v'>{(m.get('latency_ms',0) or 0)/1000:.1f}s</div><div class='k'>耗时</div></div>"
        f"<div class='metric'><div class='v'>${float(m.get('cost',0) or 0):.4f}</div><div class='k'>预估成本</div></div>"
        "</div>"
    )

    gen_at = report.get("generated_at") or ""
    charts_json = json.dumps(non_r3f, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <header class="report-head">
    <h1>{title}</h1>
    <div class="meta">
      <span>数据集：{esc(dataset_name or '-')}</span>
      <span>分析目标：{esc(query or '-')}</span>
      <span>生成时间：{esc(gen_at)}</span>
    </div>
  </header>

  <section>
    <h2>执行摘要</h2>
    <p class="summary">{summary}</p>
  </section>

  <section>
    <h2>关键发现</h2>
    {findings_html}
  </section>

  <section>
    <h2>可视化图表</h2>
    {charts_html}
  </section>

  <section>
    <h2>数据证据</h2>
    {evidence_html}
  </section>

  <section>
    <h2>行动建议</h2>
    {recs_html}
  </section>

  {('<section><h2>局限与说明</h2>' + limits_html + '</section>') if limits_html else ''}

  <section>
    <h2>运行指标</h2>
    {metrics_html}
  </section>

  <footer>由 InsightFlow AI 数据分析平台生成</footer>
</div>
<script>var REPORT_CHARTS = {charts_json};</script>
<script>{_CHART_JS}</script>
</body>
</html>"""
