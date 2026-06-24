"""健康检查路由。

提供系统存活探针，供前端和运维工具判断后端是否正常运行。
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.schemas.responses import HealthResponse

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """GET /api/health — 系统健康检查。

    返回固定的 `{"status": "ok"}`，用于前端轮询判断后端是否可用。

    Returns:
        HealthResponse，含 status="ok"。
    """
    return HealthResponse(status="ok")
