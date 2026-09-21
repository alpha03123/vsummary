"""外部链接解析与视频下载路由。

提供 B 站视频/合集 URL 解析、链接型视频下载启动及下载进度 SSE 流的 HTTP 端点。
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from backend.api.di.container import ApiContainerDep
from backend.api.schemas.contracts import AgentSeriesCreateRequest, AgentSeriesProcessRequest
from backend.api.schemas.responses import (
    ResolveBilibiliSeriesRequest,
    ResolveBilibiliVideoRequest,
    ResolveLinkedSeriesRequest,
    ResolveLinkedVideoRequest,
    SeriesResponse,
    VideoCardResponse,
)
from backend.bilibili.ytdlp_bilibili import (
    BILIBILI_COOKIE_REQUIRED_MESSAGE,
)
from backend.external.ytdlp import ExternalVideoResolutionError
from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError
from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError

router = APIRouter()
LOGGER = logging.getLogger(__name__)
DOWNLOAD_POLL_INTERVAL_SECONDS = 0.5


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
            progress_reporters: dict[str, ProgressReporter] = {}
            for video_id in video_ids:
                _find_video(container, series_id, video_id)
                reporter = container.generation_progress_tracker.create_reporter(f"{series_id}/{video_id}")
                reporter.update(
                    "queued",
                    0.0,
                    "任务已进入队列，等待开始处理",
                )
                progress_reporters[video_id] = reporter
            asyncio.create_task(
                _run_agent_selected_video_generation(
                    container=container,
                    series_id=series_id,
                    video_ids=video_ids,
                    transcript_enhancement_enabled=payload.transcript_enhancement_enabled,
                    progress_reporters=progress_reporters,
                    processing_mode=payload.processing_mode,
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
                processing_mode=payload.processing_mode,
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
    processing_mode: str = "summary",
) -> None:
    try:
        await _download_agent_linked_videos(
            container=container,
            series_id=series_id,
            video_ids=[],
            task_id=f"series/{series_id}",
        )
        arguments = {
            "transcript_enhancement_enabled": transcript_enhancement_enabled,
            "run_id": run_id,
        }
        if processing_mode != "summary":
            arguments["processing_mode"] = processing_mode
        await container.generate_series_summaries.run(series_id, **arguments)
    except Exception as error:
        container.generation_progress_tracker.create_reporter(f"series/{series_id}").failed(str(error))
        LOGGER.exception("Background agent series generation failed: series_id=%s run_id=%s", series_id, run_id)


async def _run_agent_selected_video_generation(
    *,
    container,
    series_id: str,
    video_ids: list[str],
    transcript_enhancement_enabled: bool | None,
    progress_reporters: dict[str, ProgressReporter],
    processing_mode: str = "summary",
) -> None:
    for video_id in video_ids:
        reporter = progress_reporters[video_id]
        try:
            if reporter.is_cancel_requested():
                reporter.cancelled("任务已取消")
                continue
            downloaded = await _download_agent_linked_videos(
                container=container,
                series_id=series_id,
                video_ids=[video_id],
                progress_reporter=reporter,
            )
            if not downloaded or reporter.is_cancel_requested():
                reporter.cancelled("任务已取消")
                continue
            arguments = {
                "transcript_enhancement_enabled": transcript_enhancement_enabled,
                "progress_reporter": reporter,
            }
            if processing_mode != "summary":
                arguments["processing_mode"] = processing_mode
            await container.generate_video_summary.run(series_id, video_id, **arguments)
        except GenerateCancelledError:
            reporter.cancelled("任务已取消")
        except Exception as error:
            if reporter.is_cancel_requested():
                reporter.cancelled("任务已取消")
                continue
            reporter.failed(str(error))
            LOGGER.exception(
                "Background agent selected video generation failed: series_id=%s video_id=%s",
                series_id,
                video_id,
            )


async def _download_agent_linked_videos(
    *,
    container,
    series_id: str,
    video_ids: list[str],
    task_id: str | None = None,
    progress_reporter: ProgressReporter | None = None,
) -> bool:
    reporter = progress_reporter
    if reporter is None and task_id is not None:
        reporter = container.generation_progress_tracker.create_reporter(task_id)

    if reporter is not None and reporter.is_cancel_requested():
        reporter.cancelled("任务已取消")
        return False

    videos = _find_agent_download_targets(container, series_id, video_ids)
    if not videos:
        return True

    total = len(videos)
    for index, video in enumerate(videos, start=1):
        if reporter is not None and reporter.is_cancel_requested():
            reporter.cancelled("任务已取消")
            return False
        if reporter is not None:
            reporter.update(
                "download",
                ((index - 1) / total) * 100.0,
                f"正在下载未缓存视频 {index}/{total}: {video.title}",
            )
        try:
            await _download_agent_linked_video(
                container=container,
                series_id=series_id,
                video_id=video.id,
                progress_reporter=reporter,
            )
        except GenerateCancelledError:
            if reporter is not None:
                reporter.cancelled("任务已取消")
            return False
        except Exception as error:
            if reporter is not None:
                reporter.failed(str(error))
            raise

    if reporter is not None:
        reporter.update("download", 100.0, "未缓存视频已下载完成")
    return True


async def _download_agent_linked_video(
    *,
    container,
    series_id: str,
    video_id: str,
    progress_reporter: ProgressReporter | None = None,
) -> None:
    submitted = _submit_linked_video_download_job(container, series_id, video_id)
    while True:
        if progress_reporter is not None and progress_reporter.is_cancel_requested():
            container.job_repository.request_cancel(
                submitted.id,
                workspace_id=container.sql_workspace.workspace_id,
            )
            raise GenerateCancelledError("任务已取消")
        snapshot = container.job_repository.get(
            submitted.id,
            workspace_id=container.sql_workspace.workspace_id,
        )
        if snapshot is None:
            raise RuntimeError("linked video download job disappeared")
        if snapshot.status == "succeeded":
            return
        if snapshot.status in {"failed", "cancelled"}:
            detail = snapshot.failure_detail or f"linked video download {snapshot.status}"
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


@router.post("/api/linked/{provider}/resolve/series", response_model=SeriesResponse)
async def resolve_linked_series(
    provider: str,
    request: ResolveLinkedSeriesRequest,
    container: ApiContainerDep,
) -> SeriesResponse:
    """解析指定 yt-dlp 平台的系列或播放列表。"""
    try:
        series = await container.resolve_linked_series.run(provider=provider, url=request.url)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise _linked_resolution_http_error(provider, error) from error
    return SeriesResponse.from_model(series)


@router.post("/api/linked/{provider}/resolve/video", response_model=VideoCardResponse)
async def resolve_linked_video(
    provider: str,
    request: ResolveLinkedVideoRequest,
    container: ApiContainerDep,
) -> VideoCardResponse:
    """解析指定 yt-dlp 平台的单视频并写入目标系列。"""
    try:
        video = await container.resolve_linked_video.run(
            provider=provider,
            url=request.url,
            target_series_id=request.target_series_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise _linked_resolution_http_error(provider, error) from error
    return VideoCardResponse.from_model(video)


def _is_bilibili_cookie_required_error(error: RuntimeError) -> bool:
    message = str(error)
    return (
        BILIBILI_COOKIE_REQUIRED_MESSAGE in message
        or "HTTP Error 412" in message
        or "Precondition Failed" in message
    )


def _linked_resolution_http_error(provider: str, error: Exception) -> HTTPException:
    message = str(error)
    if isinstance(error, ExternalVideoResolutionError):
        status_code = {"cookie_required": 409, "invalid_url": 422, "failed": 502}.get(error.kind, 502)
        return HTTPException(status_code=status_code, detail=message)
    if provider.lower() == "bilibili" and _is_bilibili_cookie_required_error(error):
        return HTTPException(status_code=409, detail=BILIBILI_COOKIE_REQUIRED_MESSAGE)
    return HTTPException(status_code=502, detail=message)


@router.post("/api/videos/{series_id}/{video_id}/download")
async def start_video_download(series_id: str, video_id: str, container: ApiContainerDep) -> JSONResponse:
    """提交外链下载的持久 Job。"""
    try:
        submitted = _submit_linked_video_download_job(container, series_id, video_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ControlPlaneConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return JSONResponse(
        status_code=202,
        content={
            "job_id": submitted.id,
            "status": submitted.status,
            "resource": {"type": "video", "id": video_id},
            "status_url": f"/api/jobs/{submitted.id}",
            "events_url": f"/api/jobs/{submitted.id}/events",
        },
    )


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
    active = container.job_repository.active_for_resource(
        workspace_id=container.sql_workspace.workspace_id,
        resource_id=video_id,
        operation="download_linked_video",
    )
    if active is None:
        raise HTTPException(status_code=404, detail="no active download job found")
    snapshot = container.job_repository.request_cancel(
        active.id,
        workspace_id=container.sql_workspace.workspace_id,
    )
    return {"status": snapshot.status if snapshot is not None else "cancelling", "job_id": active.id}


def _submit_linked_video_download_job(container, series_id: str, video_id: str):
    workspace = container.linked_series_workspace
    if workspace.get_linked_video_for_download(series_id, video_id) is None:
        raise LookupError(f"linked video not found: {series_id}/{video_id}")
    try:
        return container.job_repository.submit(
            workspace_id=container.sql_workspace.workspace_id,
            resource_type="video",
            resource_id=video_id,
            operation="download_linked_video",
            request_payload={"series_id": series_id, "video_id": video_id},
            active_key=f"video:{video_id}:download_linked_video",
            idempotency_scope_id=None,
            idempotency_key=None,
        )
    except ControlPlaneConflictError:
        active = container.job_repository.active_for_resource(
            workspace_id=container.sql_workspace.workspace_id,
            resource_id=video_id,
            operation="download_linked_video",
        )
        if active is None:
            raise
        return active
