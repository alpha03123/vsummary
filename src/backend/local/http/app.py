"""Local API application factory."""

from __future__ import annotations

from backend.api.common.app import create_app as create_common_app
from backend.api.di.bootstrap import ApiContainer
from backend.api.http.static_assets import mount_frontend_dist
from backend.local.routes.cookie_login import router as cookie_login_router
from backend.local.routes.chaoxing import router as chaoxing_router
from backend.local.routes.local_import import router as local_import_router
from backend.local.routes.legacy_migration import router as legacy_migration_router
from backend.local.routes.settings import router as settings_router
from backend.mcp.video_series_server import install_mcp_http_endpoint


def create_app(container: ApiContainer):
    """Build the Local application with Local-only routes and MCP endpoint."""

    application = create_common_app(container)
    application.include_router(settings_router)
    application.include_router(cookie_login_router)
    application.include_router(local_import_router)
    application.include_router(legacy_migration_router)
    application.include_router(chaoxing_router)
    install_mcp_http_endpoint(application)
    root_dir = getattr(container, "root_dir", None)
    if root_dir is not None:
        mount_frontend_dist(application, root_dir)
    return application
