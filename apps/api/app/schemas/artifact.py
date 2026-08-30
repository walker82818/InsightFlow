"""Agent2UI artifact API schemas (P1).

ArtifactSpec 契约与 ``packages/artifact-schema``（TS/zod）对齐：
Agent 生成单文件 React TSX，前端在严格隔离 iframe 内编译渲染。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ArtifactError(BaseModel):
    """iframe 回传的渲染/编译错误。"""

    message: str
    line: int | None = None
    column: int | None = None


class ArtifactSpec(BaseModel):
    """Agent 输出的可执行 UI 规格。"""

    title: str = ""
    code: str = Field(
        ...,
        min_length=1,
        description="单文件 React TSX 源码，默认导出 App({ data, theme })",
    )
    imports: list[str] = Field(default_factory=list)
    data: Any = None
    theme: str | None = None


class ArtifactRepairRequest(BaseModel):
    """自愈请求：上次的 spec + iframe 报错（attempt 由前端记录，1..3）。"""

    spec: ArtifactSpec
    error: ArtifactError
    attempt: int = Field(1, ge=1, le=3)


class ArtifactRepairResponse(BaseModel):
    repaired: bool
    spec: ArtifactSpec | None = None
    reason: str | None = None
