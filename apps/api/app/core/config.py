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

    # Python sandbox (Docker)
    sandbox_docker_image: str = "insightflow-sandbox:latest"
    sandbox_timeout: int = 30

    # DuckDB analysis engine (Phase 2)
    # File-backed in-memory-style OLAP store; tables persist across restarts.
    duckdb_path: str = "data/insightflow.duckdb"
    max_sql_rows: int = 200  # cap rows returned to the LLM / frontend

    # LLM provider abstraction (default: domestic models, OpenAI-compatible)
    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    small_model: str = "deepseek-chat"
    large_model: str = "deepseek-reasoner"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
