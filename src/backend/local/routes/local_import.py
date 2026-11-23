"""Local filesystem picker, relink, and absolute-path import endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.api.dependencies import WorkspaceServicesDep
from backend.local.desktop_media_picker import select_local_media_directory, select_local_media_paths
from backend.api.schemas.contracts import LocalMediaPathImportRequest, LocalMediaSeriesPathImportRequest
from backend.api.schemas.responses import SeriesResponse, VideoCardResponse


router = APIRouter()


@router.post("/api/import/local/select")
def select_local_media(services: WorkspaceServicesDep) -> dict[str, object]:
    try:
        source_paths = select_local_media_paths()
        incompatible_paths = [
            Path(path).name for path in source_paths if not services.linked_series_workspace.can_hardlink(Path(path))
        ]
        return {
            "source_paths": source_paths,
            "hardlink_available": not incompatible_paths,
            "incompatible_source_names": incompatible_paths,
        }
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"无法打开本机文件选择框：{error}") from error


@router.post("/api/videos/{series_id}/{video_id}/relink")
def relink_external_video(series_id: str, video_id: str, services: WorkspaceServicesDep) -> dict[str, object]:
    workspace = services.linked_series_workspace
    recorded_path = workspace.get_external_media_reference_path(series_id, video_id)
    source = services.get_video_source.run(series_id, video_id)
    initial_dir = (
        recorded_path.parent
        if recorded_path is not None
        else (source.source_path.parent if source is not None else None)
    )
    selected_paths = select_local_media_paths(initial_directory=initial_dir, allow_multiple=False)
    if not selected_paths:
        return {"relinked": False, "relinked_count": 0}
    chosen_path = Path(selected_paths[0])
    try:
        workspace.relink_external_video(
            series_id=series_id,
            video_id=video_id,
            source_path=chosen_path,
        )
        extra_count = workspace.relink_series_from_directory(
            series_id=series_id,
            directory=chosen_path.parent,
            only_missing=True,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"relinked": True, "relinked_count": 1 + extra_count}


@router.post("/api/series/{series_id}/relink-folder")
def relink_series_from_folder(
    series_id: str,
    services: WorkspaceServicesDep,
    video_id: str | None = None,
) -> dict[str, object]:
    workspace = services.linked_series_workspace
    recorded_path = workspace.get_external_media_reference_path(series_id, video_id)
    initial_dir = recorded_path.parent if recorded_path is not None else None
    selected_dir = select_local_media_directory(initial_directory=initial_dir)
    if not selected_dir:
        return {"relinked": False, "relinked_count": 0}
    try:
        count = workspace.relink_series_from_directory(
            series_id=series_id,
            directory=Path(selected_dir),
            only_missing=False,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"relinked": count > 0, "relinked_count": count}


@router.post("/api/import/local/series/from-paths", response_model=SeriesResponse)
def import_local_series_from_paths(
    request: LocalMediaSeriesPathImportRequest,
    services: WorkspaceServicesDep,
) -> SeriesResponse:
    if request.storage_mode is None:
        raise HTTPException(status_code=400, detail="storage_mode 不能为空。")
    try:
        series = services.import_media_series.run_from_paths(
            title=request.series_title,
            source_paths=[Path(path) for path in request.source_paths],
            storage_mode=request.storage_mode,
        )
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return SeriesResponse.from_model(series)


@router.post("/api/import/local/playground/from-paths", response_model=list[VideoCardResponse])
def import_local_playground_videos_from_paths(
    request: LocalMediaPathImportRequest,
    services: WorkspaceServicesDep,
) -> list[VideoCardResponse]:
    try:
        videos = services.import_playground_media.run_from_paths(
            source_paths=[Path(path) for path in request.source_paths],
        )
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return [VideoCardResponse.from_model(video) for video in videos]


@router.post("/api/import/local/series/{series_id}/from-paths", response_model=list[VideoCardResponse])
def import_local_series_videos_from_paths(
    series_id: str,
    request: LocalMediaPathImportRequest,
    services: WorkspaceServicesDep,
) -> list[VideoCardResponse]:
    try:
        videos = services.import_series_media.run_from_paths(
            series_id=series_id,
            source_paths=[Path(path) for path in request.source_paths],
        )
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return [VideoCardResponse.from_model(video) for video in videos]
