"""Product-neutral FastAPI application factory."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager, contextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from backend.api.di.bootstrap import ApiContainer
from backend.api.common.capabilities import router as capabilities_router
from backend.api.common.access_log import install_access_log_filters
from backend.api.routes.agent import router as agent_router
from backend.api.routes.health import router as health_router
from backend.api.routes.jobs import router as jobs_router
from backend.api.routes.linked import router as linked_router
from backend.api.routes.videos import router as videos_router
from backend.api.routes.usage import router as usage_router
from backend.api.routes.preferences import router as preferences_router
from backend.api.routes.chat_queue import router as chat_queue_router
from backend.api.routes.import_preview import router as import_preview_router
from backend.core.request_context import bind_workspace_context
from backend.core.context import WorkspaceContext
from backend.core.preferences import bind_user_preferences
from backend.core.metering import bind_resource_budget
from backend.core.concurrency import bind_request_limiter
from backend.core.job_queue import JobQueueFull
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
        client = getattr(getattr(app.state, "container", None), "model_http_client", None)
        if client is not None:
            client.close()
        if root_dir is not None:
            close_application_logging(root_dir)


def include_common_routers(app: FastAPI) -> None:
    app.include_router(capabilities_router)
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(videos_router)
    app.include_router(agent_router)
    app.include_router(linked_router)
    app.include_router(usage_router)
    app.include_router(preferences_router)
    app.include_router(chat_queue_router)
    app.include_router(import_preview_router)


def create_app(container: ApiContainer) -> FastAPI:
    """Create an app containing only public Core routes and lifecycle hooks."""

    root_dir = getattr(container, "root_dir", None)
    if root_dir is not None:
        configure_application_logging(root_dir)
    install_access_log_filters()
    application = FastAPI(title="VSummary Core API", lifespan=lifespan)
    application.state.container = container
    include_common_routers(application)

    @application.exception_handler(JobQueueFull)
    async def queue_full(_request: Request, error: JobQueueFull) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(error)})

    @application.exception_handler(OperationalError)
    async def database_unavailable(_request: Request, _error: OperationalError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "数据服务暂不可用，正在恢复连接。"})

    @application.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id
        container = getattr(request.app.state, "container", None)
        context_provider = getattr(container, "context_provider", None)
        context = getattr(request.state, "workspace_context", None)
        if not isinstance(context, WorkspaceContext):
            context = context_provider.get_context(request_id=request_id) if context_provider is not None else None
        if context is not None:
            request.state.workspace_context = context
        started_at = time.perf_counter()
        store = getattr(container, "preference_store", None)
        preferences = store.get(context) if store is not None and context is not None else None
        with bind_request_id(request_id), bind_request_limiter(getattr(container, "request_limiter", None)), bind_workspace_context(context) if context is not None else _null_context(), bind_user_preferences(preferences, getattr(container, "model_profiles", {})), bind_resource_budget(getattr(container, "resource_budget", None), request_id):
            try:
                response = await call_next(request)
            except Exception:
                LOGGER.exception(
                    "request failed",
                    extra={"event": "request_failed", "method": request.method, "path": request.url.path},
                )
                raise
            LOGGER.info(
                "request completed",
                extra={
                    "event": "request_completed",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                },
            )
            response.headers["X-Request-ID"] = request_id
            return response

    return application


@contextmanager
def _null_context():
    yield
