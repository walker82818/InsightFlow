"""Artifact 截图 API（P2）。

- ``POST /api/v1/artifacts/shot``：渲染单个 ArtifactSpec 并返回 PNG，
  供前端「保存为图片」与报告快照复用。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import logging

from app.services.artifact_shooter import shot_artifact

logger = logging.getLogger("insightflow")

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


class ArtifactShotRequest(BaseModel):
    code: str
    data: Any = None
    theme: str = "light"
    width: int = 960
    title: str = ""


@router.post("/shot")
async def shot_artifact_endpoint(payload: ArtifactShotRequest) -> Response:
    """渲染单个 ArtifactSpec 并返回 PNG 字节流。"""
    try:
        png = await shot_artifact(
            payload.model_dump(exclude_none=True),
            width=payload.width,
        )
    except Exception as exc:  # noqa: BLE001 - 返回对客户端友好的错误
        logger.error("artifact shot failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=f"artifact 截图服务暂不可用（{type(exc).__name__}）：{exc}",
        ) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
