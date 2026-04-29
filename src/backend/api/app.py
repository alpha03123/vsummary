from __future__ import annotations

from fastapi import FastAPI

from backend.api.bootstrap import ApiContainer
from backend.api.container import build_default_container
from backend.api.routes import include_api_routers


def create_app(container: ApiContainer | None = None) -> FastAPI:
    application = FastAPI(title="video_include api")
    application.state.container = container or build_default_container()
    include_api_routers(application)
    return application


app = create_app()
