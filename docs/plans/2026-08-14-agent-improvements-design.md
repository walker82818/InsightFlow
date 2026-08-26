# InsightFlow 改进设计（2026-08-14）

> 背景：经 code review，项目结构（pnpm monorepo + FastAPI + Next.js）已较完整，
> Phase 1–7 核心链路打通。本设计针对 4 个**真实架构/质量缺陷**做定向改进，不重构整体架构。

---

## 0. 问题总览

| # | 问题 | 严重度 | 根因 |
|---|------|--------|------|
| 1 | 重试丢失既往证据、重复烧钱 | 高 | state 字段缺 reducer + 重试从头重跑 ReAct |
| 2 | SSE 双会话、崩溃后 run 永久 running | 中 | 路由与 run_analysis 各自建会话 |
| 3 | 并发 `/run` 无拦截 | 中 | 路由未检查 status==running |
| 4 | 报告 trace 缺失时指标偏弱 | 低 | 已有兜底，仅收口 |
| 5 | README PG 端口漂移 | 低 | 文档与 .env 事实不一致 |

---

## 1. Agent 重试：累积证据 + 定向重试（问题 1）

### 根因（已用代码确认）
- `app/agent/state.py` 中 `sql_results / python_results / analysis_results` **无 reducer**，
  采用 last-writer-wins。`reviewer` 路由回到 `analysis` 时，`analysis_node` 返回的
  新 `sql_results` 会**整体覆盖**上一轮结果 → 先前 SQL 结果、token 全部丢弃。
- `analysis_node` 重试时仍从原始 `user_query` 完全重跑 ReAct 循环（`agent_max_steps` 次），
  未利用已查证据，会**重复执行相同 SQL**、重复消耗 DB + LLM。

### 改动
1. **`state.py`**：给 `sql_results / python_results / analysis_results` 加
   `Annotated[list, operator.add]` reducer（证据累积）。
   `visualizations / answer / review_result` 保持 last-writer（重试只覆盖最终结论/图表，符合预期）。
2. **`nodes.py` `analysis_node`**：
   - 检测重试：`state.get("retries", 0) >= 1 and not state.get("review_result", {}).get("passed")` 时，
     在首条 user message 末尾追加「**既往证据摘要**（取累积 `sql_results/python_results` 前几条）
     + **审查 critique**（`review_result.comment`）」区块，使模型做**定向修正**而非从头再来。
   - 重试时 step 预算下调：`max(2, settings.agent_max_steps // 2)`，降低重试成本。
3. **不把 `messages` 放进 state**：避免 checkpoint 序列化复杂度；改为每次重建但注入既往证据块。
   `MemorySaver`（in-memory）下也无需持久化 messages。

### 收益
- 最终 `sql_results` 为各轮**并集**，可视化/报告拿更完整证据。
- 重试 LLM 步数更少、不重跑相同 SQL，直接降 token 成本（对按量计费的国内模型敏感）。

---

## 2. SSE 持久化与会话统一 + 崩溃恢复（问题 2）

### 根因
- `analyses.py::run_analysis_stream` 路由用 `get_session` 调 `set_running`，
  而 `single_agent.run_analysis` 内部用独立 `AsyncSessionLocal` 落库 → **两套会话各自为政**。
- 若进程在流式期间崩溃，遗留 `AgentRun.status="running"` 永久挂起。

### 改动
1. **`single_agent.run_analysis` 开头统一负责"置运行态"**（用自身 session）：
   - 将对应 `Analysis.status` 置 `"running"` 并提交；
   - **崩溃恢复**：把本 analysis 任何遗留 `status="running"` 的 `AgentRun` 标为 `"error"`（interrupted）；
   - 新建 `AgentRun(status="running", ...)`，记录 `run_id`。
2. **`analyses.py` 路由**：
   - 开始流式前若 `row.status == "running"` 返回 **409**（并发拦截，见问题 3）；
   - **删除**路由里冗余的 `set_running` 调用（改由 `run_analysis` 统一负责）。
3. 保留 `run_analysis` 内部自管会话：该函数是库函数，`evals/runner.py` 直接复用，
   不应依赖请求级 session（保持现状即可，无需注入）。

### 收益
- 状态一致、无重复 `set_running`；崩溃重启后历史遗留 run 被自动标 error；
- 并发 `/run` 被 409 拒绝（问题 3 一并解决）。

---

## 3. 报告鲁棒性收口（问题 4）

### 现状（已确认较轻）
`report.py::_build_metrics` 在 `run_summary is None` 时已用 `analysis_prompt_tokens /
analysis_completion_tokens` 兜底成本，所以成本**不会凭空丢失**。仅有两处可收口：

### 改动
1. **`analyses.py::create_report`**：当 `trace` 缺失时，构造**合成 `run_summary`**
   （`prompt/completion tokens` 取自 analysis 行，`cost` 用 `settings.trace_cost_per_1k_*` 估算，
   `latency_ms/tool_calls` 标 `None/0`），保证 metrics 块始终有值且字段完整。
2. **收紧生成条件**：`analysis.status == "running"` 时**不生成**报告，返回 409
   （避免对空结果_json 生成弱报告），待 `completed` 后再生成。

---

## 4. 文档与配置对齐（问题 5）

### 改动（`README.md` 第 3 节）
- 以**原生安装（推荐，端口 5432）**为默认；Docker 仅作可选替代说明。
- 统一端口为 **5432**，移除文中 5433 表述（与 `apps/api/.env` 实际值一致）。
- 补充：`storage_backend` 默认 `local`，MinIO 仅在显式设为 `minio` 时生效。

> 纯文档改动，零代码风险。

---

## 5. 验证方式
1. **重试**：构造一个"结论缺少证据"的 query，触发 `reviewer` 未通过 → 观察 trace 中
   `sql_results` 是否累积、重试轮 LLM 步数是否下降。
2. **并发 409**：对同一 analysis 连发两次 `/run`，第二次应返回 409。
3. **崩溃恢复**：手动把某 `AgentRun` 置 `running`，再跑一次该 analysis，确认被标 `error`。
4. **报告**：对 `completed` analysis 调 `/report`，确认 metrics 含 `cost`；对 `running` 状态确认 409。

## 6. 影响范围 / 风险
- 改动文件：`app/agent/state.py`、`app/agent/nodes.py`、`app/agent/single_agent.py`、
  `app/api/v1/analyses.py`、`README.md`。（`graph.py` 大概率无需改。）
- 风险：**低–中**。reducer 改动需回归**正常流程（无重试）**结果不被破坏——
  因为 `operator.add` 在单次运行时等价于追加一次完整列表，与原行为一致，风险可控。
