"""外部链接解析与视频下载路由。

提供 B 站视频/合集 URL 解析、链接型视频下载启动及下载进度 SSE 流的 HTTP 端点。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.container import ApiContainerDep
from backend.api.contracts import AgentSeriesCreateRequest, AgentSeriesVideosAddRequest, GenerateSeriesSummariesRequest
from backend.api.responses import (
    LinkedVideoDownloadResponse,
    ResolveBilibiliSeriesRequest,
    ResolveBilibiliVideoRequest,
    SeriesResponse,
    VideoCardResponse,
)
from backend.api.sse import stream_progress_events
from backend.bilibili.ytdlp_bilibili import (
    BILIBILI_COOKIE_REQUIRED_MESSAGE,
    BilibiliCookieInitError,
    build_video_download_task_id,
)
from backend.video_summary.library.usecases.agent_series import AgentVideoCandidate

router = APIRouter()
LOGGER = logging.getLogger(__name__)


class BilibiliCookieStatusResponse(BaseModel):
    """Bilibili Cookie 配置状态响应。"""
    configured: bool


class BilibiliCookieInitRequest(BaseModel):
    """BiliNote 风格的 Cookie 初始化请求。"""

    cookie: str | None = None


class DownloaderCookieUpdateRequest(BaseModel):
    """BiliNote 兼容的下载器 Cookie 更新请求。"""

    platform: str
    cookie: str


class DownloaderCookieUpdateResponse(BaseModel):
    success: bool


class DownloaderCookieStatusResponse(BaseModel):
    platform: str
    configured: bool


class BilibiliQrLoginSessionResponse(BaseModel):
    url: str
    qrcode_key: str


class BilibiliQrLoginPollRequest(BaseModel):
    qrcode_key: str


class BilibiliQrLoginPollResponse(BaseModel):
    status: str
    message: str
    configured: bool


@router.post("/api/linked/bilibili/cookie/init", response_model=BilibiliCookieStatusResponse)
async def init_bilibili_cookie(
    container: ApiContainerDep,
    request: BilibiliCookieInitRequest | None = None,
) -> BilibiliCookieStatusResponse:
    """POST /api/linked/bilibili/cookie/init — 写入或获取 Bilibili Cookie。"""
    try:
        configured = await asyncio.to_thread(container.bilibili_cookie_initializer.init, request.cookie if request else None)
    except BilibiliCookieInitError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return BilibiliCookieStatusResponse(configured=configured)


@router.post("/api/update_downloader_cookie", response_model=DownloaderCookieUpdateResponse)
async def update_downloader_cookie(
    request: DownloaderCookieUpdateRequest,
    container: ApiContainerDep,
) -> DownloaderCookieUpdateResponse:
    """POST /api/update_downloader_cookie — BiliNote 兼容的 Cookie 保存接口。"""
    platform = request.platform.strip()
    cookie = request.cookie.strip()
    if not platform:
        raise HTTPException(status_code=422, detail="platform 不能为空")
    if not cookie:
        raise HTTPException(status_code=422, detail="cookie 不能为空")
    if platform == "bilibili":
        try:
            await asyncio.to_thread(container.bilibili_cookie_initializer.init, cookie)
        except (BilibiliCookieInitError, RuntimeError, ValueError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    else:
        container.bilibili_cookie_config_manager.set(platform, cookie)
    return DownloaderCookieUpdateResponse(success=True)


@router.get("/api/get_downloader_cookie/{platform}", response_model=DownloaderCookieStatusResponse)
async def get_downloader_cookie(platform: str, container: ApiContainerDep) -> DownloaderCookieStatusResponse:
    """GET /api/get_downloader_cookie/{platform} — 返回 Cookie 配置状态，不返回明文。"""
    normalized_platform = platform.strip()
    return DownloaderCookieStatusResponse(
        platform=normalized_platform,
        configured=container.bilibili_cookie_config_manager.get(normalized_platform) is not None,
    )


@router.post("/api/linked/bilibili/cookie/qr", response_model=BilibiliQrLoginSessionResponse)
async def create_bilibili_qr_login_session(container: ApiContainerDep) -> BilibiliQrLoginSessionResponse:
    """POST /api/linked/bilibili/cookie/qr — 创建 Bilibili 扫码登录会话。"""
    try:
        session = await asyncio.to_thread(container.bilibili_qr_login_service.create_session)
    except (BilibiliCookieInitError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return BilibiliQrLoginSessionResponse(url=session.url, qrcode_key=session.qrcode_key)


@router.post("/api/linked/bilibili/cookie/qr/poll", response_model=BilibiliQrLoginPollResponse)
async def poll_bilibili_qr_login(
    request: BilibiliQrLoginPollRequest,
    container: ApiContainerDep,
) -> BilibiliQrLoginPollResponse:
    """POST /api/linked/bilibili/cookie/qr/poll — 查询 Bilibili 扫码登录状态。"""
    qrcode_key = request.qrcode_key.strip()
    if not qrcode_key:
        raise HTTPException(status_code=422, detail="qrcode_key 不能为空")
    try:
        result = await asyncio.to_thread(container.bilibili_qr_login_service.poll, qrcode_key)
    except (BilibiliCookieInitError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return BilibiliQrLoginPollResponse(status=result.status, message=result.message, configured=result.configured)


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


@router.post("/api/agent/series", response_model=SeriesResponse)
async def create_agent_series(request: AgentSeriesCreateRequest, container: ApiContainerDep) -> SeriesResponse:
    try:
        series = container.create_agent_series.run(
            title=request.title,
            source=request.source,
            notes=request.notes,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return SeriesResponse.from_model(series)


@router.post("/api/agent/series/{series_id}/videos", response_model=list[VideoCardResponse])
async def add_agent_series_videos(
    series_id: str,
    request: AgentSeriesVideosAddRequest,
    container: ApiContainerDep,
) -> list[VideoCardResponse]:
    try:
        videos = await container.add_agent_series_videos.run(
            series_id=series_id,
            videos=[
                AgentVideoCandidate(url=item.url, title=item.title, source=item.source)
                for item in request.videos
            ],
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        if _is_bilibili_cookie_required_error(error):
            raise HTTPException(status_code=409, detail=BILIBILI_COOKIE_REQUIRED_MESSAGE) from error
        raise HTTPException(status_code=502, detail=str(error)) from error
    return [VideoCardResponse.from_model(video) for video in videos]


@router.post("/api/agent/series/{series_id}/process")
async def process_agent_series(
    series_id: str,
    request: GenerateSeriesSummariesRequest | None = None,
    container: ApiContainerDep = None,
) -> dict[str, str]:
    run_id = (request.run_id if request else None) or str(uuid4())
    try:
        _find_agent_series(container, series_id)
        asyncio.create_task(
            _run_agent_series_generation(
                container=container,
                series_id=series_id,
                run_id=run_id,
                transcript_enhancement_enabled=(None if request is None else request.transcript_enhancement_enabled),
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"series_id": series_id, "run_id": run_id, "status": "scheduled"}


@router.get("/api/agent/series/{series_id}/status")
async def get_agent_series_status(series_id: str, container: ApiContainerDep) -> dict[str, object]:
    try:
        series = _find_agent_series(container, series_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return {
        "id": series.id,
        "title": series.title,
        "videos": [_agent_video_status(container, series.id, video) for video in series.videos],
    }


async def _run_agent_series_generation(
    *,
    container,
    series_id: str,
    run_id: str,
    transcript_enhancement_enabled: bool | None,
) -> None:
    try:
        await container.generate_series_summaries.run(
            series_id,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
            run_id=run_id,
        )
    except Exception:
        LOGGER.exception("Background agent series generation failed: series_id=%s run_id=%s", series_id, run_id)


def _find_agent_series(container, series_id: str):
    if not series_id.strip():
        raise ValueError("series_id must not be blank")
    library = container.list_video_library.run()
    for series in library.series:
        if series.id == series_id:
            return series
    raise LookupError(f"series not found '{series_id}'")


def _agent_video_status(container, series_id: str, video) -> dict[str, object]:
    return {
        "id": video.id,
        "title": video.title,
        "status": video.status,
        "processed": bool(video.processed),
        "is_linked": bool(video.is_linked),
        "source_url": video.source_url,
        "artifacts": _agent_video_artifacts(container, series_id, video.id),
        "failure_reason": str(getattr(video, "error", "") or getattr(video, "detail", "") or ""),
    }


def _agent_video_artifacts(container, series_id: str, video_id: str) -> dict[str, bool]:
    root_dir = getattr(container, "root_dir", None)
    if root_dir is None:
        return {"summary": False, "transcript": False}
    try:
        video_dir = Path(root_dir) / "workspace" / series_id / video_id
        return {
            "summary": (video_dir / "summary.json").exists(),
            "transcript": (video_dir / "transcript.cleaned.json").exists(),
        }
    except OSError:
        return {"summary": False, "transcript": False}


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
