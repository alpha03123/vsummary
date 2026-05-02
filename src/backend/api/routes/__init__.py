from __future__ import annotations

from fastapi import FastAPI

from backend.api.routes.agent import router as agent_router
from backend.api.routes.health import router as health_router
from backend.api.routes.settings import router as settings_router
from backend.api.routes.videos import router as videos_router


def include_api_routers(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(settings_router)
    app.include_router(videos_router)
    app.include_router(agent_router)
