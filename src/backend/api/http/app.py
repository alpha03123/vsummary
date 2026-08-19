"""FastAPI 应用工厂与全局 app 实例。

负责创建 FastAPI 应用、安装访问日志过滤、挂载 API 路由与前端静态资源，
并作为 uvicorn 的入口点。
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request

from backend.api.http.access_log import install_access_log_filters
from backend.api.di.bootstrap import ApiContainer
from backend.api.di.container import build_default_container
from backend.api.routes.agent import router as agent_router
from backend.api.routes.chaoxing import router as chaoxing_router
from backend.api.routes.health import router as health_router
from backend.api.routes.linked import router as linked_router
from backend.api.routes.settings import router as settings_router
from backend.api.routes.videos import router as videos_router
from backend.api.http.static_assets import mount_frontend_dist
from backend.mcp.video_series_server import install_mcp_http_endpoint
from backend.shared.observability import bind_request_id, close_application_logging, configure_application_logging


LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_server = getattr(app.state, "mcp_server", None)
    try:
        if mcp_server is None:
            yield
        else:
            async with mcp_server.session_manager.run():
                yield
    finally:
        root_dir = getattr(getattr(app.state, "container", None), "root_dir", None)
        if root_dir is not None:
            close_application_logging(root_dir)


def include_api_routers(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(settings_router)
    app.include_router(videos_router)
    app.include_router(agent_router)
    app.include_router(linked_router)
    app.include_router(chaoxing_router)


def create_app(container: ApiContainer | None = None) -> FastAPI:
    """构建并配置 FastAPI 应用实例。

    按顺序完成以下初始化步骤：
    1. 安装 uvicorn 访问日志过滤器（屏蔽高频轮询路径）
    2. 创建 FastAPI 应用（title="video_include api"）
    3. 将依赖容器注入到 ``app.state.container``
    4. 注册所有 API 路由
    5. 若 root_dir 已知，挂载前端静态资源分发

    Args:
        container: 可选的自定义依赖容器；若为 None 则使用默认容器。

    Returns:
        已完成初始化的 FastAPI 应用实例，可直接传给 ``uvicorn.run()``。
    """
    resolved_container = container or build_default_container()
    root_dir = getattr(resolved_container, "root_dir", None)
    if root_dir is not None:
        configure_application_logging(root_dir)
    install_access_log_filters()
    application = FastAPI(title="video_include api", lifespan=lifespan)
    application.state.container = resolved_container
    include_api_routers(application)
    install_mcp_http_endpoint(application)
    if root_dir is not None:
        mount_frontend_dist(application, root_dir)

    @application.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        started_at = time.perf_counter()
        with bind_request_id(request_id):
            try:
                response = await call_next(request)
            except Exception:
                LOGGER.exception(
                    "request failed",
                    extra={"event": "request_failed", "method": request.method, "path": request.url.path},
                )
                raise
            duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
            LOGGER.info(
                "request completed",
                extra={
                    "event": "request_completed",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            response.headers["X-Request-ID"] = request_id
            return response
    return application


app = create_app()
