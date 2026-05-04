from __future__ import annotations

from fastapi import FastAPI

from backend.api.access_log import install_access_log_filters
from backend.api.bootstrap import ApiContainer
from backend.api.container import build_default_container
from backend.api.routes import include_api_routers
from backend.api.static_assets import mount_frontend_dist


def create_app(container: ApiContainer | None = None) -> FastAPI:
    install_access_log_filters()
    application = FastAPI(title="video_include api")
    resolved_container = container or build_default_container()
    application.state.container = resolved_container
    include_api_routers(application)
    root_dir = getattr(resolved_container, "root_dir", None)
    if root_dir is not None:
        mount_frontend_dist(application, root_dir)
    return application


app = create_app()
