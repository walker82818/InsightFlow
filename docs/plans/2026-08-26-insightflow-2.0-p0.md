# InsightFlow 2.0 升级改造设计（2026-08-26）— P0 核心差异化

> 背景：基于《InsightFlow_2.0_Data_Agent_升级改造方案.docx》做技术落地方案。
> 定位从 1.0 的"问答式数据分析 Agent"升级为 2.0 的**"证据驱动的自主数据分析师"**：
> 上传即主动产出洞察、每个结论可溯源到结构化证据、对"为什么"能给出带贡献度分解的根因。
> 本设计覆盖 P0 四模块（Data Profiler 2.0 / Semantic Layer / Insight Discovery / Root Cause）
> + Reviewer 2.0 证据闭环，架构为 P1（Evidence Graph / Data Source 统一 / Evaluation 2.0）预留挂载点。
>
> 已与用户确认的决策见 §0。本文档为后续实现的蓝图。

---

## 0. 本期关键决策

| # | 决策项 | 结论 |
|---|--------|------|
| D1 | 领域对象持久化 | **新增 PostgreSQL 领域表**（六类），独立查询/审计，替代塞进 `analyses.result_json` |
| D2 | LangGraph 拓扑 | **上传即跑子图**（profile→semantic→insight）+ **问答条件分支**（root_cause），非串行塞进主链路 |
| D3 | 语义层 | **自动建议 + 人工确认**双态（`auto`/`confirmed`），`confirmed` 优先于 `auto` |
| D4 | 字段关系识别 | P0 只做**启发式提示**（`suggested_join` + strength），不自动 join，避免误连多表 |
| D5 | 根因置信 | **确定性贡献度分解**为核心（SQL 分组加总，LLM 不编数字）+ **变化显著性门槛**（幅度过小/样本过少直接拒答） |
| D6 | 洞察配额 | **可配置**（settings 参数），默认每数据集 ≤6 条，只对 top metric×维度组合计算 |
| D7 | 现有端点 | 保留现有上传流程，profile/semantic/insight 挂在上传后**异步触发** + 新增 GET 端点，增量改造 |
| D8 | 迁移 | 全部新增**全新表 + 独立 JSON 字段**，不动现有表结构，规避无迁移系统的 ALTER 坑 |

---

## 1. 总体架构与领域对象

### 1.1 目标架构

```
                        ┌─────────────── 上传即跑子图（异步，独立于问答）───────────────┐
   上传文件 ────────────►  profile_node ─► semantic_node ─► insight_node ─► 落表/前端面板
                         (全量画像)        (建议指标维度)     (主动洞察 ≤6条)
                              │
                              ▼
                         dataset_profiles / metrics / dimensions / insights  表
                              │
   用户提问 ─────────────────►  planner（注入语义层口径）
                                    │
                           ┌────────┴─────────┐
                    "为什么"                普通分析
                           ▼                     ▼
                  root_cause 子图          analysis（写 evidences 表）
                  （贡献度分解）                    │
                           │                     visualization
                           ▼                     ▼
                  root_causes 表           reviewer 2.0（规则+LLM 双通道）
                                                    │
                                           通过 / 定向重试
```

### 1.2 六类新增 PG 领域表

全部挂在 `apps/api/app/models/`，注册进 `db/base.py` 的 `Base.metadata`（`create_all` 自动建全新表，无迁移系统）。

| 表 | 归属模块 | 关键字段 | 目的 |
|----|---------|---------|------|
| `dataset_profiles` | Data Profiler | `dataset_id`, `quality_score`, `issues`(JSON), `schema_json`(角色/关系), `anomalies`(JSON), `generated_at` | 升级后完整画像，独立于 `datasets.profile_json` |
| `metrics` | Semantic Layer | `dataset_id`, `name`, `sql_expr`, `aggregation`, `unit`, `description`, `status`(auto/confirmed) | 业务指标定义 |
| `dimensions` | Semantic Layer | `dataset_id`, `name`, `column`, `is_time`, `granularity`, `description`, `status` | 业务维度定义 |
| `insights` | Insight Discovery | `dataset_id`, `kind`, `title`, `conclusion`, `metric`, `dimensions`(JSON), `evidence`(JSON), `confidence`, `severity`, `sql` | 主动发现的洞察 |
| `evidences` | 证据链（P0 即启用） | `analysis_id`, `parent_id`, `claim`, `source`(sql/python/profile/semantic/llm_reasoning), `result`(JSON), `metric`, `confidence`, `ts` | 证据链节点，Reviewer 2.0 与 Root Cause 共享 |
| `root_causes` | Root Cause | `analysis_id`, `question`, `change`(JSON), `hypotheses`(JSON), `contributions`(JSON), `conclusion`, `confidence`, `factors`(JSON) | 根因结论 |

> `evidences.parent_id` P0 预留，P1 扩展为完整 Evidence Graph。

### 1.3 规范化 Evidence 结构（跨模块核心中介）

所有产出（洞察、根因、审查）以同一结构为载体：

```jsonc
{
  "claim": "华东区 6 月销售额环比下降 12%",
  "metric": "sales_amount",
  "dimensions": ["region", "month"],
  "source": "sql",              // sql | python | profile | semantic | llm_reasoning
  "sql": "SELECT ...",
  "result": {"rows": [...], "n": 1},
  "confidence": 0.86,           // 0-1，组合计算
  "parents": [],                // 依赖的上游 evidence id（P1 图）
  "ts": 1725000000000
}
```

**置信度组合规则**：统计证据高（样本完整、n 大、差异显著）→ 基础分高；LLM 判定弱/模棱两可 → 扣分。
2.0 相对 1.0 的关键：不再只是"结论有没有"，而是"结论有多可信 + 凭什么信"。

---

## 2. Data Profiler 2.0

在现有 `profiling.py`（列类型 + 基础统计）上扩展，保持上传流程不变，完整画像落 `dataset_profiles` 表。

### 2.1 分层

| 层 | 内容 | 落点 |
|----|------|------|
| ① 基础画像 | 列逻辑类型 + 统计（沿用现有） | `datasets.profile_json`（不变） |
| ② 数据质量报告 | 缺失率、空串、格式不一致、IQR 离群、全常数列、重复行 | `dataset_profiles.quality_*` |
| ③ 字段角色推断 | id / 时间维度 / 维度 / 指标候选 / 数值维度 / 文本 | `dataset_profiles.schema_json` |
| ④ 潜在关系识别 | 列名归一化 + 值域交叠推断 FK 候选 | `dataset_profiles.schema_json.relations` |
| ⑤ 异常检测 | 未来日期、负值出现在非负列、IQR 突刺 | `dataset_profiles.anomalies` |

### 2.2 质量评分公式（确定性、可解释）

`Q = 100 − Σ penalty`，按类别加权（缺失/重复/异常/格式），输出 `issues[]`（每条含列名、类型、严重度、建议）。
该分数作为 insight 置信度的先验之一。

### 2.3 字段角色判定规则

```
id           → 主键候选（高唯一、非空、无异常）
date/time    → 时间维度（标注 grain: 日/月/年）
category     → 维度 (dimension)
numeric 低基数 → 数值维度（≤20 distinct 且 min/max 为整数小范围，如"评分 1-5"）
numeric 其余 → 指标候选 (metric)
string 高基数 → 文本/命名维度
```

### 2.4 关系识别（启发式，保守）

基于**列名归一化**（去下划线/驼峰/后缀）+ **值域交叠比**推断 FK 候选，输出 `relation_type: "suggested_join"` + `strength`。
只给 planner 参考，不自动 join。

---

## 3. Semantic Layer

让 Agent 用"业务词"而非"列名"。`metrics` / `dimensions` 表承载业务语义。

- **自动建议 + 人工确认**：`semantic_node` 用**小模型**读 `dataset_profiles.schema_json` 批量生成候选
  metric/dimension（含 SQL 表达式如 `SUM(amount)`、时间粒度），`status=auto`；用户可确认/修改 → `status=confirmed`。
  **confirmed 优先于 auto**（语义层权威性来自人工确认）。
- **查询改写（注入式）**：planner 注入语义层内容，把 `"销售额"` → `SUM(amount)`、`"按地区"` → `GROUP BY region`。
  P0 先做**注入**（喂给 LLM 参考），不做硬解析。
- **进 AgentState**：`AgentState.schema_text` 附上已确认 metrics/dimensions，analysis 直接引用业务口径。

---

## 4. Insight Discovery Engine（`insight_node`，上传后异步）

### 4.1 六类洞察（按确定性排序）

| kind | 触发 | 计算 | 确定性 |
|------|------|------|--------|
| `trend` | 有时间维度 | 对每个 metric 按 grain 算环比/同比/增长率，斜率/残差判趋势 | 高 |
| `anomaly` | 有时间维度 | 时间序列 Z-score / IQR 找突刺点（复用 profiler anomalies） | 高 |
| `distribution_shift` | 分类维度 | 维度取值占比随时间显著变化（JS 散度 / 占比差 > 阈值） | 中 |
| `top_contribution` | metric + 分类维度 | Top-N 维度取值对总量的累计贡献（帕累托） | 高 |
| `correlation` | ≥2 数值列 | 皮尔逊相关（\|r\|>0.6），**只提示、不做因果** | 中 |
| `quality` | 任一表 | 从 `quality_*` 提取高严重度问题 | 高 |

### 4.2 置信度分级与配额

- 确定性高（trend/top_contribution/quality）给高先验；需 LLM 措辞的（correlation/distribution_shift）先算统计，
  再让**小模型**生成 `conclusion` 中文文案并校正置信度。
- `severity`（high/medium/low）= 置信度 × 指标量级。
- **配额**：每数据集 ≤6 条（settings 可配 `insight_max_count`），只针对**前 3 最高量级 metric × 前 2 维度**组合，超时降级。

---

## 5. Root Cause Analysis（`root_cause_node`，问答条件分支）

当 planner 判定为"为什么"问题时走子图。五步，每步产 `Evidence`：

```
① confirm_change    : SQL 确认"变化/差异是否真实存在、量级多大"（基准期 vs 变化期）
② generate_hypotheses: 大模型基于 schema/semantic + 变化量列 2-4 个候选假设
③ collect_evidence  : 对每个假设用 SQL/Python 收集支持/反驳证据（同一 Evidence 结构）
④ rank_factors      : 贡献度分解（region/segment/product 各贡献多少下降额，确定性加总，排除量级小）+ LLM 排序
⑤ conclude          : 输出 {主要根因, 贡献度, 支撑证据, 置信度, 待验证项}
```

**核心原则**：根因的确定性核心是**贡献度分解**（"华东贡献了 60% 的下滑"），来自 SQL 分组加总，
可复现、可审计——LLM 只负责假设生成与措辞，**不编数字**。

**变化显著性门槛（D5）**：环比变化幅度 < `settings.root_cause_min_delta`（默认 5%）或样本过少时，
直接返回"变化不显著，无根因可分析"，避免对无意义波动强行编故事。

前端在报告区下方渲染"根因分析"卡片（结论 + 各因素贡献条形图 + 证据可折叠查看 SQL）。

---

## 6. Reviewer 2.0（证据驱动的审查）

现有 reviewer 为纯 LLM 判断 `passed`。2.0 升级为**双通道校验**，是"证据驱动"闭环的最后一块。

### 6.1 确定性校验（规则层，无 LLM，必过）

```
check_numeric_claims : 结论中数字（金额/计数/占比/排名）能在 evidence.result 实际行命中（容差 ±1% 或 ±1 单位）
check_sql_reproduce  : 结论引用的 SQL 真实执行成功过（在 sql_results 里）
check_evidence_sup   : 每个 metric/结论点至少有一条 Evidence 支撑
check_semantic_alignment: 用的度量是否来自语义层口径（绕过 confirmed metric 则提示）
```

四条全过才允许"通过"；任一不过 → 标记不通过并**结构化指出具体失败规则**（非笼统"数字对不上"），
让 analysis 定向修正。

### 6.2 LLM 通道（语义层）

规则层过后，LLM 只做**语义一致性**（措辞、因果夸大、是否回答问题），不再兜底编数字。
规则层 + LLM 双通过 → `passed`；规则层不过 → 直接拒。

### 6.3 evidences 表启用

analysis 节点把每次成功工具调用的 `{claim, sql, result, metric, confidence}` 写入 `evidences` 表，
reviewer 直接查表核对（因此 `evidences` 表在 P0 即启用，不推到 P1）。

---

## 7. 端到端数据流（P0 全貌）

```
上传文件
  → profile_node  → dataset_profiles 表（质量分/角色/关系/异常）
  → semantic_node → metrics/dimensions 表（auto，待人工确认）
  → insight_node  → insights 表（≤6条，前端"AI洞察"面板）
         │
用户提问 ────────► planner(semantic 注入) → analysis(写 evidences 表)
                        │                     │
                        ├─"为什么"──► root_cause 子图（贡献度分解）→ root_causes 表
                        └─普通─────► visualization → reviewer 2.0(规则+LLM) → 通过/重试
```

---

## 8. 实现顺序（3 批，每批可独立交付验证）

| 批次 | 内容 | 交付验证点 |
|------|------|-----------|
| **批 1：数据基建** | 新增 6 张表模型 + Profiler 2.0（quality/roles/relations/anomalies）+ profile_node/semantic_node 子图 | 上传后数据集详情页出现「数据质量」+「语义层」面板，可确认/编辑 metric |
| **批 2：主动洞察** | insight_node（六类检测器）+ insights 表/端点/「AI 洞察」面板 | 上传即出 ≤6 条洞察卡片，置信度与证据可查 |
| **批 3：证据闭环** | evidences 写入 + Reviewer 2.0 双通道 + root_cause 子图 + 根因卡片 | "为什么"问题出根因分解图；审查失败时给出结构化规则原因 |

依赖：批 2 依赖批 1 的 schema/semantic；批 3 依赖批 1 的 evidences 表 + 批 2 的 evidence 结构。

---

## 9. 改动清单

### 9.1 后端（apps/api）

| 文件 | 改动 |
|------|------|
| `models/dataset.py` | 新增 `DatasetProfile` 模型（quality/schema/relations/anomalies JSON 字段） |
| `models/semantic.py` | 新增 `Metric`、`Dimension` |
| `models/insight.py` | 新增 `Insight` |
| `models/evidence.py` | 新增 `Evidence` |
| `models/root_cause.py` | 新增 `RootCause` |
| `models/__init__.py` | 注册新模型（确保 `create_all` 建表） |
| `services/profiling.py` | 扩展 quality/roles/relations/anomalies 子模块 |
| `services/semantic.py` | 新：`suggest_semantics()` 小模型批处理 |
| `services/insight.py` | 新：六类检测器 + LLM 措辞封装 |
| `services/root_cause.py` | 新：五步子图逻辑 + 贡献度分解 + 显著性门槛 |
| `services/evidence.py` | 新：Evidence 写入/读取/置信度组合 |
| `agent/nodes.py` | 新 `profile_node` / `semantic_node` / `insight_node` / `root_cause_node`（及子步骤） |
| `agent/graph.py` | 上传即跑子图 + 主链路 root_cause 条件边（复用现有 conditional routing） |
| `agent/state.py` | `AgentState` 扩展（profile/semantic/insights/evidences 相关字段） |
| `api/datasets.py` | 上传后异步触发子图；新增 GET profile/semantics 端点 |
| `api/insights.py` | 新：GET `/datasets/{id}/insights` |
| `api/analyses.py` | 新：GET `/analyses/{id}/root-cause` |
| `schemas/` | 新增对应 Pydantic 响应模型 |
| `core/config.py` | 新增 `insight_max_count`、`root_cause_min_delta` 等 settings |

### 9.2 前端（apps/web）

| 改动 | 说明 |
|------|------|
| 数据集详情页「数据质量」面板 | 质量分 + issues 列表 |
| 数据集详情页「语义层」面板 | 确认/编辑 metric/dimension |
| 数据集详情页「AI 洞察」面板 | ≤6 条洞察卡片（置信度 + 证据可查） |
| 报告区「根因分析」卡片 | 结论 + 贡献条形图 + 证据折叠查看 SQL |
| `api.ts` | 新增对应请求封装 |

---

## 10. 关键注意事项（衔接现有代码）

- **无迁移系统**：新增 6 张全新表由 `create_all` 自动建，无需 ALTER；本设计**不改动现有表结构**，
  规避无迁移的坑。若后续给已有表加列需手动 ALTER（见项目记忆）。
- **保留现有端点**：不新增上传端点，profile/semantic/insight 挂在上传后异步触发 + 新 GET 端点。
- **DuckDB 引擎复用**：insight/root_cause 检测器复用现有 `run_sql_tool` 的 DuckDB 连接，不另起数据栈。
- **Python 沙箱门控**：检测器同样受 `python_sandbox_isolated()` 门控，无沙箱时退化为纯 SQL。
- **Streaming 复用**：新节点沿用 `_ev()` 事件旁路（`_STREAM_QUEUE` contextvar），SSE 实时推送不重建。

---

## 11. P1 展望（架构已预留，本期不实现）

- **Evidence Graph**：`evidences.parent_id` 扩展为有向图，支持多跳溯源的完整证据链可视化。
- **Data Source 统一**：文件 / 直连 DB 抽象为统一 source 接口（当前 file/db 均已落到 DuckDB，接入成本低）。
- **Evaluation 2.0**：用 `evidences` 表 + 置信度做自动化断言评估，替代纯 LLM 评分。
- **Langfuse 接入**：P0 新节点的事件/置信度/证据可挂 Langfuse 可观测。
