from __future__ import annotations

from fastapi import FastAPI

from backend.api.routes.agent import router as agent_router
from backend.api.routes.chaoxing import router as chaoxing_router
from backend.api.routes.chaoxing_downloads import router as chaoxing_downloads_router
from backend.api.routes.health import router as health_router
from backend.api.routes.linked import router as linked_router
from backend.api.routes.settings import router as settings_router
from backend.api.routes.videos import router as videos_router


def include_api_routers(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(settings_router)
    app.include_router(videos_router)
    app.include_router(agent_router)
    app.include_router(linked_router)
    app.include_router(chaoxing_router)
    app.include_router(chaoxing_downloads_router)
