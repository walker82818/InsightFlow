# InsightFlow — 部署指南（Docker）

InsightFlow 采用 **Docker Compose 一键部署**，编排 PostgreSQL、FastAPI 后端与 Next.js 前端。
目标环境：一台可访问外网（含 Docker Hub）、装有 Docker Engine 20.10+ / Docker Compose v2 的 Linux 或 macOS 主机（Windows 建议用 WSL2）。

---

## 1. 架构总览

```
                ┌────────────────────────────────────────────────┐
  浏览器 :3000 ──►  web (Next.js standalone)                     │
                │     · 静态资源 + SSR                          │
                │     · /api/* 反向代理到 api                   │
                └──────────────┬────────────────────────────────┘
                               │ BACKEND_URL=http://api:8000
                               ▼
                ┌────────────────────────────────────────────────┐
                │  api (FastAPI / uvicorn)                       │
                │     · 数据访问 · 指标分析 · 证据链 · 报告       │
                │     · DuckDB 分析引擎 (data/insightflow.duckdb)│
                │     · LLM 调用（DeepSeek / OpenAI-compatible）  │
                └──────┬───────────────┬─────────────────────────┘
                       │               │
                       ▼               ▼
                ┌────────────┐   ┌───────────────────────┐
                │ db (PG16)  │   │ data 卷 (DuckDB+上传)  │
                └────────────┘   └───────────────────────┘
```

可选服务（默认不启动）：
- **minio**（对象存储）：大数据文件存对象存储时启用。
- **代码沙箱**（`insightflow-sandbox`）：让 LLM 生成的 Python 在隔离容器中执行。

---

## 2. 一键启动

```bash
# 1) 准备环境变量
cp .env.example .env
#    编辑 .env，至少填入 LLM_API_KEY（DeepSeek 或任意 OpenAI-compatible key）

# 2) 构建并启动（web / api / db）
docker compose up -d --build

# 3) 查看状态
docker compose ps

# 4) 访问
#    前端   → http://<host>:3000
#    后端   → http://<host>:8000/health
```

启动完成后，网页会自动完成 PostgreSQL 建表（SQLAlchemy `create_all`），无需手工迁移。

---

## 3. 配置说明（`.env`）

| 变量 | 说明 | 默认 |
|---|---|---|
| `LLM_API_KEY` | **必填**，LLM 服务商 API Key | - |
| `LLM_BASE_URL` | OpenAI-compatible 基地址 | `https://api.deepseek.com/v1` |
| `LLM_SMALL_MODEL` / `LLM_LARGE_MODEL` | 小/大模型 | `deepseek-chat` / `deepseek-reasoner` |
| `POSTGRES_USER/PASSWORD/DB` | 数据库账号密码库名 | `insightflow` |
| `STORAGE_BACKEND` | 对象存储：`local` 或 `minio` | `local` |

> 生产环境建议改掉 `POSTGRES_PASSWORD` 默认值，并妥善保管 `LLM_API_KEY`。

---

## 4. 数据持久化

三个命名卷：

| 卷 | 挂载点 | 内容 |
|---|---|---|
| `postgres_data` | db 容器 `/var/lib/postgresql/data` | 元数据、报告、证据链等业务库 |
| `insightflow_data` | api 容器 `/app/data` | DuckDB 分析文件 + 本地上传 |
| `minio_data` | minio 容器 `/data` | 对象存储（仅 minio 模式） |

卷在 `docker compose down` 后依然保留；`docker compose down -v` 会清空数据，请谨慎。

---

## 5. 可选服务

### 5.1 对象存储（minio）

当数据集文件较大或希望接入 S3 生态时：

```bash
docker compose --profile minio up -d
# .env 中设置
# STORAGE_BACKEND=minio
# MINIO_ACCESS_KEY=minioadmin
# MINIO_SECRET_KEY=minioadmin
```

控制台：`http://<host>:9001`。

### 5.2 代码沙箱（LLM 生成 Python 的隔离执行）

api 默认在**无沙箱**模式下运行。若要让 LLM 生成的 Python 代码在隔离容器中执行：

```bash
# 1) 先构建沙箱镜像（sandbox/ 下有独立 Dockerfile）
docker build -t insightflow-sandbox ./sandbox

# 2) 用覆盖层启动（会为 api 挂载 Docker socket）
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up -d --build
```

> ⚠️ 安全提示：挂载 Docker socket 会让 api 进程获得宿主机 Docker 控制权，
> 仅在可信环境使用。生产环境若对安全敏感，建议用 Kubernetes / 独立执行器替代。

---

## 6. 常用运维命令

```bash
docker compose logs -f api      # 跟踪后端日志
docker compose logs -f web      # 跟踪前端日志
docker compose restart api      # 重启后端
docker compose ps               # 服务状态
docker compose down             # 停止（保留数据卷）
docker compose down -v          # 停止并清空数据
docker compose up -d --build    # 升级后重建
```

---

## 7. 单独构建 / 运行镜像

```bash
# API 镜像（独立运行，需自行提供 DATABASE_URL）
docker build -t insightflow-api ./apps/api
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://... \
  -e LLM_API_KEY=sk-... \
  -v insightflow_data:/app/data \
  insightflow-api

# Web 镜像（从仓库根构建，pnpm workspace）
docker build -f apps/web/Dockerfile -t insightflow-web .
docker run -p 3000:3000 \
  -e BACKEND_URL=http://host.docker.internal:8000 \
  insightflow-web
```

---

## 8. 故障排查

- **`db` 未就绪 / api 不断重启**：api 等待 `db` 的 healthcheck。查看 `docker compose logs api`。
- **浏览器能开前端但请求 /api 失败**：确认 web 容器能解析 `api` 服务名，`docker compose exec web wget -qO- http://api:8000/health`。
- **DuckDB 文件找不到**：确认 `insightflow_data` 卷已挂载到 `/app/data`。
- **拉取镜像超时（Docker Hub 不可达）**：为 Docker 配置 registry mirror（镜像加速）后重试。

---

## 9. 关于 SSE 流式（重要）

分析运行是 SSE 流式输出。生产部署默认走 Next 的 same-origin 反向代理
（`BACKEND_URL=http://api:8000`）。经实测，**Next 16 standalone 的 rewrites 会
透传 `text/event-stream` / chunked 响应、不缓冲**，因此默认配置下实时流式可正常工作，
无需额外设置。

若在特殊网关/代理环境下遇到流式卡顿，可让浏览器直连后端：构建镜像时设置
`NEXT_PUBLIC_API_URL` 指向浏览器可访问的后端地址：

```bash
docker compose build \
  --build-arg BACKEND_URL=http://api:8000 \
  --build-arg NEXT_PUBLIC_API_URL=http://<host>:8000 \
  web
```
> `NEXT_PUBLIC_*` 变量在**构建时**内联进前端代码；`BACKEND_URL` 在构建时烘焙进
> Next rewrites。二者按需调整。

---

## 10. 本地开发对照（无需 Docker）

```bash
# 后端
cd apps/api && .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# 前端
cd apps/web && pnpm dev
```
前端 dev 模式下通过 `next.config.ts` 的 rewrite 将 `/api` 代理到 `http://127.0.0.1:8000`。
