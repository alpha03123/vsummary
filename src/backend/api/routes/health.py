"""健康检查路由。

提供系统存活探针，供前端和运维工具判断后端是否正常运行。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import OperationalError

from backend.api.dependencies import WorkspaceServicesDep
from backend.api.schemas.responses import HealthResponse

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
def health(container: WorkspaceServicesDep) -> HealthResponse:
    """GET /api/health — 系统健康检查。

    只有 API 与其 SQL 权威存储均可读时才返回成功，避免数据库已经中断但
    前端继续把服务当作可用状态。

    Returns:
        HealthResponse，含 status="ok"。
    """
    try:
        container.check_health()
    except OperationalError as error:
        raise HTTPException(status_code=503, detail="数据服务暂不可用，正在恢复连接。") from error
    return HealthResponse(status="ok")
