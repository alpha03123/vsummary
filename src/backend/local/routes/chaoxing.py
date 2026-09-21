"""Local-only Chaoxing login, browsing, and durable import endpoints."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.di.container import ApiContainerDep
from backend.chaoxing.chaoxing_api import ChaoxingInitCancelled
from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError


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
    job_id: str
    status: str
    series_id: str


@router.get("/api/linked/chaoxing/status", response_model=ChaoxingStatusResponse)
async def get_chaoxing_status(container: ApiContainerDep) -> ChaoxingStatusResponse:
    try:
        initialized = await asyncio.to_thread(container.chaoxing_importer.is_initialized)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ChaoxingStatusResponse(initialized=initialized)


@router.post("/api/linked/chaoxing/init", response_model=ChaoxingStatusResponse)
async def init_chaoxing(container: ApiContainerDep) -> ChaoxingStatusResponse:
    try:
        await asyncio.to_thread(container.chaoxing_importer.init)
    except (ChaoxingInitCancelled, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ChaoxingStatusResponse(initialized=await asyncio.to_thread(container.chaoxing_importer.is_initialized))


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
        chapters = await asyncio.to_thread(container.chaoxing_importer.list_chapters, course_key)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return [ChaoxingChapterResponse(**chapter.__dict__) for chapter in chapters]


@router.get("/api/linked/chaoxing/chapters/{chapter_key}/videos", response_model=list[ChaoxingVideoResponse])
async def list_chaoxing_videos(chapter_key: str, container: ApiContainerDep) -> list[ChaoxingVideoResponse]:
    try:
        videos = await asyncio.to_thread(container.chaoxing_importer.list_videos, chapter_key)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return [ChaoxingVideoResponse(**video.__dict__) for video in videos]


@router.post("/api/linked/chaoxing/import/course", response_model=ImportChaoxingCourseResponse, status_code=202)
async def import_chaoxing_course(request: ImportChaoxingCourseRequest, container: ApiContainerDep) -> ImportChaoxingCourseResponse:
    series_id = f"chaoxing-{_safe_key(request.course_key)}"
    try:
        submitted = container.job_repository.submit(
            workspace_id=container.sql_workspace.workspace_id,
            resource_type="series",
            resource_id=series_id,
            operation="import_chaoxing_course",
            request_payload={"course_key": request.course_key},
            active_key=f"chaoxing-course:{request.course_key}:import",
            idempotency_scope_id=None,
            idempotency_key=None,
        )
    except ControlPlaneConflictError as error:
        active = container.job_repository.active_for_resource(
            workspace_id=container.sql_workspace.workspace_id,
            resource_id=series_id,
            operation="import_chaoxing_course",
        )
        if active is None:
            raise HTTPException(status_code=409, detail=str(error)) from error
        submitted = active
    return ImportChaoxingCourseResponse(job_id=submitted.id, status=submitted.status, series_id=series_id)


@router.post("/api/linked/chaoxing/import/course/{job_id}/cancel")
async def cancel_chaoxing_course_import(job_id: str, container: ApiContainerDep) -> dict[str, str]:
    snapshot = container.job_repository.request_cancel(job_id, workspace_id=container.sql_workspace.workspace_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"status": snapshot.status, "job_id": snapshot.id}


def _safe_key(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return normalized or "item"
