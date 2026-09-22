"""Dependencies required by product-neutral API routes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import uuid4

from fastapi import Depends, HTTPException, Request

from backend.api.di.container import ApiContainerDep
from backend.api.di.workspace_services import WorkspaceServices
from backend.chaoxing import ChaoxingCourseImporter
from backend.core.context import WorkspaceContext
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository


def get_workspace_context(
    request: Request,
    container: ApiContainerDep,
) -> WorkspaceContext:
    context = getattr(request.state, "workspace_context", None)
    if isinstance(context, WorkspaceContext):
        return context
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID") or uuid4().hex
    return container.context_provider.get_context(request_id=request_id)


WorkspaceContextDep = Depends(get_workspace_context)


def get_workspace_services(
    context: WorkspaceContext = WorkspaceContextDep,
    container: ApiContainerDep = None,
) -> WorkspaceServices:
    if container is None:
        raise RuntimeError("workspace service resolution requires an application container.")
    try:
        services = container.workspace_services_provider.get_services(context)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="workspace not found") from error
    return cast(WorkspaceServices, services)


WorkspaceServicesDep = Annotated[WorkspaceServices, Depends(get_workspace_services)]


def get_job_repository(container: ApiContainerDep) -> SqlJobRepository:
    return container.job_repository


JobRepositoryDep = Annotated[SqlJobRepository, Depends(get_job_repository)]


def get_chaoxing_importer(container: ApiContainerDep) -> ChaoxingCourseImporter:
    return container.chaoxing_importer


ChaoxingImporterDep = Annotated[ChaoxingCourseImporter, Depends(get_chaoxing_importer)]
