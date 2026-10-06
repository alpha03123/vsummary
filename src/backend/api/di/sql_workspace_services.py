"""Bounded SQL Workspace service scope shared by hosted deployments."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import RLock

from sqlalchemy import select

from backend.api.di.bootstrap import ApiContainer, build_workspace_services
from backend.core.context import WorkspaceContext
from backend.video_summary.infrastructure.persistence.models import Workspace
from backend.video_summary.infrastructure.persistence.sql_video_workspace import (
    SqlVideoWorkspace,
)


class SqlWorkspaceServicesProvider:
    def __init__(
        self,
        *,
        session_factory,
        blob_store,
        data_root: Path,
        max_cached_workspaces: int = 64,
        media_preview_enabled: bool = True,
    ):
        if max_cached_workspaces < 1:
            raise ValueError("Workspace cache size must be positive.")
        self.session_factory = session_factory
        self.blob_store = blob_store
        self.data_root = data_root
        self.max_cached_workspaces = max_cached_workspaces
        self.media_preview_enabled = media_preview_enabled
        self._container: ApiContainer | None = None
        self._services = OrderedDict()
        self._lock = RLock()

    def install_host(self, container: ApiContainer) -> None:
        if self._container is not None:
            raise RuntimeError("Workspace provider host is already installed.")
        self._container = container

    def get_services(self, context: WorkspaceContext):
        with self.session_factory() as session:
            exists = session.scalar(
                select(Workspace.id).where(
                    Workspace.id == context.workspace_id, Workspace.deleted_at.is_(None)
                )
            )
        if exists is None:
            raise LookupError("workspace not found")
        with self._lock:
            if self._container is None:
                raise RuntimeError("Workspace provider host has not been installed.")
            services = self._services.get(context.workspace_id)
            if services is None:
                workspace = SqlVideoWorkspace(
                    session_factory=self.session_factory,
                    blob_store=self.blob_store,
                    cache_root=self.data_root / "workspaces" / context.workspace_id,
                    workspace_id=context.workspace_id,
                    media_preview_enabled=self.media_preview_enabled,
                )
                services = build_workspace_services(self._container, workspace)
                self._services[context.workspace_id] = services
                if len(self._services) > self.max_cached_workspaces:
                    # In-flight requests retain their service references. The
                    # shared model HTTP client is owned by the host, not cache entries.
                    self._services.popitem(last=False)
            self._services.move_to_end(context.workspace_id)
            return services

    def close(self):
        with self._lock:
            self._services.clear()
