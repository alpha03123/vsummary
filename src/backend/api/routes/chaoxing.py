"""超星课程导入路由。

提供超星平台的初始化、课程/章节/视频浏览与课程导入（含进度流）的 HTTP 端点。
"""

from __future__ import annotations

import asyncio
from threading import Thread
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.container import ApiContainerDep
from backend.api.sse import stream_progress_events
from backend.chaoxing.chaoxing_api import ChaoxingImportCancelled, ChaoxingInitCancelled
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO

router = APIRouter()


class ChaoxingStatusResponse(BaseModel):
    """超星初始化状态响应。"""
    initialized: bool


class ChaoxingCourseResponse(BaseModel):
    """超星课程信息响应。"""
    course_key: str
    title: str
    teacher: str
    open_time: str


class ChaoxingChapterResponse(BaseModel):
    """超星课程章节信息响应。"""
    chapter_key: str
    title: str
    order: str


class ChaoxingVideoResponse(BaseModel):
    """超星章节视频信息响应。"""
    video_key: str
    chapter_key: str
    title: str
    duration: int
    filename: str


class ImportChaoxingCourseRequest(BaseModel):
    """导入超星课程的请求体。"""
    course_key: str


class ImportChaoxingCourseResponse(BaseModel):
    """导入超星课程的响应体，含后台任务 ID 和目标系列 ID。"""
    task_id: str
    series_id: str


@router.get("/api/linked/chaoxing/status", response_model=ChaoxingStatusResponse)
async def get_chaoxing_status(container: ApiContainerDep) -> ChaoxingStatusResponse:
    """GET /api/linked/chaoxing/status — 查询超星平台初始化状态。

    返回超星平台是否已成功登录/初始化，前端据此决定是否展示登录界面。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        ChaoxingStatusResponse，含 initialized 布尔值。

    Raises:
        HTTPException(409): 超星客户端未初始化或状态异常。
    """
    try:
        initialized = await asyncio.to_thread(container.chaoxing_importer.is_initialized)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ChaoxingStatusResponse(
        initialized=initialized,
    )


@router.post("/api/linked/chaoxing/init", response_model=ChaoxingStatusResponse)
async def init_chaoxing(container: ApiContainerDep) -> ChaoxingStatusResponse:
    """POST /api/linked/chaoxing/init — 触发超星平台初始化。

    执行超星平台的登录/会话建立流程，完成后返回最新初始化状态。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        ChaoxingStatusResponse，含初始化完成后的状态。

    Raises:
        HTTPException(409): 初始化被取消或执行异常。
    """
    try:
        await asyncio.to_thread(container.chaoxing_importer.init)
    except ChaoxingInitCancelled as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ChaoxingStatusResponse(
        initialized=await asyncio.to_thread(container.chaoxing_importer.is_initialized),
    )


@router.post("/api/linked/chaoxing/init/cancel")
async def cancel_chaoxing_init(container: ApiContainerDep) -> dict[str, str]:
    """POST /api/linked/chaoxing/init/cancel — 取消正在进行的超星初始化。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"status": "cancelled"}
    """
    container.chaoxing_importer.cancel_init()
    return {"status": "cancelled"}


@router.get("/api/linked/chaoxing/courses", response_model=list[ChaoxingCourseResponse])
async def list_chaoxing_courses(container: ApiContainerDep) -> list[ChaoxingCourseResponse]:
    """GET /api/linked/chaoxing/courses — 列出当前超星账号的所有课程。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        课程信息列表。

    Raises:
        HTTPException(409): 超星客户端未初始化或状态异常。
    """
    try:
        courses = await asyncio.to_thread(container.chaoxing_importer.list_courses)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return [ChaoxingCourseResponse(**course.__dict__) for course in courses]


@router.get("/api/linked/chaoxing/courses/{course_key}/chapters", response_model=list[ChaoxingChapterResponse])
async def list_chaoxing_chapters(course_key: str, container: ApiContainerDep) -> list[ChaoxingChapterResponse]:
    """GET /api/linked/chaoxing/courses/{course_key}/chapters — 列出课程的章节列表。

    Args:
        course_key: 超星课程唯一 key，取自课程列表中的 course_key 字段。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        章节信息列表。

    Raises:
        HTTPException(409): 超星客户端未初始化或状态异常。
    """
    try:
        chapters = await asyncio.to_thread(lambda: container.chaoxing_importer.list_chapters(course_key))
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return [ChaoxingChapterResponse(**chapter.__dict__) for chapter in chapters]


@router.get("/api/linked/chaoxing/chapters/{chapter_key}/videos", response_model=list[ChaoxingVideoResponse])
async def list_chaoxing_videos(chapter_key: str, container: ApiContainerDep) -> list[ChaoxingVideoResponse]:
    """GET /api/linked/chaoxing/chapters/{chapter_key}/videos — 列出章节下的视频列表。

    Args:
        chapter_key: 超星章节唯一 key，取自章节列表中的 chapter_key 字段。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        视频信息列表。

    Raises:
        HTTPException(409): 超星客户端未初始化或状态异常。
    """
    try:
        videos = await asyncio.to_thread(lambda: container.chaoxing_importer.list_videos(chapter_key))
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return [ChaoxingVideoResponse(**video.__dict__) for video in videos]


@router.post("/api/linked/chaoxing/import/course", response_model=ImportChaoxingCourseResponse)
async def import_chaoxing_course(request: ImportChaoxingCourseRequest, container: ApiContainerDep) -> ImportChaoxingCourseResponse:
    """POST /api/linked/chaoxing/import/course — 启动超星课程导入（后台任务）。

    立即返回任务 ID 和系列 ID，实际下载和导入在后台线程执行；
    前端应通过 SSE 进度端点订阅导入进度。

    Args:
        request: 包含 course_key 的导入请求。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        ImportChaoxingCourseResponse，含 task_id 和 series_id。
    """
    task_id = f"chaoxing-import-{uuid4().hex}"
    series_id = f"chaoxing-{_safe_key(request.course_key)}"
    reporter = container.chaoxing_import_progress_tracker.create_reporter(task_id)
    reporter.update("import", 0.0, "超星课程导入任务已开始")

    def _run_import() -> None:
        try:
            linked_series = container.chaoxing_importer.import_course(request.course_key, progress=reporter)
            if reporter.is_cancel_requested():
                reporter.cancelled("超星课程导入已取消")
                return
            reporter.update("save", 95.0, "正在保存导入结果")
            if reporter.is_cancel_requested():
                reporter.cancelled("超星课程导入已取消")
                return
            container.linked_series_workspace.save_linked_series(linked_series)
            container.workspace_index_invalidator.invalidate()
            reporter.completed(f"导入完成：{len(linked_series.videos)} 个视频")
        except ChaoxingImportCancelled as error:
            reporter.cancelled(str(error))
        except Exception as error:
            reporter.failed(str(error))

    Thread(target=_run_import, daemon=True).start()
    return ImportChaoxingCourseResponse(task_id=task_id, series_id=series_id)


@router.post("/api/linked/chaoxing/import/course/{task_id}/cancel")
async def cancel_chaoxing_course_import(task_id: str, container: ApiContainerDep) -> dict[str, str]:
    """POST /api/linked/chaoxing/import/course/{task_id}/cancel — 取消正在进行的课程导入。

    Args:
        task_id: 导入任务 ID，来自 import_chaoxing_course 返回的 task_id。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"status": "cancelling", "task_id": ...}
    """
    container.chaoxing_import_progress_tracker.request_cancel(task_id)
    return {"status": "cancelling", "task_id": task_id}


@router.get("/api/linked/chaoxing/import/course/{task_id}/progress")
async def stream_chaoxing_import_progress(task_id: str, container: ApiContainerDep) -> StreamingResponse:
    """GET /api/linked/chaoxing/import/course/{task_id}/progress — 订阅课程导入进度流（SSE）。

    以 SSE 推送导入的状态变化、进度百分比与详情；
    到达 completed、failed 或 cancelled 终端状态后自动关闭流。

    Args:
        task_id: 导入任务 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        StreamingResponse（`text/event-stream`）。
    """
    return StreamingResponse(
        stream_progress_events(
            tracker=container.chaoxing_import_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
    )


def _to_series_dto(linked_series: LinkedSeries) -> LibrarySeriesDTO:
    """将链接型系列模型转换为库层 DTO。

    Args:
        linked_series: 链接型系列实体。

    Returns:
        库层兼容的 LibrarySeriesDTO。
    """
    return LibrarySeriesDTO(
        id=linked_series.series_id,
        title=linked_series.title,
        videos=[_to_video_card_dto(video) for video in linked_series.videos],
        is_linked=True,
        source_url=linked_series.source_url,
    )


def _to_video_card_dto(video: LinkedVideo) -> LibraryVideoCardDTO:
    """将链接型视频模型转换为库层视频卡片 DTO。

    Args:
        video: 链接型视频实体。

    Returns:
        库层兼容的 LibraryVideoCardDTO。
    """
    return LibraryVideoCardDTO(
        id=video.video_id,
        title=video.title,
        source_name=f"{video.video_id}.mp4",
        processed=False,
        status="linked",
        is_linked=True,
        bilibili_bvid=video.bvid,
        bilibili_page=video.page,
        source_url=video.source_url,
        provider=video.provider,
    )


def _safe_key(value: str) -> str:
    """将任意字符串清洗为安全的标识符（仅保留字母、数字、下划线和连字符）。

    用于将超星课程 key 转换为安全的工作区 ID。

    Args:
        value: 原始字符串。

    Returns:
        清洗后的安全标识符，若清洗后为空则返回 "item"。
    """
    import re

    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return normalized or "item"
