"""外部链接解析与视频下载路由。

提供 B 站视频/合集 URL 解析、链接型视频下载启动及下载进度 SSE 流的 HTTP 端点。
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.di.container import ApiContainerDep
from backend.api.schemas.contracts import AgentSeriesCreateRequest, AgentSeriesProcessRequest
from backend.api.schemas.responses import (
    LinkedVideoDownloadResponse,
    ResolveBilibiliSeriesRequest,
    ResolveBilibiliVideoRequest,
    SeriesResponse,
    VideoCardResponse,
)
from backend.api.schemas.sse import stream_progress_events
from backend.bilibili.ytdlp_bilibili import (
    BILIBILI_COOKIE_REQUIRED_MESSAGE,
    BilibiliCookieInitError,
    build_video_download_task_id,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)
DOWNLOAD_POLL_INTERVAL_SECONDS = 0.5
DOWNLOAD_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class BilibiliCookieStatusResponse(BaseModel):
    """Bilibili Cookie 配置状态响应。"""
    configured: bool


@router.post("/api/agent/series", response_model=SeriesResponse)
async def create_agent_series(request: AgentSeriesCreateRequest, container: ApiContainerDep) -> SeriesResponse:
    """POST /api/agent/series — 创建一个供 Agent 编排的空链接型系列。"""
    try:
        series = container.create_agent_series.run(title=request.title)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return SeriesResponse.from_model(series)


@router.post("/api/agent/series/{series_id}/process")
async def process_agent_series(
    series_id: str,
    request: AgentSeriesProcessRequest | None = None,
    container: ApiContainerDep = None,
) -> dict[str, object]:
    """POST /api/agent/series/{series_id}/process — 后台启动 Agent 系列处理。"""
    payload = request or AgentSeriesProcessRequest()
    video_ids = [item.strip() for item in payload.video_ids if item.strip()]
    try:
        _find_series(container, series_id)
        run_id = payload.run_id or str(uuid4())
        if video_ids:
            for video_id in video_ids:
                _find_video(container, series_id, video_id)
            asyncio.create_task(
                _run_agent_selected_video_generation(
                    container=container,
                    series_id=series_id,
                    video_ids=video_ids,
                    transcript_enhancement_enabled=payload.transcript_enhancement_enabled,
                )
            )
            return {
                "series_id": series_id,
                "run_id": run_id,
                "scope": "videos",
                "video_ids": video_ids,
                "status": "scheduled",
            }
        asyncio.create_task(
            _run_agent_series_generation(
                container=container,
                series_id=series_id,
                run_id=run_id,
                transcript_enhancement_enabled=payload.transcript_enhancement_enabled,
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "series_id": series_id,
        "run_id": run_id,
        "scope": "series",
        "video_ids": [],
        "status": "scheduled",
    }


@router.post("/api/linked/bilibili/cookie/init", response_model=BilibiliCookieStatusResponse)
async def init_bilibili_cookie(container: ApiContainerDep) -> BilibiliCookieStatusResponse:
    """POST /api/linked/bilibili/cookie/init — 打开登录页并写入 Bilibili Cookie。"""
    try:
        configured = await asyncio.to_thread(container.bilibili_cookie_initializer.init)
    except BilibiliCookieInitError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return BilibiliCookieStatusResponse(configured=configured)


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
        if _is_bilibili_cookie_required_error(error):
            raise HTTPException(status_code=409, detail=BILIBILI_COOKIE_REQUIRED_MESSAGE) from error
        raise HTTPException(status_code=502, detail=str(error)) from error
    return SeriesResponse.from_model(series)


async def _run_agent_series_generation(
    *,
    container,
    series_id: str,
    run_id: str,
    transcript_enhancement_enabled: bool | None,
) -> None:
    try:
        await _download_agent_linked_videos(
            container=container,
            series_id=series_id,
            video_ids=[],
            task_id=f"series/{series_id}",
        )
        await container.generate_series_summaries.run(
            series_id,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
            run_id=run_id,
        )
    except Exception as error:
        container.generation_progress_tracker.create_reporter(f"series/{series_id}").failed(str(error))
        LOGGER.exception("Background agent series generation failed: series_id=%s run_id=%s", series_id, run_id)


async def _run_agent_selected_video_generation(
    *,
    container,
    series_id: str,
    video_ids: list[str],
    transcript_enhancement_enabled: bool | None,
) -> None:
    try:
        for video_id in video_ids:
            await _download_agent_linked_videos(
                container=container,
                series_id=series_id,
                video_ids=[video_id],
                task_id=f"{series_id}/{video_id}",
            )
            await container.generate_video_summary.run(
                series_id,
                video_id,
                transcript_enhancement_enabled=transcript_enhancement_enabled,
            )
    except Exception as error:
        for video_id in video_ids:
            container.generation_progress_tracker.create_reporter(f"{series_id}/{video_id}").failed(str(error))
        LOGGER.exception("Background agent selected video generation failed: series_id=%s video_ids=%s", series_id, video_ids)


async def _download_agent_linked_videos(
    *,
    container,
    series_id: str,
    video_ids: list[str],
    task_id: str | None = None,
) -> None:
    videos = _find_agent_download_targets(container, series_id, video_ids)
    if not videos:
        return

    reporter = None
    if task_id is not None:
        reporter = container.generation_progress_tracker.create_reporter(task_id)

    total = len(videos)
    for index, video in enumerate(videos, start=1):
        if reporter is not None and reporter.is_cancel_requested():
            reporter.cancelled("任务已取消")
            return
        if reporter is not None:
            reporter.update(
                "download",
                ((index - 1) / total) * 100.0,
                f"正在下载未缓存视频 {index}/{total}: {video.title}",
            )
        try:
            await _download_agent_linked_video(container=container, series_id=series_id, video_id=video.id)
        except Exception as error:
            if reporter is not None:
                reporter.failed(str(error))
            raise

    if reporter is not None:
        reporter.update("download", 100.0, "未缓存视频已下载完成")


async def _download_agent_linked_video(*, container, series_id: str, video_id: str) -> None:
    result = container.start_linked_video_download.run(series_id=series_id, video_id=video_id)
    task_id = result.task_id
    while True:
        snapshot = container.video_download_progress_tracker.get_snapshot(task_id)
        if snapshot.status == "completed":
            return
        if snapshot.status in DOWNLOAD_TERMINAL_STATUSES:
            detail = snapshot.error or snapshot.detail or f"linked video download {snapshot.status}"
            raise RuntimeError(detail)
        await asyncio.sleep(DOWNLOAD_POLL_INTERVAL_SECONDS)


def _find_agent_download_targets(container, series_id: str, video_ids: list[str]):
    selected_ids = set(video_ids)
    series = _find_series(container, series_id)
    return [
        video
        for video in series.videos
        if (not selected_ids or video.id in selected_ids)
        and not video.processed
        and (video.is_linked or video.status == "linked")
    ]


def _find_series(container, series_id: str):
    if not series_id.strip():
        raise ValueError("series_id must not be blank")
    library = container.list_video_library.run()
    for series in library.series:
        if series.id == series_id:
            return series
    raise LookupError(f"series not found '{series_id}'")


def _find_video(container, series_id: str, video_id: str):
    series = _find_series(container, series_id)
    for video in series.videos:
        if video.id == video_id:
            return video
    raise LookupError(f"video not found '{series_id}/{video_id}'")


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
        if _is_bilibili_cookie_required_error(error):
            raise HTTPException(status_code=409, detail=BILIBILI_COOKIE_REQUIRED_MESSAGE) from error
        raise HTTPException(status_code=502, detail=str(error)) from error
    return VideoCardResponse.from_model(video)


def _is_bilibili_cookie_required_error(error: RuntimeError) -> bool:
    message = str(error)
    return (
        BILIBILI_COOKIE_REQUIRED_MESSAGE in message
        or "HTTP Error 412" in message
        or "Precondition Failed" in message
    )


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
