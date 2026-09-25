"""外部链接解析与视频下载路由。

提供 B 站视频/合集 URL 解析、链接型视频下载启动及下载进度 SSE 流的 HTTP 端点。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from backend.api.dependencies import JobRepositoryDep, WorkspaceServicesDep
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
from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError

router = APIRouter()


@router.post("/api/agent/series", response_model=SeriesResponse)
async def create_agent_series(request: AgentSeriesCreateRequest, container: WorkspaceServicesDep) -> SeriesResponse:
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
    container: WorkspaceServicesDep = None,
    job_repository: JobRepositoryDep = None,
) -> dict[str, object]:
    """提交 Agent 系列的视频处理 Job。"""
    payload = request or AgentSeriesProcessRequest()
    video_ids = [item.strip() for item in payload.video_ids if item.strip()]
    try:
        series = _find_series(container, series_id)
        target_video_ids = video_ids or [
            video.id
            for video in series.videos
            if not video.processed
        ]
        if not target_video_ids:
            raise ValueError("agent series has no pending videos")
        submissions = []
        for video_id in target_video_ids:
            _find_video(container, series_id, video_id)
            submissions.append(
                _submit_agent_video_job(
                    container=container,
                    job_repository=job_repository,
                    series_id=series_id,
                    video_id=video_id,
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
        "scope": "videos",
        "video_ids": target_video_ids,
        "status": "queued",
        "jobs": [
            {
                "job_id": submitted.id,
                "status": submitted.status,
                "resource": {"type": "video", "id": video_id},
                "status_url": f"/api/jobs/{submitted.id}",
                "events_url": f"/api/jobs/{submitted.id}/events",
            }
            for video_id, submitted in zip(target_video_ids, submissions, strict=True)
        ],
    }


@router.post("/api/linked/bilibili/resolve/series", response_model=SeriesResponse)
async def resolve_bilibili_series(request: ResolveBilibiliSeriesRequest, container: WorkspaceServicesDep) -> SeriesResponse:
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


def _submit_agent_video_job(
    *,
    container,
    job_repository,
    series_id: str,
    video_id: str,
    transcript_enhancement_enabled: bool | None,
    processing_mode: str,
):
    try:
        return job_repository.submit(
            workspace_id=container.workspace_id,
            resource_type="video",
            resource_id=video_id,
            operation="process_agent_video",
            request_payload={
                "series_id": series_id,
                "video_id": video_id,
                "transcript_enhancement_enabled": transcript_enhancement_enabled,
                "processing_mode": processing_mode,
            },
            active_key=f"video:{video_id}:process_agent_video",
            idempotency_scope_id=None,
            idempotency_key=None,
        )
    except ControlPlaneConflictError:
        active = job_repository.active_for_resource(
            workspace_id=container.workspace_id,
            resource_id=video_id,
            operation="process_agent_video",
        )
        if active is None:
            raise
        return active


@router.post("/api/linked/bilibili/resolve/video", response_model=VideoCardResponse)
async def resolve_bilibili_video(request: ResolveBilibiliVideoRequest, container: WorkspaceServicesDep) -> VideoCardResponse:
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


@router.post("/api/linked/bilibili/inbox/resolve/video", response_model=VideoCardResponse)
async def resolve_bilibili_inbox_video(request: ResolveBilibiliVideoRequest, container: WorkspaceServicesDep) -> VideoCardResponse:
    """解析浏览器扩展当前的 Bilibili 视频并加入专用收件箱。"""
    try:
        video = await container.resolve_bilibili_video.run_inbox(url=request.url)
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
    container: WorkspaceServicesDep,
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
    container: WorkspaceServicesDep,
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
async def start_video_download(
    series_id: str,
    video_id: str,
    container: WorkspaceServicesDep,
    job_repository: JobRepositoryDep,
) -> JSONResponse:
    """提交外链下载的持久 Job。"""
    try:
        submitted = _submit_linked_video_download_job(container, job_repository, series_id, video_id)
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
async def cancel_video_download(
    series_id: str,
    video_id: str,
    container: WorkspaceServicesDep,
    job_repository: JobRepositoryDep,
) -> dict[str, str]:
    """POST /api/videos/{series_id}/{video_id}/download/cancel — 取消正在进行的视频下载。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"status": "cancelling"}
    """
    active = job_repository.active_for_resource(
        workspace_id=container.workspace_id,
        resource_id=video_id,
        operation="download_linked_video",
    )
    if active is None:
        raise HTTPException(status_code=404, detail="no active download job found")
    snapshot = job_repository.request_cancel(
        active.id,
        workspace_id=container.workspace_id,
    )
    return {"status": snapshot.status if snapshot is not None else "cancelling", "job_id": active.id}


def _submit_linked_video_download_job(container, job_repository, series_id: str, video_id: str):
    workspace = container.linked_series_workspace
    if workspace.get_linked_video_for_download(series_id, video_id) is None:
        raise LookupError(f"linked video not found: {series_id}/{video_id}")
    try:
        return job_repository.submit(
            workspace_id=container.workspace_id,
            resource_type="video",
            resource_id=video_id,
            operation="download_linked_video",
            request_payload={"series_id": series_id, "video_id": video_id},
            active_key=f"video:{video_id}:download_linked_video",
            idempotency_scope_id=None,
            idempotency_key=None,
        )
    except ControlPlaneConflictError:
        active = job_repository.active_for_resource(
            workspace_id=container.workspace_id,
            resource_id=video_id,
            operation="download_linked_video",
        )
        if active is None:
            raise
        return active
