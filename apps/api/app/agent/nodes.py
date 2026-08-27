"""LangGraph node implementations (Phase 3 / 6).

Each node is an ``async`` function returning a state delta. Nodes that produce
fine-grained streaming events append them to ``events`` (an ``operator.add``
field). Every event carries a ``ts`` (milliseconds, monotonic) so the Trace
layer can compute per-step / per-tool latency.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import math
from time import perf_counter
from typing import Any

from app.agent.state import AgentState
from app.agent.tools import SQL_TOOL_SPEC, run_sql_tool
from app.agent.tools.python_tool import (
    PYTHON_TOOL_SPEC,
    python_sandbox_isolated,
    run_python_tool,
)
from app.core.config import settings
from app.core.llm import ModelSize, get_llm_client
from app.core.llm.base import LLMMessage, ToolCall


# Live streaming side-channel. run_analysis() sets this contextvar to an
# asyncio.Queue before running the graph; every emitted event is pushed there
# so the SSE handler can yield it as soon as a node produces it (true
# streaming) instead of buffering all events until the graph finishes.
_STREAM_QUEUE: contextvars.ContextVar["asyncio.Queue | None"] = contextvars.ContextVar(
    "stream_queue", default=None
)


def _ev(type_: str, **kw: Any) -> dict[str, Any]:
    """Build a streaming event with a monotonic timestamp (ms).

    The event is also pushed to the live queue (if one is active) so the SSE
    endpoint can emit it immediately.
    """
    kw["type"] = type_
    kw["ts"] = round(perf_counter() * 1000)
    q = _STREAM_QUEUE.get()
    if q is not None:
        q.put_nowait(kw)
    return kw


def _msg_to_dict(m: LLMMessage) -> dict[str, Any]:
    """Serialize an LLMMessage to a JSON-friendly dict for checkpointing."""
    d: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.name is not None:
        d["name"] = m.name
    if m.tool_call_id is not None:
        d["tool_call_id"] = m.tool_call_id
    if m.tool_calls:
        d["tool_calls"] = [
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in m.tool_calls
        ]
    return d


def _msg_from_dict(d: dict[str, Any]) -> LLMMessage:
    """Rebuild an LLMMessage from a checkpointed dict (ReAct inner-loop resume)."""
    tcs = d.get("tool_calls")
    return LLMMessage(
        role=d["role"],
        content=d.get("content"),
        name=d.get("name"),
        tool_call_id=d.get("tool_call_id"),
        tool_calls=(
            [ToolCall(id=t["id"], name=t["name"], arguments=t["arguments"]) for t in tcs]
            if tcs
            else None
        ),
    )


PLANNER_SYSTEM = """你是一名数据分析规划师。把用户的问题拆成 2-4 个清晰的子任务 \
（例如：数据概览、地区对比、时间趋势、相关性）。只返回简洁的步骤列表，每行一个步骤。"""

ANALYSIS_SYSTEM = """你是一名严谨的数据分析助手。你可以通过两种工具分析「可用数据表」（可能包含多个表，多表可用表名 JOIN 关联后再计算）：
- sql_execute：用 DuckDB 执行只读 SQL（聚合/分组/排序优先，避免 SELECT * 返回过多行）。
- python_execute：用 pandas 做 SQL 不易表达的统计或变换（相关、回归、复杂分组等），读取 DATA_PATH。
规则：
1. 只能写只读 SQL（SELECT/WITH/SHOW/DESCRIBE/EXPLAIN）。
2. 优先用 SQL 做大表聚合；只有 SQL 明显不便时才用 Python。
3. 每次只调用一个工具；基于上一轮结果决定下一步。
4. 拿到足够证据后，用中文给出最终结论，引用关键数字与所用 SQL/Python。
5. 如果数据无法回答问题，如实说明并解释原因。
6. 你可能会收到「审查未通过」的反馈消息——此时上下文里已有你之前的工具结果与证据，\
请基于它们做针对性修正（优先修正结论或补充缺失的查询，不要重复执行已成功的查询），\
然后重新给出结论，而不是从头再来一遍。
7. 列作用域（极易出错，务必遵守）：外层查询只能引用其 FROM 子句中**真正存在的列**。
   - 用子查询或 CTE 时，内层聚合/计算后只暴露你在内层 SELECT 列表里写出的列名；
     被聚合掉的原列（如内层写了 `AVG(评分) AS avg_rating`，则外层只有 `avg_rating`，没有 `评分`）
     **在外层不可见**，外层要先引用 `avg_rating` 再聚合（如 `AVG(avg_rating)`），不能直接 `AVG(评分)`。
   - GROUP BY 后，SELECT 中只能出现分组列或被聚合的列，不能出现既非分组又非聚合的列。
   - 若 SQL 报错 `Referenced column "X" not found`，说明 X 不在当前可见列里：
     先核对内层 SELECT 到底输出了哪些列名，用那些名字重写外层，不要臆想原列。"""

VIZ_SYSTEM = """你是可视化专家。根据分析结果选择最合适的图表类型与坐标轴字段，调用 generate_chart 工具。
- 2D（echarts）优先用柱状图/折线图展示对比与趋势，用饼图展示占比。
- 当结果至少包含 3 个数值列、且问题适合空间关系时，可选用 3D 图表：3d_scatter（三点分布）或 3d_bar（三维柱）。
- x/y 字段（3D 还需 z_field）必须来自真实返回的列名，不要臆造数据（data 由系统自动填充）。"""

REVIEWER_SYSTEM = """你是分析审查员。判断最终结论是否有前面的 SQL/Python 结果作为证据支持，\
结论与证据是否一致。请重点核对：结论中引用的关键数字（金额、计数、均值、占比、排名等）\
是否能在证据里找到对应的值；若结论声称了证据中不存在的趋势或对比，应标记未通过。\
若明显缺乏证据、自相矛盾，或结论中的数字与证据不符，标记未通过并简短说明原因；否则标记通过。"""

GENERATE_CHART_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "generate_chart",
        "description": "为分析结果生成图表规格（data 由系统填充，只需给出类型与轴字段）。2D 用 echarts，前缀 3d_ 为三维图表用 react-three-fiber 渲染。",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": [
                        "bar",
                        "line",
                        "pie",
                        "scatter",
                        "histogram",
                        "area",
                        "3d_scatter",
                        "3d_bar",
                    ],
                    "description": "图表类型；3d_scatter/3d_bar 为三维图表",
                },
                "title": {"type": "string", "description": "图表标题"},
                "x_field": {"type": "string", "description": "横轴字段（来自真实列名）"},
                "y_field": {"type": "string", "description": "纵轴字段（来自真实列名）"},
                "z_field": {
                    "type": "string",
                    "description": "三维图表可选：第三维字段（来自真实数值列）",
                },
            },
            "required": ["type", "x_field", "y_field"],
            "additionalProperties": False,
        },
    },
}

REVIEW_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "review_decision",
        "description": "给出审查结论。",
        "parameters": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean", "description": "结论是否有证据支持"},
                "comment": {"type": "string", "description": "审查说明或未通过原因"},
            },
            "required": ["passed"],
            "additionalProperties": False,
        },
    },
}


def _summarize_sql(out: dict[str, Any]) -> str:
    if "error" in out:
        err = out["error"]
        hint = ""
        if "not found" in err and "Referenced column" in err:
            hint = (
                "\n修正提示：报错的列不在当前可见列中。若用了子查询/CTE，外层只能引用内层"
                "SELECT 列表里写出的列名（被聚合掉的原列如 评分 已不可见，应改用其别名如 avg_rating）。"
                "请先确认内层到底输出了哪些列，再用那些名字重写外层。"
            )
        return f"SQL 执行出错: {err}{hint}"
    cols = out.get("columns", [])
    rows = out.get("rows", [])
    rc = out.get("row_count", len(rows))
    note = f"(共 {rc} 行{'，已截断' if out.get('truncated') else ''})"
    preview = "\n".join(" | ".join(str(v) for v in row) for row in rows[:10])
    return f"列: {cols}\n{note}\n示例:\n{preview}"


def _summarize_python(out: dict[str, Any]) -> str:
    if out.get("error"):
        return f"Python 出错: {out['error']}"
    return f"Python 结果: {json.dumps(out, ensure_ascii=False)[:800]}"


def _frame_of(out: dict[str, Any] | None) -> tuple[list, list] | None:
    """Extract a (columns, rows) chartable frame from a tool result, else None.

    Handles both SQL results and Python ``submit({columns, rows})`` outputs.
    Results shaped as ``{summary: {...}}`` (no columns/rows) are not chartable
    and return None, so the visualizer won't emit meaningless charts.
    """
    if not out or "error" in out:
        return None
    cols = out.get("columns")
    rows = out.get("rows")
    if not isinstance(cols, list) or not isinstance(rows, list):
        return None
    if len(cols) == 0 or len(rows) == 0:
        return None
    return cols, rows


def _score_frame(cols: list, rows: list) -> float:
    """Higher = better chart candidate. Rewards 2-3 columns, a numeric axis,
    and a moderate (not trivial, not huge) row count."""
    rc = len(rows)
    n = len(cols)
    if rc < 2 or n < 1:
        return -1.0
    score = 0.0
    if n >= 2:
        score += 2.0
    if n >= 3:
        score += 1.0  # more dimensions → richer chart
    sample = rows[:20]

    def _is_num(v: Any) -> bool:
        if v is None or v == "":
            return False
        try:
            return not math.isnan(float(v))
        except (TypeError, ValueError):
            return False

    numeric = [i for i in range(n) if all(_is_num(r[i]) for r in sample if i < len(r))]
    if numeric:
        score += 1.0
    if rc <= settings.max_chart_rows:
        score += 1.0
    # prefer a bit more data, but cap the bonus
    score += min(rc, settings.max_chart_rows) / settings.max_chart_rows
    return score


async def planner_node(state: AgentState) -> dict[str, Any]:
    client = get_llm_client(ModelSize.large)
    messages = [
        LLMMessage(role="system", content=PLANNER_SYSTEM),
        LLMMessage(
            role="user",
            content=(
                f"数据集（共 {len(state.get('datasets', []))} 个）："
                + "、".join(d['name'] for d in state.get('datasets', []))
                + "（表名：" + ", ".join(d['table_name'] for d in state.get('datasets', [])) + "）\n"
                f"表结构：\n{state['schema_text']}\n\n"
                f"用户问题：{state['user_query']}"
            ),
        ),
    ]
    try:
        resp = await client.chat(messages, temperature=0.0)
    except RuntimeError as exc:
        return {"errors": [str(exc)], "status": "error", "events": [_ev("error", message=str(exc))]}
    plan_text = resp.content or ""
    plan = [
        {"id": f"step_{i+1}", "desc": ln.strip("- ").strip()}
        for i, ln in enumerate(plan_text.splitlines())
        if ln.strip()
    ]
    return {
        "plan": plan,
        "prompt_tokens": resp.prompt_tokens,
        "completion_tokens": resp.completion_tokens,
        "events": [_ev("agent_activity", agent="planner", content="已制定分析计划")],
    }


async def analysis_node(state: AgentState) -> dict[str, Any]:
    datasets = state.get("datasets", [])
    client = get_llm_client(ModelSize.small)
    names = "、".join(d["name"] for d in datasets)
    tables = ", ".join(d["table_name"] for d in datasets)
    schema = "\n\n".join(
        f"表 {d['table_name']}（{d['name']}）:\n" + d["schema_text"] for d in datasets
    )
    multi_hint = ""
    if len(datasets) >= 2:
        multi_hint = (
            "\n\n【多表分析】必须先把多个表 JOIN 关联再计算：\n"
            "1) 对比各表 schema，找出可关联的键（同名字段如 id/date/region/customer_id/order_id，"
            "或语义相同的字段）。\n"
            "2) 给每个表起短别名（如 a、b），并在 SELECT、GROUP BY、ORDER BY、JOIN ON 中用 "
            "`别名.列` 限定，避免 `Ambiguous column` 错误。\n"
            "3) 若确实找不到任何关联键，先只选一个表做描述性统计，并在最终回答中说明两表"
            "无法直接关联的原因，不要编造关联关系。"
        )
    # 重试判定：上一轮 reviewer 未通过才会回到 analysis（此时 retries>=1 且
    # review_result.passed 为 False）。重试时复用既往证据做定向修正，而非从头重跑。
    # ReAct 内循环：reviewer 未通过时 graph 会把 critique 送回本节点。此时不重建对话，
    # 而是「携带既往对话（含工具结果）继续迭代」，实现自我修正，而非跨节点重跑整条链路。
    review = state.get("review_result") or {}
    prior_msgs = state.get("analysis_messages") or []
    is_continue = bool(prior_msgs) and (state.get("retries", 0) or 0) >= 1 and not review.get("passed", True)

    # ④ 沙箱门控：无隔离沙箱时，绝对不暴露 python_execute（否则落到服务器同权限本地进程
    # 执行任意代码 = RCE）。仅给 SQL 工具并明确告知模型。
    python_ok = python_sandbox_isolated()
    tools = [SQL_TOOL_SPEC]
    if python_ok:
        tools.append(PYTHON_TOOL_SPEC)

    if not is_continue:
        # 首轮：构建初始对话（含 planner 计划约束）
        user_content = (
            f"数据集（共 {len(datasets)} 个）：{names}\n"
            f"可用表名：{tables}\n"
            f"表结构：\n{schema}\n\n"
            f"用户问题：{state['user_query']}{multi_hint}"
        )
        # ① Planner 复用：把规划节点产出的子任务作为约束注入分析。
        plan = state.get("plan") or []
        if plan:
            plan_text = "\n".join(
                f"{i+1}. {p.get('desc', '')}" for i, p in enumerate(plan)
            )
            user_content += (
                f"\n\n【分析计划（请尽量遵循，必要时可按数据实际情况微调）】\n{plan_text}"
            )
        if not python_ok:
            user_content += "\n\n（注：本环境 Python 沙箱不可用，请仅使用 sql_execute 工具。）"
        messages: list[LLMMessage] = [
            LLMMessage(role="system", content=ANALYSIS_SYSTEM),
            LLMMessage(role="user", content=user_content),
        ]
        budget = settings.agent_max_steps
        events: list[dict] = [_ev("agent_activity", agent="analysis", content="开始数据分析")]
    else:
        # 续轮：从 state 还原对话，并注入审查意见让模型定向修正（既往工具结果已在上下文中）。
        messages = [_msg_from_dict(m) for m in prior_msgs]
        critique = review.get("comment", "")
        messages.append(
            LLMMessage(
                role="user",
                content=(
                    "上一轮分析未通过审查。请基于上下文里已有的工具结果与证据做针对性修正"
                    "（不要重复执行已成功的查询，优先修正结论或补充缺失的查询）。\n"
                    f"审查意见：\n{critique or '（未提供具体原因）'}"
                ),
            )
        )
        budget = max(2, settings.agent_max_steps // 2)
        events = [_ev("agent_activity", agent="analysis", content="审查未通过，基于反馈继续分析")]

    if not python_ok:
        events.append(
            _ev(
                "agent_activity",
                agent="analysis",
                content="Python 沙箱不可用：本次仅使用 SQL 分析（安全策略）",
            )
        )
    analysis_results: list[dict] = []
    sql_results: list[dict] = []
    python_results: list[dict] = []
    answer = ""
    pt = ct = 0

    for _ in range(budget):
        try:
            resp = await client.chat(messages, tools=tools, temperature=0.0)
        except RuntimeError as exc:
            return {
                "errors": [str(exc)],
                "status": "error",
                "events": [*events, _ev("error", message=str(exc))],
            }
        pt += resp.prompt_tokens
        ct += resp.completion_tokens

        if not resp.tool_calls:
            if resp.content:
                answer = resp.content
                events.append(_ev("message", content=answer))
            break

        messages.append(
            LLMMessage(role="assistant", content=resp.content, tool_calls=resp.tool_calls)
        )
        for tc in resp.tool_calls:
            name = tc.name
            args = tc.arguments or {}
            if name == "sql_execute":
                sql = args.get("sql", "")
                events.append(_ev("tool_start", tool="sql_execute", input={"sql": sql}))
                try:
                    out = await asyncio.to_thread(run_sql_tool, datasets, sql)
                except Exception as exc:  # noqa: BLE001
                    out = {"error": str(exc)}
                events.append(_ev("tool_end", tool="sql_execute", result=out))
                sql_results.append({"sql": sql, "result": out})
                analysis_results.append({"tool": "sql_execute", "sql": sql, "result": out})
                messages.append(
                    LLMMessage(role="tool", content=_summarize_sql(out), tool_call_id=tc.id, name="sql_execute")
                )
            elif name == "python_execute":
                code = args.get("code", "")
                events.append(_ev("tool_start", tool="python_execute", input={"code": code}))
                try:
                    out = await run_python_tool(datasets, code)
                except Exception as exc:  # noqa: BLE001
                    out = {"error": str(exc)}
                events.append(_ev("tool_end", tool="python_execute", result=out))
                python_results.append({"code": code, "result": out})
                analysis_results.append({"tool": "python_execute", "code": code, "result": out})
                messages.append(
                    LLMMessage(role="tool", content=_summarize_python(out), tool_call_id=tc.id, name="python_execute")
                )
            else:
                events.append(_ev("tool_end", tool=name, result={"error": f"未知工具 {name}"}))
                messages.append(
                    LLMMessage(role="tool", content=f"未知工具 {name}", tool_call_id=tc.id, name=name)
                )

    if not answer:
        try:
            resp = await client.chat(messages, tools=tools, temperature=0.0)
            pt += resp.prompt_tokens
            ct += resp.completion_tokens
            if resp.content:
                answer = resp.content
                events.append(_ev("message", content=answer))
        except RuntimeError as exc:
            return {
                "errors": [str(exc)],
                "status": "error",
                "events": [*events, _ev("error", message=str(exc))],
            }

    return {
        # 持久化完整对话，供 reviewer 回边时续跑（ReAct 内循环）。
        "analysis_messages": [_msg_to_dict(m) for m in messages],
        "analysis_results": analysis_results,
        "sql_results": sql_results,
        "python_results": python_results,
        "answer": answer,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "status": "analyzed",
        "events": events,
    }


async def visualization_node(state: AgentState) -> dict[str, Any]:
    # ② 选优：从 SQL 与 Python 的「可绘图」结果中挑质量最高的一框，而非只取最后
    # 一条 SQL（可能只是单值/窄表，生成的图表无意义）。
    candidates: list[tuple[list, list, str]] = []  # (cols, rows, source)
    for r in state.get("sql_results", []):
        fr = _frame_of(r.get("result"))
        if fr:
            candidates.append((*fr, "sql"))
    for r in state.get("python_results", []):
        fr = _frame_of(r.get("result"))
        if fr:
            candidates.append((*fr, "python"))
    if not candidates:
        return {
            "visualizations": [],
            "events": [_ev("agent_activity", agent="visualization", content="暂无结构化结果，跳过图表")],
        }
    best = max(candidates, key=lambda c: _score_frame(c[0], c[1]))

    cols = best[0]
    rows = best[1]
    rc = len(rows)
    sample = rows[:20]
    data = [{cols[i]: row[i] for i in range(len(cols))} for row in rows[: settings.max_chart_rows]]

    # 探测数值列，供 LLM 在≥3个数值列时选择三维图表
    def _is_num(v: Any) -> bool:
        if v is None or v == "":
            return False
        try:
            return not math.isnan(float(v))
        except (TypeError, ValueError):
            return False

    numeric_cols = [
        cols[i]
        for i in range(len(cols))
        if i < len(cols) and all(_is_num(row[i]) for row in sample if i < len(row))
    ]

    client = get_llm_client(ModelSize.large)
    messages = [
        LLMMessage(role="system", content=VIZ_SYSTEM),
        LLMMessage(
            role="user",
            content=(
                f"用户问题：{state['user_query']}\n"
                f"可用字段：{cols}\n"
                f"数值字段：{numeric_cols}\n"
                f"结果行数：{rc}\n"
                f"样例：{json.dumps(sample, ensure_ascii=False)[:1500]}\n"
                "请调用 generate_chart 选择图表类型与 x/y 轴字段（三维图表还需 z_field）。"
            ),
        ),
    ]
    try:
        resp = await client.chat(messages, tools=[GENERATE_CHART_TOOL], temperature=0.0)
    except RuntimeError as exc:
        return {
            "visualizations": [],
            "events": [_ev("error", message=f"可视化失败: {exc}")],
        }
    spec = None
    if resp.tool_calls:
        a = resp.tool_calls[0].arguments
        ctype = a.get("type", "bar")
        is_3d = ctype.startswith("3d_")
        spec = {
            "renderer": "r3f" if is_3d else "echarts",
            "type": ctype,
            "title": a.get("title", state["user_query"]),
            "xField": a.get("x_field", cols[0]),
            "yField": a.get("y_field", cols[1] if len(cols) > 1 else cols[0]),
            "zField": a.get("z_field") if is_3d else None,
            "data": data,
        }
    events = (
        [_ev("chart", spec=spec)]
        if spec
        else [_ev("agent_activity", agent="visualization", content="未生成图表")]
    )
    return {
        "visualizations": [spec] if spec else [],
        "prompt_tokens": resp.prompt_tokens,
        "completion_tokens": resp.completion_tokens,
        "events": events,
    }


async def reviewer_node(state: AgentState) -> dict[str, Any]:
    from app.services.evidence_check import run_rule_checks

    answer = (state.get("answer", "") or "").strip()
    sql_results = state.get("sql_results", []) or []
    python_results = state.get("python_results", []) or []

    # —— Reviewer 2.0 · 通道 1：确定性规则校验（硬闸门）——
    # 规则通道不依赖 LLM，可复现。任一硬规则失败即标记未通过，无论 LLM 如何表态，
    # 避免"自信但无依据"的结论蒙混过关。第 4 条语义对齐为 advisory「提示」。
    rule_checks, rules_passed = run_rule_checks(
        answer,
        sql_results,
        python_results,
        semantic_metrics=state.get("semantic_metrics", []),
    )

    # 结论为空 → 硬性未通过（无证据可审查）。
    if not answer:
        return {
            "review_result": {
                "passed": False,
                "comment": "分析结论为空，无证据可审查",
                "checks": rule_checks,
                "channels": {"rules": False, "llm": False},
            },
            "retries": (state.get("retries", 0) or 0) + 1,
            "events": [_ev("agent_activity", agent="reviewer", content="审查未通过：分析结论为空")],
        }

    if not rules_passed:
        failures = [c["detail"] for c in rule_checks if not c["passed"]]
        comment = "规则校验未通过：" + "；".join(failures)
        return {
            "review_result": {
                "passed": False,
                "comment": comment,
                "checks": rule_checks,
                "channels": {"rules": False, "llm": False},
            },
            "retries": (state.get("retries", 0) or 0) + 1,
            "events": [_ev("agent_activity", agent="reviewer", content=f"审查未通过：{comment}")],
        }

    # —— Reviewer 2.0 · 通道 2：LLM 语义校验（规则通道已通过后再执行）——
    client = get_llm_client(ModelSize.large)
    evidence = json.dumps(
        {"sql": sql_results[:5], "python": python_results[:5]},
        ensure_ascii=False,
    )[:2400]
    messages = [
        LLMMessage(role="system", content=REVIEWER_SYSTEM),
        LLMMessage(
            role="user",
            content=(
                f"用户问题：{state['user_query']}\n"
                f"分析结论：{answer[:1500]}\n"
                f"证据（SQL/Python 结果）：{evidence}\n"
                "结论中的关键数字是否能在证据中找到对应值？调用 review_decision。"
            ),
        ),
    ]
    try:
        resp = await client.chat(messages, tools=[REVIEW_TOOL], temperature=0.0)
    except RuntimeError as exc:
        # ③ 审查器自身失败时「保守地」标记未通过（而非静默放行），让重试/人工复核
        # 机制生效；不会死循环——graph 仅在 retries < agent_max_retries 时回 analysis。
        return {
            "review_result": {
                "passed": False,
                "comment": f"审查器调用失败，保守标记未通过以触发复核: {exc}",
                "checks": rule_checks,
                "channels": {"rules": True, "llm": False},
            },
            "retries": (state.get("retries", 0) or 0) + 1,
            "events": [_ev("agent_activity", agent="reviewer", content=f"审查器异常，标记未通过: {exc}")],
        }
    passed = True
    comment = ""
    if resp.tool_calls:
        a = resp.tool_calls[0].arguments
        passed = bool(a.get("passed", True))
        comment = a.get("comment", "")
    else:
        comment = resp.content or ""

    # 仅在未通过（触发重跑）时累计重试次数
    retries = (state.get("retries", 0) or 0) + (0 if passed else 1)
    events = [
        _ev(
            "agent_activity",
            agent="reviewer",
            content="审查通过" if passed else f"审查未通过：{comment}",
        )
    ]
    return {
        "review_result": {
            "passed": passed,
            "comment": comment,
            "checks": rule_checks,
            "channels": {"rules": True, "llm": passed},
        },
        "retries": retries,
        "prompt_tokens": resp.prompt_tokens,
        "completion_tokens": resp.completion_tokens,
        "events": events,
    }
