# InsightFlow

## AI Data Analysis & Visualization Agent
### 技术方案设计文档 / Technical Design Document

**版本：V1.0**
**定位：秋招作品集 / 可部署个人项目 / Agent Engineering 实践**
**派生自：AgentViz 技术方案设计文档（项目改名 + 技术栈本地化适配）**

---

## 0. 本期关键决策（与原 AgentViz 文档的差异）

本设计在保留原 AgentViz 架构与流程的前提下，做了以下适配（均已与用户确认）：

| # | 决策项 | 结论 |
|---|--------|------|
| D1 | 项目命名 | `AgentViz` → **InsightFlow**（目录、文档、标题、简历文案统一替换） |
| D2 | 包管理 | **pnpm**（monorepo + pnpm workspace），原文档用 npm |
| D3 | 3D 可视化 | **react-three-fiber (r3f) + drei** 替代原生 Three.js |
| D4 | 后端运行 | **Python venv 虚拟环境** + uvicorn 本地运行，替代容器化后端 |
| D5 | 基础设施 | **本地原生安装**：PostgreSQL / Redis / MinIO 本机运行；**Docker 仅用于 Python 沙箱** |
| D6 | LLM 供应商 | **provider 抽象**，默认国内模型（DeepSeek / Qwen / 通义，均兼容 OpenAI 协议）；小模型做 Schema/简单任务，大模型做规划/总结 |
| D7 | 鉴权 | **暂不鉴权**，固定单默认用户（users 表保留） |
| D8 | 范围 | **完整 Phase 1-10**（含 Evaluation、报告导出、Docker 化与部署） |

其余（FastAPI、LangGraph、DuckDB、Pandas/NumPy、ECharts 2D、SSE、MinIO 对象存储）与原文档一致。

---

## 1. 项目概述

InsightFlow 是一个面向数据分析场景的 Agentic Data Intelligence 平台。用户上传 CSV/Excel 或连接数据库后，可以直接使用自然语言提出分析需求。系统通过 Planner、Data Agent、Analysis Agent、Visualization Agent 和 Reviewer Agent 协同完成数据理解、SQL/Python 执行、统计分析、可视化生成、结果校验和报告生成。

### 1.1 项目定位
- 不是简单的 LLM Chatbot，而是具有状态、工具、规划、反馈和验证机制的 Agent 系统。
- 不是以 RAG 为核心，而是以 Agentic Data Analysis 为核心，RAG 作为业务知识增强能力（V2）。
- 不仅生成文字答案，还生成可复用的数据分析结果、ECharts 图表、react-three-fiber 3D 可视化和结构化报告。
- 支持本地原生环境一键启动（pnpm + venv + 本地 PG/Redis/MinIO），最终可 Docker 化部署到云服务器。

### 1.2 核心价值

| 能力 | InsightFlow 实现 |
|------|------------------|
| Agent Loop | Reason → Tool → Observation → State Update → Continue |
| Tool Calling | SQL、Python、DuckDB、数据分析、图表生成 |
| Multi-Agent | Planner / Data / Analysis / Visualization / Reviewer |
| State | LangGraph StateGraph 管理任务状态 |
| Persistence | Checkpoint + PostgreSQL 持久化执行状态 |
| Visualization | ECharts 2D + react-three-fiber 3D |
| Evaluation | 正确性、工具调用、图表、报告质量评估 |
| Observability | Agent 执行 Trace（SSE 事件 → steps/tool_calls 落库） |
| Deployment | 本地 venv + Docker 沙箱；最终 Docker Compose + Nginx + PostgreSQL + Redis + MinIO |

---

## 2. 产品目标与最终形态

### 2.1 用户最终体验
```
用户
↓ 上传 sales_2025.csv
↓ 输入：分析 2025 年销售额下降的主要原因，重点看地区、产品和月份
↓ Planner 拆解任务
↓ Data Agent 理解数据
↓ Analysis Agent 调用 SQL / Python / DuckDB
↓ Visualization Agent 生成 2D / 3D 图表
↓ Reviewer 检查结论与证据
↓ 必要时自动重试
↓ 生成分析报告
↓ 用户查看 Agent Trace / 图表 / 报告并导出
```

### 2.2 最终页面

| 页面 | 主要功能 | 优先级 |
|------|----------|--------|
| Dashboard | 任务、数据集、最近报告、快速开始 | P0 |
| Dataset | 上传、Schema、数据预览、质量分析 | P0 |
| Analysis Workspace | 自然语言分析、实时 Agent 状态、结果 | P0 |
| Visualization | ECharts + react-three-fiber | P1 |
| Agent Trace | Agent/Tool/Retry/Token/Latency | P1 |
| Report | 结构化报告、导出、分享 | P1 |
| Settings | 模型、用户配置、系统设置 | P2 |

---

## 3. 核心用户流程

### 3.1 数据上传流程
```
Browser → POST /datasets → FastAPI → File Validation
→ MinIO Object Storage → Dataset Record → PostgreSQL
→ DuckDB Registration → Schema Detection + Profiling → Dataset Ready
```

### 3.2 分析任务流程
```
User Query → Create Analysis → LangGraph Thread
→ Planner → Data Agent → Analysis Agent
   ├── SQL Tool
   ├── Python Tool
   └── Dataset Tool
→ Visualization Agent → Reviewer
   ├── PASS → Report
   └── FAIL → Retry / Additional Analysis
→ Completed
```

---

## 4. 功能模块设计

### 4.1 Dataset 数据集模块
- CSV/Excel/JSON 上传（本地 MinIO 存储）。
- 文件大小、扩展名、MIME 类型校验。
- Schema 自动识别：string / integer / float / date / category。
- 行数、列数、缺失值、重复值、异常值统计。
- 数据预览与字段级统计。
- 未来扩展 PostgreSQL/MySQL/API 数据源。

### 4.2 Analysis 分析模块
- 自然语言创建分析任务。
- Planner 自动拆解分析步骤。
- SQL、Python、统计分析工具调用。
- 任务状态实时流式更新（SSE）。
- 支持失败重试与人工审批（Human-in-the-loop）。

### 4.3 Visualization 可视化模块
- LLM 只生成结构化 ChartSpec，不直接生成 HTML/JS。
- ECharts 负责常规 2D 图表（`echarts-for-react`）。
- **react-three-fiber + drei 负责 3D Scatter、3D Bar、3D Map 等交互式数据探索**（替代原生 Three.js）。
- 图表结果与分析证据绑定，避免"图表与结论脱节"。

### 4.4 Report 报告模块
- Executive Summary / Key Findings / Evidence / Charts / Recommendations。
- 支持 HTML / PDF 导出。

---

## 5. 总体技术架构

```
┌──────────────┐
│ User         │
└──────┬───────┘
       │ Natural Language
       ▼
┌─────────────────────────────────────────────────────────────┐
│ Next.js (pnpm)                                               │
│ Dashboard │ Dataset │ Analysis │ Visualization │ Report      │
└────────────────────────────┬────────────────────────────────┘
       │ REST / SSE
       ▼
┌─────────────────────────────────────────────────────────────┐
│ FastAPI (venv + uvicorn)                                     │
│ Auth │ Dataset │ Analysis │ Report │ Agent │ Streaming        │
└────────────────────────────┬────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ LangGraph                                                    │
│ Planner → Data → Analysis → Visualization → Reviewer         │
│ State │ Checkpoint │ Memory │ Interrupt │ Streaming           │
└──────────────┬──────────────────────────────┬───────────────┘
       │                                        │
       ▼                                        ▼
┌─────────────┐                        ┌──────────────┐
│ Tools       │                        │ Agent Trace  │
│ SQL/Python  │                        │ SSE steps/db │
│ DuckDB      │                        └──────────────┘
│ Dataset     │
│ Chart       │
└──────┬──────┘
       │
   ┌───┼─────────┐
   ▼   ▼         ▼
PostgreSQL  DuckDB   Sandbox(Docker)
   │
   └───┼─────────┐
       ▼         ▼
     Redis     MinIO(本地)
```

### 5.1 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 包管理 | **pnpm** | monorepo workspace 依赖管理 |
| Frontend | Next.js + React + TypeScript | Web 应用与交互 |
| UI | Tailwind CSS | 界面系统 |
| 2D Visualization | ECharts (`echarts-for-react`) | 常规数据图表 |
| 3D Visualization | **react-three-fiber + drei** | 3D 数据探索 |
| Backend | FastAPI (venv + uvicorn) | REST / SSE API |
| Agent | LangGraph + Pydantic | Agent orchestration / State / Structured Output |
| LLM | **provider 抽象（DeepSeek/Qwen/通义，OpenAI 兼容）** | 规划 / 计算决策 / 总结 |
| Data | DuckDB + Pandas + NumPy | 分析计算 |
| Database | PostgreSQL（本地原生） | 业务数据、Agent 状态、结果 |
| Cache/Queue | Redis（本地原生） | 缓存、任务队列 |
| Storage | MinIO（本地原生） | 上传数据文件 |
| Sandbox | Docker | Python 安全执行 |
| Observability | 自研 Agent Trace（SSE + agent_steps/tool_calls） | Token / Latency / Cost |
| Deployment | Docker Compose + Nginx（最终阶段） | 部署 |

---

## 6. Agent 架构与 LangGraph 设计

### 6.1 最终 Agent Graph
```
┌─────────────┐
│ Planner     │
└──────┬──────┘
   ┌───┼───────────┐
   ▼   ▼           ▼
Data Agent  Analysis Agent  Visualization Agent
   │        │            │
   └────────┼────────────┘
            ▼
      ┌─────────────┐
      │ Reviewer    │
      └──────┬──────┘
         ┌───┴───┐
         ▼       ▼
       PASS    FAIL
         │       └──→ Analysis
         ▼
       Report
```

### 6.2 AgentState
```python
class AgentState(TypedDict):
    user_query: str
    task_id: str
    dataset_id: str
    schema: dict
    plan: list[dict]
    completed_tasks: list[str]
    analysis_results: list[dict]
    sql_results: list[dict]
    python_results: list[dict]
    visualizations: list[dict]
    review_result: dict
    report: dict
    messages: list
    status: str
    errors: list[str]
```

### 6.3 Planner Agent
- 输入：用户自然语言问题 + 数据集元信息。
- 输出：结构化任务计划。
- 决定哪些任务需要 SQL、Python、统计分析或可视化。
- 控制任务依赖与执行顺序。
```json
{
  "tasks": [
    {"id": "task_1", "type": "data_profile"},
    {"id": "task_2", "type": "time_analysis"},
    {"id": "task_3", "type": "region_analysis"},
    {"id": "task_4", "type": "product_analysis"}
  ]
}
```

### 6.4 Data Agent
读取数据并识别 Schema；执行数据质量检查；输出 Dataset Summary。

### 6.5 Analysis Agent
- 优先使用 DuckDB/SQL 处理大表聚合。
- 复杂统计或数据变换使用 Python/Pandas。
- LLM 负责决定计算方式，不直接承担数据计算。

### 6.6 Visualization Agent
- 根据分析目标选择图表类型。
- 生成结构化 ChartSpec（含 `renderer` 字段区分 echarts / r3f）。
- 确保 x/y/z 字段来自真实数据 Schema。

### 6.7 Reviewer Agent
- 验证结论是否有证据支持。
- 检查 SQL/Python 结果是否合理。
- 检查图表是否与结论一致。
- 失败时生成 retry_tasks，最多重试 3 次。

---

## 7. Tool Calling 与执行沙箱

### 7.1 Tool Registry
```
ToolRegistry
├── dataset_profile
├── sql_execute
├── python_execute
├── dataframe_query
├── generate_chart
├── search_knowledge
└── generate_report
```

### 7.2 SQL Tool
```python
execute_sql(dataset_id: str, sql: str) -> QueryResult
```
推荐使用 DuckDB 对 CSV/Parquet 做分析，避免将完整数据集直接注入 LLM Context。

### 7.3 Python Tool
```python
execute_python(dataset_id: str, code: str, timeout: int = 30) -> ExecutionResult
```

### 7.4 Sandbox 安全边界
- Python 执行进入独立 **Docker Sandbox**（本地基础设施中唯一使用 Docker 的部分）。
- 限制 CPU、内存、执行时间和文件系统权限。
- 默认禁止网络访问。
- 数据文件以只读方式挂载；输出目录单独挂载，禁止访问宿主机敏感目录。
- 工具层增加代码/SQL 风险检测与超时控制。

---

## 8. 数据层与数据库设计

本地 PostgreSQL 原生运行，业务数据 + Agent 状态 + 后续 pgvector 知识库共用实例。

### 8.1 核心数据表

| 表 | 核心字段 | 作用 |
|----|----------|------|
| users | id, email, name | 用户（本期单默认用户，跳过鉴权） |
| datasets | id, user_id, file_name, schema, profile | 数据集 |
| dataset_columns | dataset_id, name, type, stats | 字段元数据 |
| analyses | id, user_id, dataset_id, query, status | 分析任务 |
| analysis_messages | analysis_id, role, content | 对话消息 |
| agent_runs | analysis_id, thread_id, tokens, cost | Agent 执行实例 |
| agent_steps | run_id, agent_name, input, output, duration | Trace |
| tool_calls | run_id, tool, input, output, status | 工具调用 |
| analysis_results | analysis_id, result_type, data | 分析结果 |
| visualizations | analysis_id, type, spec, data | 图表 |
| reports | analysis_id, content, format | 报告 |

### 8.2 datasets
```
id, user_id, name, file_name, file_type, file_size, storage_path,
row_count, column_count, schema, profile, status, created_at, updated_at
```

### 8.3 agent_steps
```
id, run_id, agent_name, step_type, input, output, status, duration_ms, created_at
```
Agent Trace 页面直接基于 `agent_steps + tool_calls` 构建。

---

## 9. 前端架构与可视化设计

### 9.1 前端目录（pnpm monorepo）
```
web/                         # = apps/web
├── app/
│ ├── page.tsx
│ ├── dashboard/
│ ├── datasets/
│ ├── analysis/
│ ├── visualization/
│ ├── reports/
│ └── settings/
├── components/
│ ├── layout/
│ ├── chat/
│ ├── dataset/
│ ├── charts/               # ECharts + r3f 分发
│ ├── three/                # react-three-fiber 3D 组件
│ └── agent/
├── hooks/
├── stores/
├── types/
└── utils/
```
共享类型在 `packages/shared-types`、`packages/chart-schema` 中定义，前端通过 `workspace:*` 依赖引用。

### 9.2 Analysis Workspace
```
┌────────────┬────────────────────────────┬───────────────┐
│ Dataset    │ Chat / Agent              │ Data Insight │
│ sales.csv  │ User: 分析销售下降...     │ Rows         │
│ Schema     │ Agent: 正在分析...        │ Columns      │
│            │ ✓ Data profiling          │ Missing      │
│            │ ⟳ Region analysis         │ Chart        │
│            │ [输入问题................] │              │
└────────────┴────────────────────────────┴───────────────┘
```

### 9.3 ChartSpec（扩展）
```python
class ChartSpec(BaseModel):
    renderer: Literal["echarts", "r3f"]   # 新增：区分 2D/3D 渲染器
    type: str          # line/bar/scatter/heatmap 或 3d_scatter/3d_bar/3d_map
    title: str
    x_field: str
    y_field: str
    z_field: Optional[str]      # 3D 新增
    data: list[dict]
```
前端 `components/charts/` 按 `renderer` 分发：ECharts 用 `echarts-for-react`；3D 用 **react-three-fiber + drei** 封装 `Scatter3D / Bar3D / Map3D` 组件。避免 LLM 直接生成 HTML/JS。

---

## 10. API 与实时通信设计

### 10.1 Dataset API
```
POST   /api/v1/datasets
GET    /api/v1/datasets
GET    /api/v1/datasets/{id}
DELETE /api/v1/datasets/{id}
```

### 10.2 Analysis API
```
POST   /api/v1/analyses
GET    /api/v1/analyses
GET    /api/v1/analyses/{id}
DELETE /api/v1/analyses/{id}
POST   /api/v1/analyses/{id}/run
POST   /api/v1/analyses/{id}/resume
GET    /api/v1/analyses/{id}/status
GET    /api/v1/analyses/{id}/trace
```

### 10.3 SSE
第一版推荐 SSE，Agent 主要是后端向前端单向推送执行事件。
```
GET /api/v1/analyses/{id}/stream
```

### 10.4 Agent Event
```typescript
type AgentEvent =
  | { type: "agent_start"; agent: string }
  | { type: "agent_end"; agent: string }
  | { type: "tool_start"; tool: string }
  | { type: "tool_end"; tool: string; result: unknown }
  | { type: "message"; content: string }
  | { type: "chart"; spec: ChartSpec }
  | { type: "interrupt"; payload: unknown }
  | { type: "error"; message: string }
```

---

## 11. Memory、Checkpoint 与 Human-in-the-loop

### 11.1 Memory
| 类型 | 内容 | 实现 |
|------|------|------|
| Short-term | 当前分析、消息、Agent State | LangGraph thread/checkpoint |
| Long-term | 用户偏好、历史摘要 | PostgreSQL / Store |
| Knowledge | 业务文档、产品手册 | PostgreSQL + pgvector（V2） |

### 11.2 Checkpoint
- 每个分析任务绑定 thread_id。
- 关键 Node 完成后持久化 State（PostgreSQL 后端）。
- 异常后从最近 Checkpoint 恢复；支持查看历史执行状态。

### 11.3 Human-in-the-loop
```
Agent → Risk Detection → interrupt() → Frontend Approval UI
├── Reject
└── Approve → resume() → Continue Graph
```
高风险操作：外部数据库写操作、文件删除、大量资源消耗的执行任务等。

---

## 12. RAG 与知识库扩展
- RAG 作为 V2 能力，不作为第一阶段主线。
- 优先 PostgreSQL + pgvector（个人项目阶段不强制 Milvus）。
- 知识库补充业务规则、产品说明、指标定义等非结构化信息。
- 最终结论区分"数据证据"和"知识库证据"。

---

## 13. Observability 与 Evaluation

### 13.1 Agent Trace
每次分析运行以 SSE 事件流驱动，`_build_trace` 规整为 AgentRun / AgentStep / ToolCall 落 PostgreSQL；前端以执行时间线展示 Agent / Tool 调用、Token、耗时与成本。实现为自研方案（未引入第三方可观测平台）。

### 13.2 Evaluation 数据集
```
evals/
├── datasets/  (basic.json, complex.json, edge_cases.json)
└── evaluators/ (correctness.py, tool_usage.py, visualization.py, report.py)
```

### 13.3 指标
| 指标 | 说明 | 目标 |
|------|------|------|
| Task Success Rate | 完整任务成功率 | ≥ 85% |
| Tool Success Rate | 工具正确调用率 | ≥ 90% |
| Analysis Correctness | 分析结果正确率 | ≥ 90% |
| Chart Correctness | 图表字段/数据正确率 | ≥ 95% |
| Reviewer Pass Rate | 首次 Review 通过率 | 持续优化 |
| Average Latency | 单任务平均延迟 | 持续优化 |
| Average Cost | 单任务模型成本 | 可控 |

---

## 14. 安全、可靠性与成本控制

### 14.1 安全
- 上传文件白名单与大小限制。
- SQL 只读模式；禁止 DROP/DELETE/UPDATE（除非明确授权）。
- Python 运行在隔离 Docker Sandbox。
- 默认关闭 Sandbox 网络。
- 用户只能访问自己的 Dataset（本期单用户，预留约束）。
- LLM API Key 仅保存在后端环境变量（`.env`），不进入前端。

### 14.2 可靠性
- Agent 最大步骤数限制；Reviewer 最大重试 3 次。
- Tool Timeout；LLM Timeout + Retry；每步保存 Trace；Checkpoint 支持失败恢复。

### 14.3 成本控制
- 数据计算优先本地 DuckDB/Pandas，不把原始数据发送给 LLM。
- **小模型处理 Schema/简单任务，大模型处理复杂规划和最终总结**（provider 抽象下配置 SMALL_MODEL / LARGE_MODEL）。
- 缓存重复 Dataset Profile；限制单任务最大 Token、Tool Calls、运行时间。
- 记录每任务 Token/Cost。

---

## 15. 项目目录结构（pnpm monorepo）

```
insightflow/
│
├── apps/
│ ├── web/              # 前端 (Next.js + TS + Tailwind, pnpm)
│ │ ├── app/
│ │ ├── components/
│ │ ├── hooks/
│ │ ├── stores/
│ │ └── lib/
│ │
│ └── api/              # 后端 (FastAPI, venv)
│   ├── api/
│   ├── agent/
│   │ ├── graph.py
│   │ ├── state.py
│   │ ├── nodes/
│   │ ├── tools/
│   │ └── prompts/
│   ├── services/
│   ├── models/
│   ├── schemas/
│   ├── repositories/
│   └── core/
│     └── llm/          # LLM provider 抽象（D6）
│
├── sandbox/            # Python 执行 Docker 沙箱
├── packages/
│ ├── shared-types/
│ └── chart-schema/
├── infra/
│ ├── docker/          # 最终 Docker 化
│ └── nginx/
├── evals/
├── docs/
├── pnpm-workspace.yaml
├── docker-compose.yml # 最终部署
├── .env.example
├── README.md
└── Makefile
```

---

## 16. 开发阶段与里程碑

| 阶段 | 周期 | 主要任务 | 验收标准 |
|------|------|----------|----------|
| Phase 0 | Day 1 | 脚手架、本地 PG/Redis/MinIO、venv | 本地环境可启动 |
| Phase 1 | Week 1 | Dataset、上传、Profiling | CSV 可上传并查看 Schema |
| Phase 2 | Week 2 | 单 Agent + SQL/Python Tool | 自然语言问题可完成真实计算 |
| Phase 3 | Week 3 | LangGraph、State、Checkpoint、SSE | 任务可流式执行并恢复 |
| Phase 4 | Week 4-5 | Planner + Multi-Agent + Reviewer | 完整 Agent Workflow 跑通 |
| Phase 5 | Week 6 | ECharts + react-three-fiber | 自动生成 2D/3D 可视化 |
| Phase 6 | Week 7 | Agent Trace（SSE + 落库） | 可查看完整 Agent 执行过程 |
| Phase 7 | Week 8 | Report、分享、导出 | 生成完整分析报告 |
| Phase 8 | Week 9 | Evaluation | 有可重复评测数据集和指标 |
| Phase 9 | Week 10 | 部署与优化 | 公网可访问、稳定运行 |

### 16.1 开发原则
- 先跑通数据计算，再做 Agent。
- 先单 Agent，再 Multi-Agent。
- 先 ECharts，再 react-three-fiber。
- 先 MVP，再 Observability/Evaluation。
- 每完成一个阶段都保持可运行。

---

## 17. MVP 范围控制

### 17.1 MVP 必须包含
CSV Upload、Data Profiling、DuckDB、SQL Tool、Python Tool、Single Agent Loop、LangGraph、State、SSE Streaming、基本 ECharts。

### 17.2 第一版明确不做
复杂企业权限/RBAC、多租户、实时数据库同步、大规模分布式计算、复杂 RAG、Milvus、10+ Agent、复杂 GIS 3D、模型训练。

> 做到 Phase 4 即可作为秋招主项目；做到 Phase 6-9 则作为作品集核心项目（本期目标为完整 Phase 1-10）。

---

## 18. 测试方案

### 18.1 Backend（Pytest）
- Dataset Service、Tool、Agent Node、API。
- SQL Tool：正常查询、空结果、错误 SQL、超时。
- Python Sandbox：恶意代码、超时、内存限制。

### 18.2 Frontend（Vitest / Playwright）
- Vitest：ChartSpec、状态管理、工具函数。
- Playwright：上传 → 创建分析 → 查看结果 → 查看 Trace → 查看报告。

### 18.3 Agent Evaluation
- 固定问题 + 固定数据集；记录预期 Tool；验证 SQL/计算结果、ChartSpec 字段、最终报告是否引用真实证据。

---

## 19. 部署方案

### 19.1 本地开发（本期）
- 前端：`pnpm dev`（apps/web）。
- 后端：venv 内 `uvicorn app.api.main:app --reload`（apps/api）。
- 基础设施：本地原生 PostgreSQL / Redis / MinIO + Docker Python 沙箱。
- 配置：`.env.example` 拷贝为 `.env`，填入本地连接串与 LLM API Key。

### 19.2 最终服务（Docker Compose）
| Service | Container | 用途 |
|---------|-----------|------|
| web | Next.js | 前端 |
| api | FastAPI | 后端 |
| postgres | PostgreSQL | 业务数据/状态 |
| redis | Redis | 缓存/队列 |
| minio | MinIO | 文件存储 |
| sandbox | Python Docker | 代码执行 |
| nginx | Nginx | 反向代理 |

### 19.3 线上部署
```
Browser → HTTPS → Nginx
├── / → Next.js
└── /api → FastAPI
├── PostgreSQL / Redis / MinIO / Sandbox
```
个人项目阶段部署到一台云服务器；后续再拆分 Agent Worker、Sandbox Worker 等服务。

---

## 20. 秋招项目亮点与面试准备

### 20.1 简历定位
**InsightFlow — AI Data Analysis & Visualization Agent**

### 20.2 核心亮点
- 基于 LangGraph + FastAPI + Next.js 构建具备任务规划、工具调用、多 Agent 协作、结果审查与状态持久化能力的数据分析 Agent。
- Planner–Data–Analysis–Visualization–Reviewer 工作流，支持 SQL/Python/DuckDB 工具调用、失败重试与 Human-in-the-loop。
- 结构化 ChartSpec 驱动 ECharts / react-three-fiber，实现 Agent 自动选择并生成 2D/3D 交互式可视化。
- 自研 Agent Trace（SSE 事件 → agent_steps/tool_calls 落库）记录每次运行的工具调用、Token、Latency 与成本。
- 本地 venv + Docker 沙箱隔离 Agent 生成代码执行；PostgreSQL + Redis + MinIO 容器化部署。

### 20.3 面试必须能讲清楚的问题
- 为什么需要 Agent Loop，而不是一次 LLM 调用？
- State 在 Agent 中解决什么问题？为什么使用 LangGraph？
- Planner 与普通 Prompt 有什么区别？
- 为什么 LLM 不应该直接计算大 CSV？DuckDB 的作用？
- 如何防止 Agent 执行恶意 Python？（Docker 沙箱）
- Reviewer 如何判断分析结果是否可靠？
- 为什么 ChartSpec 比让 LLM 直接生成 HTML 更可靠？
- Checkpoint 如何支持任务恢复？SSE 和 WebSocket 如何选择？
- 如何控制 Agent Token、Latency 和 Cost？（小/大模型分工、本地计算）
- 如何评价一个 Agent 是否真的比普通 Chain 好？

---

## 附录 A：从零开始的实际开发顺序

| 步骤 | 任务 | 完成标准 |
|------|------|----------|
| 01 | 初始化 monorepo | Next.js(pnpm) + FastAPI(venv) + 本地 PG |
| 02 | 完成 Dataset | CSV 上传、MinIO、PostgreSQL、Schema |
| 03 | 接入 DuckDB | CSV 注册、SQL 查询、DataFrame |
| 04 | 实现 SQL Tool | 只读 SQL + Timeout |
| 05 | 实现 Python Tool | Docker Sandbox |
| 06 | 完成 Single Agent | 自然语言 → Tool → Answer |
| 07 | 迁移 LangGraph | StateGraph + Checkpoint |
| 08 | 加入 Planner | 任务拆解 |
| 09 | 加入 Data/Analysis Agent | 数据理解 + 分析 |
| 10 | 加入 Visualization Agent | ChartSpec + ECharts |
| 11 | 加入 Reviewer | 验证 + Retry |
| 12 | 加入 react-three-fiber | 3D 数据探索 |
| 13 | 加入 Agent Trace | SSE + agent_steps |
| 14 | 加入 Evaluation | Golden Dataset + Evaluator |
| 15 | 生成 Report | HTML/PDF |
| 16 | Docker 化 | 一键启动 |
| 17 | 云服务器部署 | Nginx + HTTPS |

---

## 附录 B：最终验收标准
1. 用户可以上传一个真实 CSV 数据集。
2. 系统能够自动完成 Schema 和数据质量分析。
3. 用户可以使用自然语言提出分析问题。
4. Agent 能自主选择 SQL/Python Tool。
5. Agent 能通过 LangGraph 管理多步任务。
6. Agent 能流式输出执行过程。
7. Reviewer 能发现明显的分析证据不足并触发重试。
8. 系统能生成至少 4 类 ECharts 图表。
9. 系统能生成至少 2 类 react-three-fiber 3D 可视化。
10. 系统能生成结构化分析报告。
11. 用户能查看 Agent Trace。
12. 系统能记录 Token、Latency、Cost。
13. 系统有至少一组固定 Evaluation Dataset。
14. 整个系统可以通过 Docker Compose 启动。
15. 线上环境可以完整跑通一次从上传到报告生成的流程。
