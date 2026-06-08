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
    initialized: bool


class ChaoxingCourseResponse(BaseModel):
    course_key: str
    title: str
    teacher: str
    open_time: str


class ChaoxingChapterResponse(BaseModel):
    chapter_key: str
    title: str
    order: str


class ChaoxingVideoResponse(BaseModel):
    video_key: str
    chapter_key: str
    title: str
    duration: int
    filename: str


class ImportChaoxingCourseRequest(BaseModel):
    course_key: str


class ImportChaoxingCourseResponse(BaseModel):
    task_id: str
    series_id: str


@router.get("/api/linked/chaoxing/status", response_model=ChaoxingStatusResponse)
async def get_chaoxing_status(container: ApiContainerDep) -> ChaoxingStatusResponse:
    try:
        initialized = await asyncio.to_thread(container.chaoxing_importer.is_initialized)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ChaoxingStatusResponse(
        initialized=initialized,
    )


@router.post("/api/linked/chaoxing/init", response_model=ChaoxingStatusResponse)
async def init_chaoxing(container: ApiContainerDep) -> ChaoxingStatusResponse:
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
    container.chaoxing_importer.cancel_init()
    return {"status": "cancelled"}


@router.get("/api/linked/chaoxing/courses", response_model=list[ChaoxingCourseResponse])
async def list_chaoxing_courses(container: ApiContainerDep) -> list[ChaoxingCourseResponse]:
    try:
        courses = await asyncio.to_thread(container.chaoxing_importer.list_courses)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return [ChaoxingCourseResponse(**course.__dict__) for course in courses]


@router.get("/api/linked/chaoxing/courses/{course_key}/chapters", response_model=list[ChaoxingChapterResponse])
async def list_chaoxing_chapters(course_key: str, container: ApiContainerDep) -> list[ChaoxingChapterResponse]:
    try:
        chapters = await asyncio.to_thread(lambda: container.chaoxing_importer.list_chapters(course_key))
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return [ChaoxingChapterResponse(**chapter.__dict__) for chapter in chapters]


@router.get("/api/linked/chaoxing/chapters/{chapter_key}/videos", response_model=list[ChaoxingVideoResponse])
async def list_chaoxing_videos(chapter_key: str, container: ApiContainerDep) -> list[ChaoxingVideoResponse]:
    try:
        videos = await asyncio.to_thread(lambda: container.chaoxing_importer.list_videos(chapter_key))
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return [ChaoxingVideoResponse(**video.__dict__) for video in videos]


@router.post("/api/linked/chaoxing/import/course", response_model=ImportChaoxingCourseResponse)
async def import_chaoxing_course(request: ImportChaoxingCourseRequest, container: ApiContainerDep) -> ImportChaoxingCourseResponse:
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
    container.chaoxing_import_progress_tracker.request_cancel(task_id)
    return {"status": "cancelling", "task_id": task_id}


@router.get("/api/linked/chaoxing/import/course/{task_id}/progress")
async def stream_chaoxing_import_progress(task_id: str, container: ApiContainerDep) -> StreamingResponse:
    return StreamingResponse(
        stream_progress_events(
            tracker=container.chaoxing_import_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
    )


def _to_series_dto(linked_series: LinkedSeries) -> LibrarySeriesDTO:
    return LibrarySeriesDTO(
        id=linked_series.series_id,
        title=linked_series.title,
        videos=[_to_video_card_dto(video) for video in linked_series.videos],
        is_linked=True,
        source_url=linked_series.source_url,
    )


def _to_video_card_dto(video: LinkedVideo) -> LibraryVideoCardDTO:
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
    import re

    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return normalized or "item"
