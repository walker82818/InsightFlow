"""InsightFlow FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.models import Analysis, Dataset, DatasetColumn, User  # noqa: F401  (register models)

logger = logging.getLogger("insightflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1: create tables on startup (dev-friendly; later -> Alembic).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="InsightFlow API",
    description="AI Data Analysis & Visualization Agent backend.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局兜底异常处理：完整异常写日志，客户端只拿到通用 500，不泄漏内部细节。"""
    logger.exception(
        "unhandled error on %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error"},
    )


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {
        "status": "ok",
        "service": "insightflow-api",
        "version": "1.0.0",
        "llm_provider": settings.llm_provider,
    }


@app.get("/health/db", tags=["health"])
async def health_db() -> dict:
    """Verify connectivity to PostgreSQL via a trivial query."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "database": "unreachable", "detail": str(exc)}
