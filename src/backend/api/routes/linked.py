"""外部链接解析与视频下载路由。

提供 B 站视频/合集 URL 解析、链接型视频下载启动及下载进度 SSE 流的 HTTP 端点。
"""

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
from backend.bilibili.ytdlp_bilibili import build_video_download_task_id

router = APIRouter()


@router.post("/api/linked/bilibili/resolve/series", response_model=SeriesResponse)
async def resolve_bilibili_series(request: ResolveBilibiliSeriesRequest, container: ApiContainerDep) -> SeriesResponse:
    """POST /api/linked/bilibili/resolve/series — 解析 B 站合集/系列 URL。

    将 B 站链接解析为包含多视频的系列信息，用于后续导入预览；
    非合集 URL 时行为由实现方定义。

    Args:
        request: 包含 B 站 URL 的解析请求。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        SeriesResponse，含系列元数据与视频列表。

    Raises:
        HTTPException(422): URL 格式无效。
        HTTPException(502): 上游解析服务异常。
    """
    try:
        series = await container.resolve_bilibili_series.run(url=request.url)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return SeriesResponse.from_model(series)


@router.post("/api/linked/bilibili/resolve/video", response_model=VideoCardResponse)
async def resolve_bilibili_video(request: ResolveBilibiliVideoRequest, container: ApiContainerDep) -> VideoCardResponse:
    """POST /api/linked/bilibili/resolve/video — 解析 B 站单个视频 URL。

    将 B 站链接解析为单个视频信息卡片，支持指定目标系列 ID
    用于将视频追加到已有系列。

    Args:
        request: 包含 B 站 URL 和可选 target_series_id 的解析请求。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        VideoCardResponse，含视频元数据。

    Raises:
        HTTPException(422): URL 格式无效。
        HTTPException(404): 目标系列不存在。
        HTTPException(502): 上游解析服务异常。
    """
    try:
        video = await container.resolve_bilibili_video.run(
            url=request.url,
            target_series_id=request.target_series_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return VideoCardResponse.from_model(video)


@router.post("/api/videos/{series_id}/{video_id}/download", response_model=LinkedVideoDownloadResponse)
async def start_video_download(series_id: str, video_id: str, container: ApiContainerDep) -> LinkedVideoDownloadResponse:
    """POST /api/videos/{series_id}/{video_id}/download — 启动链接型视频的后台下载。

    立即返回任务 ID，实际下载在后台执行；
    前端应通过对应的 SSE 进度端点订阅下载进度。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        LinkedVideoDownloadResponse，含 task_id。

    Raises:
        HTTPException(404): 视频不存在。
    """
    try:
        result = container.start_linked_video_download.run(series_id=series_id, video_id=video_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return LinkedVideoDownloadResponse.started(result.task_id)


@router.post("/api/videos/{series_id}/{video_id}/download/cancel")
async def cancel_video_download(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, str]:
    """POST /api/videos/{series_id}/{video_id}/download/cancel — 取消正在进行的视频下载。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"status": "cancelling"}
    """
    task_id = build_video_download_task_id(series_id, video_id)
    container.video_download_progress_tracker.request_cancel(task_id)
    return {"status": "cancelling"}


@router.get("/api/videos/{series_id}/{video_id}/download/progress")
async def stream_video_download_progress(series_id: str, video_id: str, container: ApiContainerDep) -> StreamingResponse:
    """GET /api/videos/{series_id}/{video_id}/download/progress — 订阅视频下载进度流（SSE）。

    以 SSE 推送下载状态变化、进度百分比与详情；
    到达 completed、failed 或 cancelled 终端状态后自动关闭流。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        StreamingResponse（`text/event-stream`）。
    """
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
