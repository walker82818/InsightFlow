"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Service
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # CORS allowed origins（部署时用 CORS_ORIGINS 覆盖，JSON 数组格式：
    # CORS_ORIGINS=["http://localhost:3000","https://your.domain"])
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # PostgreSQL (async)
    database_url: str = (
        "postgresql+asyncpg://insightflow:insightflow@localhost:5432/insightflow"
    )

    # Redis (Phase 6+)
    redis_url: str = "redis://localhost:6379/0"

    # MinIO (Phase 5+ storage backend, optional)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "insightflow"

    # Dataset storage (Phase 1)
    # storage_backend: "local" (本地文件系统, 默认, 免 MinIO 即可运行)
    #                  | "minio" (需本地运行 MinIO)
    storage_backend: str = "local"
    upload_dir: str = "data/uploads"
    max_upload_size: int = 50 * 1024 * 1024  # 50 MB
    allowed_extensions: list[str] = ["csv", "xlsx", "xls", "json"]
    preview_rows: int = 50

    # 鉴权（本期跳过）：固定单默认用户
    default_user_id: str = "00000000-0000-0000-0000-000000000001"

    # 认证 (Phase: registration + JWT login). 用于签发/校验 access token.
    auth_secret_key: str = "insightflow-dev-secret-change-me"
    auth_algorithm: str = "HS256"
    auth_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Python sandbox (Docker)
    sandbox_docker_image: str = "insightflow-sandbox:latest"
    sandbox_timeout: int = 30
    # 安全开关：当 Docker 镜像不存在时，是否允许用「服务器同权限的本地进程」跑
    # LLM 生成的任意代码。默认 False = 安全（禁用 python 工具，避免 RCE）。
    # 仅开发机且明确信任输入时才可临时置 True。
    sandbox_allow_local_fallback: bool = False

    # DuckDB analysis engine (Phase 2)
    # File-backed in-memory-style OLAP store; tables persist across restarts.
    duckdb_path: str = "data/insightflow.duckdb"
    max_sql_rows: int = 200  # cap rows returned to the LLM / frontend

    # Agent loop (Phase 3, LangGraph)
    agent_max_steps: int = 6  # max ReAct steps inside the analysis node
    agent_max_retries: int = 2  # Reviewer 触发重分析（ReAct 内循环）的最大轮次
    max_chart_rows: int = 200  # rows fed into a generated ChartSpec
    # 根因分析「变化显著性门槛」（Design D5）：环比变化幅度低于此值即拒答，
    # 避免对无意义波动强行编造根因。
    root_cause_min_delta: float = 0.05
    # 全局分析墙钟超时（秒）：兜底防止 LLM 慢/死循环导致 SSE 无限挂起。
    # 单个工具调用另有 sandbox_timeout 限制；此项覆盖整条 pipeline。
    agent_total_timeout: int = 180
    # 单次 LLM 调用超时（秒）：防止偶发 API 挂起（网络抖动 / 服务端慢）吞掉整条
    # pipeline 的墙钟预算——历史失败案例中单次调用挂起直接耗尽 180s。
    llm_call_timeout: int = 120

    # Python sandbox (Docker) — overrides in .env if needed
    sandbox_memory: str = "512m"
    sandbox_cpus: float = 1.0
    # image built from /sandbox/Dockerfile: `docker build -t insightflow-sandbox ./sandbox`

    # LLM provider abstraction (default: domestic models, OpenAI-compatible)
    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    small_model: str = "deepseek-chat"
    large_model: str = "deepseek-reasoner"

    # Artifact 无头截图（P2）：主应用 runtime.html 地址与导出默认截图宽度。
    # 本地开发默认指向 web dev server；容器/部署时改为主应用地址。
    artifact_runtime_url: str = "http://127.0.0.1:3000/_artifacts/runtime.html"
    artifact_shot_width: int = 960

    # Trace cost estimation (Phase 6): rough price per 1K tokens (USD).
    trace_cost_per_1k_prompt: float = 0.001
    trace_cost_per_1k_completion: float = 0.002

    # Optional Langfuse observability (Phase 6). Leave empty to disable.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
