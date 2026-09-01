# InsightFlow

> AI 数据分析与可视化 Agent —— 上传数据、用自然语言提问，自动完成 SQL/Python 分析、交互式可视化与可解释报告。

InsightFlow 是开源的 AI 数据分析平台：由 LangGraph 多智能体（Planner / Data / Analysis / Visualization / Reviewer）协同驱动，把"分析数据"变成一场对话。**免注册、免登录**，部署后打开即用。

## 特性

- **自然语言分析**：LangGraph 多 Agent 编排，Planner 拆解任务，Analysis 节点内 ReAct 循环，SQL（DuckDB 只读）+ Python 双工具真实执行
- **Agent2UI 可视化**：Agent 直接生成可执行 TSX，在严格隔离的沙箱 iframe（esbuild-wasm 编译，React / echarts / three 走 CDN）中渲染，图表数据由真实计算结果驱动，杜绝 LLM 臆造数字
- **证据链与根因分析**：每条结论挂接可追溯证据（SQL/Python 结果、置信度、来源），根因分析自动分解贡献因子并给出置信度
- **可分享报告**：AI 生成结构化报告（执行摘要 / 关键发现 / 行动建议 / 局限说明），一键导出 HTML / Markdown / PDF
- **可观测性**：每次运行持久化 Agent 轨迹（步骤、工具调用、耗时、Token 费用），前端可视化回放
- **评测体系**：内置 golden dataset 自动跑分（任务成功率 / 工具使用 / 图表 / 报告质量 / 延迟 / 成本）
- **一键部署**：`docker compose up -d --build` 启动 web + api + PostgreSQL；可选 MinIO 对象存储与 Docker 代码沙箱

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Next.js 16 + React 19 + TypeScript + Tailwind CSS v4 |
| 可视化 | Agent2UI：TSX 运行时沙箱（esbuild-wasm）+ 内置 echarts / three |
| 后端 | FastAPI + SQLAlchemy（async）+ uvicorn |
| Agent | LangGraph + Pydantic（多 Agent 编排） |
| LLM | OpenAI 兼容 provider 抽象，默认 DeepSeek（small / large 双模型） |
| 数据库 | PostgreSQL（业务元数据）+ DuckDB（分析引擎） |
| 沙箱 | Docker（LLM 生成 Python 的隔离执行，开发机可本地降级） |
| 部署 | Docker Compose（web / api / db / minio） |

## 快速开始

### 方式一：Docker Compose 一键部署（推荐）

需要 Docker Engine 20.10+ / Compose v2。

```bash
# 1) 配置环境变量（至少填入 LLM_API_KEY）
cp .env.example .env

# 2) 构建并启动（web :3000 / api :8000 / db）
docker compose up -d --build

# 3) 访问
#    前端 → http://localhost:3000
#    后端 → http://localhost:8000/health
```

首次启动会自动完成 PostgreSQL 建表（SQLAlchemy `create_all`），无需手工迁移。完整指南（MinIO 对象存储、代码沙箱、故障排查）见 [DEPLOYMENT.md](DEPLOYMENT.md)。

### 方式二：本地开发

前置：Node 20+ / pnpm 10+、Python 3.12+、PostgreSQL（本机 5432）。

```bash
# 前端
pnpm install
pnpm dev                          # http://localhost:3000

# 后端
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
cp ../../.env.example .env        # 填入 LLM_API_KEY
uvicorn app.main:app --reload --port 8000
```

> PostgreSQL 初始化（首次）：
>
> ```sql
> CREATE ROLE insightflow WITH LOGIN PASSWORD 'insightflow';
> CREATE DATABASE insightflow OWNER insightflow;
> ```

## 使用流程

1. **数据集**：上传 CSV / Excel / JSON，自动校验、识别 Schema 并生成字段统计
2. **分析**：在对话工作台选择数据表、用自然语言提问，实时观察 Agent 步骤、SQL/Python 调用与图表生成
3. **报告**：分析完成后自动生成结构化报告，支持下载 HTML / Markdown 或打印为 PDF
4. **评测**：`cd apps/api && python -m evals.cli` 用 golden 数据集自动跑分（详见 `apps/api/evals/`）

## 项目结构

```
insightflow/
├── apps/
│   ├── web/                # Next.js 前端 + Agent2UI 渲染运行时
│   └── api/                # FastAPI 后端（agent / services / models / schemas / evals）
├── packages/
│   └── artifact-schema/    # Agent2UI Artifact 类型定义
├── sandbox/                # LLM 生成 Python 的 Docker 沙箱（runner + Dockerfile）
├── docs/plans/             # 设计与阶段文档
├── docker-compose.yml      # 一键部署编排（web / api / db / minio）
├── .env.example            # 环境变量模板
└── LICENSE                 # MIT License
```

## 配置

主要环境变量见 [.env.example](.env.example)：

| 变量 | 说明 | 默认 |
|---|---|---|
| `LLM_API_KEY` | **必填**，LLM 服务商 API Key | - |
| `LLM_BASE_URL` | OpenAI-compatible 基地址 | `https://api.deepseek.com/v1` |
| `LLM_SMALL_MODEL` / `LLM_LARGE_MODEL` | 小 / 大模型 | `deepseek-chat` / `deepseek-reasoner` |
| `POSTGRES_USER/PASSWORD/DB` | 数据库账号 / 密码 / 库名 | `insightflow` |
| `STORAGE_BACKEND` | 对象存储：`local` 或 `minio` | `local` |
| `LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST` | 可观测性（留空则关闭） | 空 |

> 生产环境建议修改 `POSTGRES_PASSWORD` 默认值，并妥善保管 `LLM_API_KEY`。

## 文档

- 总体设计：`docs/plans/2026-08-10-insightflow-design.md`
- Agent2UI 可视化设计：`docs/plans/2026-08-29-agent2ui-design.md`
- 部署指南：`DEPLOYMENT.md`

## License

[MIT](LICENSE) © 2026 walker82818
