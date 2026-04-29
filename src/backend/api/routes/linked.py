from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.container import ApiContainerDep
from backend.api.responses import (
    LinkedVideoDownloadResponse,
    ResolveBilibiliSeriesRequest,
    ResolveBilibiliVideoRequest,
    SeriesResponse,
    VideoCardResponse,
)
from backend.api.sse import stream_progress_events
from backend.bilibili.download_starter import build_video_download_task_id

router = APIRouter()


@router.post("/api/linked/bilibili/resolve/series", response_model=SeriesResponse)
async def resolve_bilibili_series(request: ResolveBilibiliSeriesRequest, container: ApiContainerDep) -> SeriesResponse:
    try:
        series = await container.resolve_bilibili_series.run(url=request.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SeriesResponse.from_model(series)


@router.post("/api/linked/bilibili/resolve/video", response_model=VideoCardResponse)
async def resolve_bilibili_video(request: ResolveBilibiliVideoRequest, container: ApiContainerDep) -> VideoCardResponse:
    try:
        card = await container.resolve_bilibili_video.run(
            url=request.url,
            target_series_id=request.target_series_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return VideoCardResponse.from_model(card)


@router.post("/api/videos/{series_id}/{video_id}/download", response_model=LinkedVideoDownloadResponse)
async def start_video_download(series_id: str, video_id: str, container: ApiContainerDep) -> LinkedVideoDownloadResponse:
    try:
        result = container.start_linked_video_download.run(series_id=series_id, video_id=video_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LinkedVideoDownloadResponse.started(result.task_id)


@router.get("/api/videos/{series_id}/{video_id}/download/progress")
async def stream_video_download_progress(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    task_id = build_video_download_task_id(series_id, video_id)
    return StreamingResponse(
        stream_progress_events(
            tracker=container.video_download_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.delete("/api/linked/{series_id}")
def delete_linked_series(series_id: str, container: ApiContainerDep) -> dict[str, object]:
    try:
        deleted = container.delete_linked_series.run(series_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "deleted", "series_id": deleted.series_id}
