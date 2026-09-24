"""Local-only endpoints for inspecting and importing an old VSummary directory."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.dependencies import WorkspaceServicesDep
from backend.api.di.container import ApiContainerDep
from backend.local.legacy_migration import LegacyMigrationService, select_legacy_directory
from backend.local.persistence.file_blob_store import FileBlobStore


router = APIRouter()


class InspectLegacyRequest(BaseModel):
    path: str
    convert_hardlinks: bool = False


class CreateLegacyRunRequest(InspectLegacyRequest):
    include_data: list[str] = Field(default_factory=list)
    delete_verified_videos: bool


def get_legacy_migration_service(request: Request, container: ApiContainerDep, services: WorkspaceServicesDep) -> LegacyMigrationService:
    service = getattr(request.app.state, "legacy_migration_service", None)
    if service is None:
        workspace = services.linked_series_workspace
        blob_store = workspace.blob_store
        if not isinstance(blob_store, FileBlobStore):
            raise HTTPException(status_code=503, detail="手动目录迁移仅支持本地 Blob 存储")
        service = LegacyMigrationService(session_factory=workspace.session_factory, blob_store=blob_store, installation_root=container.root_dir)
        request.app.state.legacy_migration_service = service
    return service


LegacyMigrationServiceDep = Annotated[LegacyMigrationService, Depends(get_legacy_migration_service)]


@router.post("/api/legacy-migration/select-source")
def select_source() -> dict[str, str | None]:
    return {"path": select_legacy_directory()}


@router.post("/api/legacy-migration/inspect")
def inspect_source(body: InspectLegacyRequest, service: LegacyMigrationServiceDep) -> dict:
    try:
        return service.inspect(Path(body.path), convert_hardlinks=body.convert_hardlinks)
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/api/legacy-migration/runs")
def create_run(body: CreateLegacyRunRequest, service: LegacyMigrationServiceDep) -> dict:
    try:
        if not body.delete_verified_videos:
            raise ValueError("必须确认逐视频核验后清理旧 videos 文件")
        return service.create_run(Path(body.path), include_data=body.include_data, convert_hardlinks=body.convert_hardlinks)
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/api/legacy-migration/runs/{run_id}/start")
def start_run(run_id: str, service: LegacyMigrationServiceDep) -> dict:
    try:
        return service.start(run_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/api/legacy-migration/runs/{run_id}")
def get_run(run_id: str, service: LegacyMigrationServiceDep) -> dict:
    try:
        return service.status(run_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/api/legacy-migration/latest")
def get_latest_run(service: LegacyMigrationServiceDep) -> dict | None:
    return service.latest()


@router.post("/api/legacy-migration/runs/{run_id}/cancel")
def cancel_run(run_id: str, service: LegacyMigrationServiceDep) -> dict:
    try:
        return service.cancel(run_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
