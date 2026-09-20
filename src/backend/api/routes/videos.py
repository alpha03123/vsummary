"""视频库管理路由。

提供视频库的增删查改、视频总结/思维导图/知识卡的生成与导出，
以及生成进度 SSE 流的 HTTP 端点。
"""

from __future__ import annotations

import asyncio
from io import BytesIO
import logging
import json
import mimetypes
from pathlib import Path
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from backend.api.di.container import ApiContainerDep
from backend.api.schemas.contracts import (
    CancelSeriesSummariesRequest,
    CreateVideoNoteRequest,
    GenerateVideoAiSummaryRequest,
    UpdateVideoAiSummaryRequest,
    GenerateMindmapRequest,
    GenerateSeriesSummariesRequest,
    GenerateVideoSummaryRequest,
    RenameTitleRequest,
    UpdateVideoNoteRequest,
    UpdateVideoSummaryRequest,
    UpdateVideoTranscriptRequest,
)
from backend.api.schemas.responses import (
    VideoChapterCardsResponse,
    VideoKnowledgeCardsResponse,
    VideoLibraryResponse,
    VideoNoteResponse,
    VideoNotesResponse,
    VideoAiSummaryResponse,
    VideoWorkspaceToolsResponse,
)
from backend.api.schemas.sse import stream_progress_events
from backend.bilibili.ytdlp_bilibili import build_video_download_task_id
from backend.video_summary.infrastructure.video_summary_runtime import AsrModelNotReadyError
from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError
from backend.video_summary.domain.models import ManualTranscriptInput
from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError
from backend.video_summary.infrastructure.subtitle_transcripts import parse_srt_transcript
from backend.video_summary.library.markdown_exports import render_knowledge_cards_markdown
from backend.video_summary.library.markdown_exports import render_mixed_overview_markdown
from backend.video_summary.library.markdown_exports import render_notes_markdown
from backend.video_summary.library.markdown_exports import render_transcript_markdown
from backend.video_summary.library.subtitle_exports import render_srt, render_webvtt
from backend.video_summary.generation.renderers import render_markdown
from backend.video_summary.library.usecases.mutations import GenerationInProgressError
from backend.video_summary.library.usecases.summary_generation import DuplicateSeriesGenerationError
from backend.video_summary.library.usecases.summary_generation import GenerationScopeBusyError
from backend.video_summary.infrastructure.storage.mindmap_export import render_mindmap_html, render_mindmap_markdown

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/api/videos", response_model=VideoLibraryResponse)
def list_videos(container: ApiContainerDep) -> VideoLibraryResponse:
    """GET /api/videos — 列出整个视频库（全部系列与视频）。

    返回工作区下所有系列及其视频卡片的扁平列表，
    前端据此渲染库面板的导航树。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        VideoLibraryResponse，含系列列表及各自下的视频卡片。
    """
    library = container.list_video_library.run()
    return VideoLibraryResponse.from_model(library)


@router.get("/api/videos/{series_id}/{video_id}/summary")
def get_video_summary(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, object]:
    """GET /api/videos/{series_id}/{video_id}/summary — 获取视频的结构化总结 JSON。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        JSON 字典，含 LLM 生成的各段总结文本。

    Raises:
        HTTPException(404): 视频不存在或总结未生成。
    """
    _ensure_video_exists(container, series_id, video_id)
    video_summary = container.get_video_summary.run(series_id, video_id)
    if video_summary is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    return video_summary.summary


@router.put("/api/videos/{series_id}/{video_id}/summary")
def update_video_summary(
    series_id: str,
    video_id: str,
    request: UpdateVideoSummaryRequest,
    container: ApiContainerDep,
) -> dict[str, object]:
    """保存用户修订后的结构化总结。"""
    try:
        summary = container.update_video_summary.run(
            series_id,
            video_id,
            markdown=request.markdown,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if summary is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    return summary.summary


@router.get("/api/videos/{series_id}/{video_id}/summary/markdown")
def get_video_summary_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, str]:
    """获取可直接编辑的原始 ``summary.md``。"""
    _ensure_video_exists(container, series_id, video_id)
    summary = container.get_video_summary.run(series_id, video_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    return {"markdown": render_markdown(summary.summary)}


@router.get("/api/videos/{series_id}/{video_id}/transcript")
def get_video_transcript(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, object]:
    """获取可编辑的完整转写分段。"""
    _ensure_video_exists(container, series_id, video_id)
    transcript = container.get_video_transcript.run(series_id, video_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail=f"transcript not found for video '{series_id}/{video_id}'")
    return {
        "title": transcript.title,
        "duration_seconds": transcript.duration_seconds,
        "segments": [
            {
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "text": segment.text,
            }
            for segment in transcript.segments
        ],
    }


@router.get("/api/videos/{series_id}/{video_id}/transcript/markdown")
def get_video_transcript_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, str]:
    """获取可直接编辑的原始 Markdown 转写。"""
    _ensure_video_exists(container, series_id, video_id)
    transcript = container.get_video_transcript.run(series_id, video_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail=f"transcript not found for video '{series_id}/{video_id}'")
    return {"markdown": render_transcript_markdown({
        "title": transcript.title,
        "duration_seconds": transcript.duration_seconds,
        "segments": [
            {"start_seconds": segment.start_seconds, "end_seconds": segment.end_seconds, "text": segment.text}
            for segment in transcript.segments
        ],
    })}


@router.get("/api/videos/{series_id}/{video_id}/subtitles.vtt")
def get_video_subtitles_webvtt(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    """将当前工作区转写作为浏览器可加载的 WebVTT 字幕轨道返回。"""
    _ensure_video_exists(container, series_id, video_id)
    transcript = container.get_video_transcript.run(series_id, video_id)
    if transcript is None or not transcript.segments:
        raise HTTPException(status_code=404, detail=f"subtitles not found for video '{series_id}/{video_id}'")
    return Response(
        content=render_webvtt(transcript.segments),
        media_type="text/vtt; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )


@router.put("/api/videos/{series_id}/{video_id}/transcript")
def update_video_transcript(
    series_id: str,
    video_id: str,
    request: UpdateVideoTranscriptRequest,
    container: ApiContainerDep,
) -> dict[str, object]:
    """保存用户修订后的完整转写分段。"""
    try:
        transcript = container.update_video_transcript.run(
            series_id,
            video_id,
            markdown=request.markdown,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if transcript is None:
        raise HTTPException(status_code=404, detail=f"transcript not found for video '{series_id}/{video_id}'")
    return {
        "title": transcript.title,
        "duration_seconds": transcript.duration_seconds,
        "segments": [
            {
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "text": segment.text,
            }
            for segment in transcript.segments
        ],
    }


@router.get("/api/videos/{series_id}/{video_id}/exports/summary.md")
def export_video_summary_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    """GET /api/videos/{series_id}/{video_id}/exports/summary.md — 导出总结 Markdown 文件。

    返回视频总结的 summary.md 文件下载；文件由生成阶段落盘。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        FileResponse（`text/markdown`），含 Content-Disposition 下载头。

    Raises:
        HTTPException(404): 视频不存在或 summary.md 未生成。
    """
    _ensure_video_exists(container, series_id, video_id)
    summary = container.get_video_summary.run(series_id, video_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"summary markdown not found for video '{series_id}/{video_id}'")
    return _markdown_response(render_markdown(summary.summary), _export_filename(video_id, "summary"))


@router.get("/api/videos/{series_id}/{video_id}/exports/summary-with-screenshots.zip")
def export_video_summary_with_screenshots(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    """导出概况 Markdown 与章节截图，保持相对图片链接可离线读取。"""
    _ensure_video_exists(container, series_id, video_id)
    summary = container.get_video_summary.run(series_id, video_id)
    screenshots = container.linked_series_workspace.list_artifacts(video_id=video_id, kind="screenshot")
    if summary is None or not screenshots:
        raise HTTPException(status_code=404, detail=f"summary screenshots not found for video '{series_id}/{video_id}'")
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("summary.md", render_markdown(summary.summary).encode("utf-8"))
        for screenshot in screenshots:
            archive.write(screenshot, f"screenshots/{screenshot.name}")
    return _zip_response(buffer.getvalue(), f"{_safe_filename_part(video_id)}-summary-with-screenshots.zip")


@router.get("/api/videos/{series_id}/{video_id}/screenshots/{filename}")
def get_video_summary_screenshot(
    series_id: str,
    video_id: str,
    filename: str,
    container: ApiContainerDep,
) -> FileResponse:
    """返回已随概况成功提交的章节截图。"""
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".jpg":
        raise HTTPException(status_code=404, detail="screenshot not found")
    _ensure_video_exists(container, series_id, video_id)
    screenshot = container.linked_series_workspace.materialize_artifact(video_id=video_id, kind="screenshot", filename=filename)
    if screenshot is None:
        raise HTTPException(status_code=404, detail="screenshot not found")
    return FileResponse(screenshot, media_type="image/jpeg")


@router.get("/api/videos/{series_id}/{video_id}/frames/{filename}")
def get_video_note_frame(
    series_id: str,
    video_id: str,
    filename: str,
    container: ApiContainerDep,
) -> FileResponse:
    """返回由笔记图片标记按时间抽取的共享视频帧。"""
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".jpg":
        raise HTTPException(status_code=404, detail="frame not found")
    _ensure_video_exists(container, series_id, video_id)
    frame = container.linked_series_workspace.materialize_artifact(video_id=video_id, kind="note_frame", filename=filename)
    if frame is None:
        raise HTTPException(status_code=404, detail="frame not found")
    return FileResponse(frame, media_type="image/jpeg")


@router.get("/api/videos/{series_id}/{video_id}/exports/video")
def export_video_source(series_id: str, video_id: str, container: ApiContainerDep) -> FileResponse:
    """GET /api/videos/{series_id}/{video_id}/exports/video — 下载原始视频文件。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        FileResponse，MIME 类型根据文件后缀自动推断。

    Raises:
        HTTPException(404): 视频不存在。
    """
    source = _require_video_source(container, series_id, video_id)
    _ensure_source_media_available(source)
    media_type, _ = mimetypes.guess_type(source.source_path.name)
    return FileResponse(
        source.source_path,
        media_type=media_type or "application/octet-stream",
        filename=_video_export_filename(video_id, source.source_path.suffix),
    )


@router.get("/api/videos/{series_id}/{video_id}/exports/transcript.md")
def export_video_transcript_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    """GET /api/videos/{series_id}/{video_id}/exports/transcript.md — 导出转写 Markdown 文件。

    将转写 JSON 渲染为带时间戳的 Markdown 文本后返回下载。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        Response（`text/markdown`），含 Content-Disposition 下载头。

    Raises:
        HTTPException(404): 视频或转写不存在。
    """
    _ensure_video_exists(container, series_id, video_id)
    transcript = container.get_video_transcript.run(series_id, video_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail=f"transcript not found for video '{series_id}/{video_id}'")
    markdown = render_transcript_markdown({"title": transcript.title, "duration_seconds": transcript.duration_seconds, "segments": [{"start_seconds": item.start_seconds, "end_seconds": item.end_seconds, "text": item.text} for item in transcript.segments]})
    return _markdown_response(markdown, _export_filename(video_id, "transcript"))


@router.get("/api/videos/{series_id}/{video_id}/exports/subtitles.srt")
def export_video_subtitles_srt(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    """GET /api/videos/{series_id}/{video_id}/exports/subtitles.srt — 导出标准 SRT 字幕。"""
    _ensure_video_exists(container, series_id, video_id)
    transcript = container.get_video_transcript.run(series_id, video_id)
    if transcript is None or not transcript.segments:
        raise HTTPException(status_code=404, detail=f"subtitles not found for video '{series_id}/{video_id}'")
    return Response(
        content=render_srt(transcript.segments),
        media_type="application/x-subrip; charset=utf-8",
        headers={"Content-Disposition": _content_disposition_attachment(_export_filename(video_id, "subtitles", ".srt"))},
    )


@router.get("/api/videos/{series_id}/{video_id}/exports/mixed.md")
def export_video_mixed_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    """GET /api/videos/{series_id}/{video_id}/exports/mixed.md — 导出混合综述 Markdown。

    将总结 JSON 与转写 JSON 合并渲染为一份完整 Markdown 后返回下载。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        Response（`text/markdown`），含 Content-Disposition 下载头。

    Raises:
        HTTPException(404): 总结或转写不存在。
    """
    _ensure_video_exists(container, series_id, video_id)
    summary = container.get_video_summary.run(series_id, video_id)
    transcript = container.get_video_transcript.run(series_id, video_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    if transcript is None:
        raise HTTPException(status_code=404, detail=f"transcript not found for video '{series_id}/{video_id}'")
    markdown = render_mixed_overview_markdown(summary.summary, {"title": transcript.title, "duration_seconds": transcript.duration_seconds, "segments": [{"start_seconds": item.start_seconds, "end_seconds": item.end_seconds, "text": item.text} for item in transcript.segments]})
    return _markdown_response(markdown, _export_filename(video_id, "mixed"))


@router.get("/api/videos/{series_id}/{video_id}/exports/knowledge-cards.md")
def export_video_knowledge_cards_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    """GET /api/videos/{series_id}/{video_id}/exports/knowledge-cards.md — 导出知识卡 Markdown。

    将知识卡 JSON 渲染为 Markdown 文本后返回下载。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        Response（`text/markdown`），含 Content-Disposition 下载头。

    Raises:
        HTTPException(404): 知识卡未生成。
    """
    _ensure_video_exists(container, series_id, video_id)
    cards = container.get_video_cards.run(series_id, video_id)
    if cards is None or not cards.cards:
        raise HTTPException(status_code=404, detail=f"knowledge cards not found for video '{series_id}/{video_id}'")
    markdown = render_knowledge_cards_markdown({"title": cards.title, "cards": [item.__dict__ for item in cards.cards]})
    return _markdown_response(markdown, _export_filename(video_id, "knowledge-cards"))


@router.get("/api/videos/{series_id}/{video_id}/exports/notes.md")
def export_video_notes_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    """GET /api/videos/{series_id}/{video_id}/exports/notes.md — 导出笔记 Markdown。

    将用户/AI 笔记渲染为 Markdown 文本后返回下载。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        Response（`text/markdown`），含 Content-Disposition 下载头。

    Raises:
        HTTPException(404): 视频或笔记不存在。
    """
    _ensure_video_exists(container, series_id, video_id)
    notes = container.get_video_notes.run(series_id, video_id)
    if notes is None or not notes.notes:
        raise HTTPException(status_code=404, detail=f"notes not found for video '{series_id}/{video_id}'")
    markdown = render_notes_markdown(notes.title, {"notes": [item.__dict__ for item in notes.notes]})
    return _markdown_response(markdown, _export_filename(video_id, "notes"))


@router.get("/api/videos/{series_id}/{video_id}/mindmap")
def get_video_mindmap(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, object]:
    """GET /api/videos/{series_id}/{video_id}/mindmap — 获取视频的思维导图 JSON。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        JSON 字典，含思维导图节点树。

    Raises:
        HTTPException(404): 视频或思维导图不存在。
    """
    _ensure_video_exists(container, series_id, video_id)
    video_mindmap = container.get_video_mindmap.run(series_id, video_id)
    if video_mindmap is None:
        raise HTTPException(status_code=404, detail=f"mindmap not found for video '{series_id}/{video_id}'")
    return video_mindmap.mindmap


@router.get("/api/videos/{series_id}/{video_id}/mindmap/export")
def export_video_mindmap(series_id: str, video_id: str, format: str = "md", container: ApiContainerDep = None):
    """GET /api/videos/{series_id}/{video_id}/mindmap/export?format=md|html — 导出思维导图。"""
    if format not in ("md", "html"):
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}，仅支持 md / html")
    _ensure_video_exists(container, series_id, video_id)
    video_mindmap = container.get_video_mindmap.run(series_id, video_id)
    if video_mindmap is None:
        raise HTTPException(status_code=404, detail=f"mindmap not found for video '{series_id}/{video_id}'")
    if format == "html":
        content = render_mindmap_html(video_mindmap.mindmap, video_mindmap.title)
        filename = f"{video_mindmap.title}-mindmap.html"
        return _html_response(content, filename)
    markdown = render_mindmap_markdown(video_mindmap.mindmap)
    filename = f"{video_mindmap.title}-mindmap.md"
    return _markdown_response(markdown, filename)


@router.get("/api/videos/{series_id}/{video_id}/cards", response_model=VideoChapterCardsResponse)
def get_video_cards(series_id: str, video_id: str, container: ApiContainerDep) -> VideoChapterCardsResponse:
    """GET /api/videos/{series_id}/{video_id}/cards — 获取视频的章节卡集合。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        VideoChapterCardsResponse，含按章节组织的卡片列表。

    Raises:
        HTTPException(404): 视频或章节卡不存在。
    """
    _ensure_video_exists(container, series_id, video_id)
    video_cards = container.get_video_chapter_cards.run(series_id, video_id)
    if video_cards is None:
        raise HTTPException(status_code=404, detail=f"cards not found for video '{series_id}/{video_id}'")
    return VideoChapterCardsResponse.from_model(video_cards)


@router.get("/api/videos/{series_id}/{video_id}/knowledge-cards", response_model=VideoKnowledgeCardsResponse)
def get_video_knowledge_cards(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> VideoKnowledgeCardsResponse:
    """GET /api/videos/{series_id}/{video_id}/knowledge-cards — 获取视频的知识卡集合。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        VideoKnowledgeCardsResponse，含知识卡列表。

    Raises:
        HTTPException(404): 视频或知识卡不存在。
    """
    _ensure_video_exists(container, series_id, video_id)
    video_cards = container.get_video_cards.run(series_id, video_id)
    if video_cards is None:
        raise HTTPException(status_code=404, detail=f"knowledge cards not found for video '{series_id}/{video_id}'")
    return VideoKnowledgeCardsResponse.from_model(video_cards)


@router.post("/api/videos/{series_id}/{video_id}/knowledge-cards/generate")
def generate_video_knowledge_cards(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> JSONResponse:
    """POST /api/videos/{series_id}/{video_id}/knowledge-cards/generate — 生成视频知识卡。

    基于已有总结调用 LLM 生成知识卡列表并落盘；
    要求视频总结已存在。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        VideoKnowledgeCardsResponse，含生成的知识卡列表。

    Raises:
        HTTPException(400): 输入参数或配置无效。
        HTTPException(404): 总结未生成。
        HTTPException(503): LLM 调用失败。
    """
    _ensure_video_exists(container, series_id, video_id)
    try:
        submitted = container.job_repository.submit(
            workspace_id=container.sql_workspace.workspace_id,
            resource_type="video",
            resource_id=video_id,
            operation="generate_video_knowledge_cards",
            request_payload={"series_id": series_id, "video_id": video_id},
            active_key=f"video:{video_id}:generate_video_knowledge_cards",
            idempotency_scope_id=None,
            idempotency_key=None,
        )
    except ControlPlaneConflictError as error:
        active = container.job_repository.active_for_resource(
            workspace_id=container.sql_workspace.workspace_id,
            resource_id=video_id,
            operation="generate_video_knowledge_cards",
        )
        if active is None:
            raise HTTPException(status_code=409, detail=str(error)) from error
        submitted = active
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


@router.get("/api/videos/{series_id}/{video_id}/notes", response_model=VideoNotesResponse)
def get_video_notes(series_id: str, video_id: str, container: ApiContainerDep) -> VideoNotesResponse:
    """GET /api/videos/{series_id}/{video_id}/notes — 获取视频的所有笔记。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        VideoNotesResponse，含笔记列表。

    Raises:
        HTTPException(404): 视频不存在。
    """
    video_notes = container.get_video_notes.run(series_id, video_id)
    if video_notes is None:
        raise HTTPException(status_code=404, detail=f"未找到该视频，可能尚未下载：{series_id}/{video_id}")
    return VideoNotesResponse.from_model(video_notes)


@router.get("/api/videos/{series_id}/{video_id}/ai-summary", response_model=VideoAiSummaryResponse)
def get_video_ai_summary(series_id: str, video_id: str, container: ApiContainerDep) -> VideoAiSummaryResponse:
    summary = container.get_video_ai_summary.run(series_id, video_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"ai summary not found for video '{series_id}/{video_id}'")
    return VideoAiSummaryResponse.from_model(summary)


@router.post("/api/videos/{series_id}/{video_id}/ai-summary/generate", response_model=VideoAiSummaryResponse)
def generate_video_ai_summary(
    series_id: str,
    video_id: str,
    request: GenerateVideoAiSummaryRequest,
    container: ApiContainerDep,
) -> VideoAiSummaryResponse:
    try:
        summary = container.generate_video_ai_summary.run(series_id, video_id, template=request.template)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if summary is None:
        raise HTTPException(status_code=404, detail=f"未找到该视频，可能尚未下载：{series_id}/{video_id}")
    return VideoAiSummaryResponse.from_model(summary)


@router.put("/api/videos/{series_id}/{video_id}/ai-summary", response_model=VideoAiSummaryResponse)
def update_video_ai_summary(
    series_id: str,
    video_id: str,
    request: UpdateVideoAiSummaryRequest,
    container: ApiContainerDep,
) -> VideoAiSummaryResponse:
    try:
        summary = container.update_video_ai_summary.run(
            series_id,
            video_id,
            title=request.title,
            content=request.content,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if summary is None:
        raise HTTPException(status_code=404, detail=f"ai summary not found for video '{series_id}/{video_id}'")
    return VideoAiSummaryResponse.from_model(summary)


@router.post("/api/videos/{series_id}/{video_id}/notes", response_model=VideoNoteResponse)
def create_video_note(
    series_id: str,
    video_id: str,
    request: CreateVideoNoteRequest,
    container: ApiContainerDep,
) -> VideoNoteResponse:
    """POST /api/videos/{series_id}/{video_id}/notes — 为视频新增一条笔记。

    笔记来源（用户手写 vs AI 生成）通过 `source` 字段区分。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        request: 包含 title、content 和 source 的请求体。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        VideoNoteResponse，含分配 ID 与时间戳。

    Raises:
        HTTPException(400): 输入参数无效。
        HTTPException(404): 视频不存在。
    """
    if request.source != "manual":
        raise HTTPException(status_code=400, detail="个人笔记只支持 manual 来源；请使用 AI 概括接口。")
    try:
        note = container.create_video_note.run(
            series_id,
            video_id,
            title=request.title,
            content=request.content,
            source=request.source,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if note is None:
        raise HTTPException(status_code=404, detail=f"未找到该视频，可能尚未下载：{series_id}/{video_id}")
    return VideoNoteResponse.from_model(note)


@router.put("/api/videos/{series_id}/{video_id}/notes/{note_id}", response_model=VideoNoteResponse)
def update_video_note(
    series_id: str,
    video_id: str,
    note_id: str,
    request: UpdateVideoNoteRequest,
    container: ApiContainerDep,
) -> VideoNoteResponse:
    """PUT /api/videos/{series_id}/{video_id}/notes/{note_id} — 更新指定笔记的标题和内容。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        note_id: 笔记 ID。
        request: 包含更新后 title 和 content 的请求体。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        VideoNoteResponse，含更新后的笔记。

    Raises:
        HTTPException(400): 输入参数无效。
        HTTPException(404): 视频或笔记不存在。
    """
    try:
        note = container.update_video_note.run(
            series_id,
            video_id,
            note_id,
            title=request.title,
            content=request.content,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if container.get_video_source.run(series_id, video_id) is None:
        raise HTTPException(status_code=404, detail=f"未找到该视频，可能尚未下载：{series_id}/{video_id}")
    if note is None:
        raise HTTPException(status_code=404, detail=f"note not found '{note_id}'")
    return VideoNoteResponse.from_model(note)


@router.delete("/api/videos/{series_id}/{video_id}/notes/{note_id}")
def delete_video_note(
    series_id: str,
    video_id: str,
    note_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    """DELETE /api/videos/{series_id}/{video_id}/notes/{note_id} — 删除指定笔记。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        note_id: 笔记 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"status": "deleted", "note_id": ...}

    Raises:
        HTTPException(404): 视频不存在、笔记不存在或删除失败。
    """
    deleted = container.delete_video_note.run(series_id, video_id, note_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail=f"未找到该视频，可能尚未下载：{series_id}/{video_id}")
    if deleted is False:
        raise HTTPException(status_code=404, detail=f"note not found '{note_id}'")
    return {"status": "deleted", "note_id": note_id}


@router.get("/api/videos/{series_id}/{video_id}/tools", response_model=VideoWorkspaceToolsResponse)
def get_video_tools(series_id: str, video_id: str, container: ApiContainerDep) -> VideoWorkspaceToolsResponse:
    """GET /api/videos/{series_id}/{video_id}/tools — 获取视频工作区工具栏的完整状态。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        VideoWorkspaceToolsResponse，含各功能模块的就绪/不可用状态。

    Raises:
        HTTPException(404): 视频不存在。
    """
    video_tools = container.get_video_workspace_tools.run(series_id, video_id)
    if video_tools is None:
        raise HTTPException(status_code=404, detail=f"未找到该视频，可能尚未下载：{series_id}/{video_id}")
    return VideoWorkspaceToolsResponse.from_model(video_tools)


@router.get("/api/videos/{series_id}/{video_id}/preview")
def preview_video(series_id: str, video_id: str, container: ApiContainerDep) -> FileResponse:
    """GET /api/videos/{series_id}/{video_id}/preview — 获取视频源文件用于浏览器预览。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        FileResponse，直接返回已经在导入阶段完成播放优化的媒体文件。

    Raises:
        HTTPException(404): 视频不存在。
    """
    source = container.get_video_source.run(series_id, video_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"未找到该视频，可能尚未下载：{series_id}/{video_id}")
    _ensure_source_media_available(source)
    return FileResponse(source.source_path)


@router.post("/api/videos/{series_id}/{video_id}/generate")
async def generate_video_summary(
    series_id: str,
    video_id: str,
    http_request: Request,
    request: GenerateVideoSummaryRequest | None = None,
    container: ApiContainerDep = None,
) -> JSONResponse:
    """POST /api/videos/{series_id}/{video_id}/generate — 触发单个视频的总结生成。

    异步执行全流程：ASR 转写 → LLM 总结 → 思维导图 → 落盘；
    前端应通过对应的 SSE 进度端点订阅进度。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        request: 可选的生成参数（如 transcript_enhancement_enabled）。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        JSON 字典，含生成后的总结数据。

    Raises:
        HTTPException(400): 参数无效。
        HTTPException(404): 视频不存在。
        HTTPException(409): ASR 模型未就绪、生成被取消或 scope 忙碌。
        HTTPException(503): 生成过程发生运行时错误。
    """
    _ensure_source_media_available(_require_video_source(container, series_id, video_id))
    processing_mode = "summary" if request is None else request.processing_mode
    return _submit_video_generation_job(
        container=container,
        series_id=series_id,
        video_id=video_id,
        processing_mode=processing_mode,
        transcript_enhancement_enabled=None if request is None else request.transcript_enhancement_enabled,
        idempotency_key=http_request.headers.get("Idempotency-Key"),
    )


def _submit_video_generation_job(
    *,
    container,
    series_id: str,
    video_id: str,
    processing_mode: str,
    transcript_enhancement_enabled: bool | None,
    idempotency_key: str | None,
    manual_transcript: dict[str, str] | None = None,
    use_saved_manual_transcript: bool = True,
) -> JSONResponse:
    operation = "generate_summary" if processing_mode == "summary" else "generate_transcript"
    request_payload = {
        "series_id": series_id,
        "video_id": video_id,
        "processing_mode": processing_mode,
        "transcript_enhancement_enabled": transcript_enhancement_enabled,
        "use_saved_manual_transcript": use_saved_manual_transcript,
    }
    if manual_transcript is not None:
        request_payload["manual_transcript"] = manual_transcript
    try:
        workspace = container.sql_workspace.get_workspace()
        if not workspace.id:
            raise RuntimeError("No SQL workspace is available for job submission.")
        submitted = container.job_repository.submit(
            workspace_id=workspace.id,
            resource_type="video",
            resource_id=video_id,
            operation=operation,
            request_payload=request_payload,
            active_key=f"video:{video_id}:{operation}",
            idempotency_scope_id=workspace.id if idempotency_key else None,
            idempotency_key=idempotency_key,
        )
    except ControlPlaneConflictError as error:
        active = container.job_repository.active_for_resource(
            workspace_id=workspace.id,
            resource_id=video_id,
            operation=operation,
        )
        if active is None:
            raise HTTPException(status_code=409, detail=str(error)) from error
        submitted = active
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
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


@router.post("/api/videos/{series_id}/{video_id}/transcript/srt-and-generate")
async def upload_srt_and_generate_video_summary(
    series_id: str,
    video_id: str,
    file: UploadFile = File(...),
    http_request: Request = None,
    container: ApiContainerDep = None,
) -> JSONResponse:
    """上传人工 SRT，并在同一原子生成任务中产出新的 AI 概况。"""
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() != ".srt":
        raise HTTPException(status_code=400, detail="请选择 .srt 字幕文件")
    try:
        raw_srt = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=400, detail="SRT 文件必须使用 UTF-8 编码") from error
    try:
        parse_srt_transcript(raw_srt)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=400, detail=f"SRT 解析失败：{error}") from error

    _ensure_source_media_available(_require_video_source(container, series_id, video_id))
    return _submit_video_generation_job(
        container=container,
        series_id=series_id,
        video_id=video_id,
        processing_mode="summary",
        transcript_enhancement_enabled=None,
        idempotency_key=http_request.headers.get("Idempotency-Key") if http_request is not None else None,
        manual_transcript={"raw_srt": raw_srt, "filename": filename},
    )


@router.post("/api/videos/{series_id}/{video_id}/transcript/restore-auto-and-generate")
async def restore_automatic_transcript_and_generate_video_summary(
    series_id: str,
    video_id: str,
    http_request: Request,
    container: ApiContainerDep = None,
) -> JSONResponse:
    """改用自动字幕/ASR 重新生成，成功后才移除当前人工 SRT。"""
    _ensure_source_media_available(_require_video_source(container, series_id, video_id))
    return _submit_video_generation_job(
        container=container,
        series_id=series_id,
        video_id=video_id,
        processing_mode="summary",
        transcript_enhancement_enabled=None,
        idempotency_key=http_request.headers.get("Idempotency-Key"),
        use_saved_manual_transcript=False,
    )


@router.post("/api/videos/{series_id}/{video_id}/generate/cancel")
async def cancel_video_summary_generation(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    """POST /api/videos/{series_id}/{video_id}/generate/cancel — 取消正在进行的视频总结生成。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"status": "cancelled", "task_id": ...}
    """
    job_repository = getattr(container, "job_repository", None)
    if job_repository is not None:
        snapshot = job_repository.request_cancel_for_resource(workspace_id=container.sql_workspace.workspace_id, resource_id=video_id, operation="generate_summary")
        if snapshot is None:
            raise HTTPException(status_code=404, detail="no active generation job found")
        return {"status": snapshot.status, "job_id": snapshot.id}
    task_id = _build_task_id(series_id, video_id)
    container.generation_progress_tracker.request_cancel(task_id)
    container.video_download_progress_tracker.request_cancel(build_video_download_task_id(series_id, video_id))

    cancel_generation = getattr(container.generate_video_summary, "cancel", None)
    if callable(cancel_generation):
        await cancel_generation(series_id, video_id)

    finalize_cancel = getattr(container.generation_progress_tracker, "cancel", None)
    if callable(finalize_cancel):
        finalize_cancel(task_id, "任务已取消")
    return {"status": "cancelled", "task_id": task_id}


@router.post("/api/series/{series_id}/generate")
async def generate_series_summaries(
    series_id: str,
    request: GenerateSeriesSummariesRequest | None = None,
    container: ApiContainerDep = None,
) -> dict[str, object]:
    """POST /api/series/{series_id}/generate — 触发系列下所有未处理视频的批量总结生成。

    按队列调度串联每个视频的生成流程；前端通过系列级 SSE 进度端点订阅进度。

    Args:
        series_id: 系列 ID。
        request: 可选的批次参数（如 transcript_enhancement_enabled 和 run_id）。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"series_id": ..., "completed_videos": ..., "skipped_videos": ..., "cancelled_videos": ..., "cancelled_video_id": ...}

    Raises:
        HTTPException(400): 参数无效。
        HTTPException(404): 系列不存在。
        HTTPException(409): 重复触发或 scope 忙碌。
        HTTPException(503): 生成过程发生运行时错误。
    """
    processing_mode = "summary" if request is None else request.processing_mode
    arguments = {
        "transcript_enhancement_enabled": None if request is None else request.transcript_enhancement_enabled,
        "run_id": None if request is None else request.run_id,
    }
    if processing_mode != "summary":
        arguments["processing_mode"] = processing_mode
    try:
        result = await container.generate_series_summaries.run(series_id, **arguments)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except DuplicateSeriesGenerationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except GenerationScopeBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "series_id": result.series_id,
        "completed_videos": result.completed_videos,
        "skipped_videos": result.skipped_videos,
        "skipped_video_errors": result.skipped_video_errors,
        "cancelled_videos": result.cancelled_videos,
        "cancelled_video_id": result.cancelled_video_id,
    }


@router.post("/api/series/{series_id}/generate/cancel")
async def cancel_series_summaries_generation(
    series_id: str,
    container: ApiContainerDep,
    request: CancelSeriesSummariesRequest | None = None,
) -> dict[str, object]:
    """POST /api/series/{series_id}/generate/cancel — 取消系列级批量生成。

    取消系列任务并向所有进行中的单个视频生成和链接型视频下载发送取消信号。
    若请求中的 run_id 与当前活跃 run_id 不匹配则忽略本次取消（防止误取消新批次）。

    Args:
        series_id: 系列 ID。
        container: FastAPI 依赖注入的 API 容器。
        request: 可选的 run_id 匹配参数，用于防误取消。

    Returns:
        {"status": "cancelled"/"stale", "task_id": ..., "cancelled_video_ids": [...]}
    """
    series_task_id = _build_series_task_id(series_id)
    requested_run_id = None if request is None else request.run_id
    get_active_run_id = getattr(container.generate_series_summaries, "get_active_run_id", None)
    active_run_id = get_active_run_id(series_id) if callable(get_active_run_id) else None
    if requested_run_id is not None and active_run_id is not None and requested_run_id != active_run_id:
        LOGGER.info(
            "Ignoring stale series cancel: series_id=%s requested_run_id=%s active_run_id=%s",
            series_id,
            requested_run_id,
            active_run_id,
        )
        return {
            "status": "stale",
            "task_id": series_task_id,
            "active_run_id": active_run_id,
            "cancelled_video_ids": [],
        }
    pending_videos = _get_pending_series_videos(container, series_id)
    active_video_ids = container.generate_series_summaries.get_active_video_ids(series_id)
    linked_video_ids = {video.id for video in pending_videos if video.is_linked or video.status == "linked"}
    cancelled_video_ids = list(dict.fromkeys([*active_video_ids, *linked_video_ids]))
    LOGGER.info(
        "Cancelling series generation: series_id=%s requested_run_id=%s active_run_id=%s "
        "pending_video_ids=%s active_video_ids=%s linked_video_ids=%s cancelled_video_ids=%s",
        series_id,
        requested_run_id,
        active_run_id,
        [video.id for video in pending_videos],
        active_video_ids,
        sorted(linked_video_ids),
        cancelled_video_ids,
    )
    for video_id in active_video_ids:
        task_id = _build_task_id(series_id, video_id)
        container.generation_progress_tracker.request_cancel(task_id)
        cancel_generation = getattr(container.generate_video_summary, "cancel", None)
        if callable(cancel_generation):
            await cancel_generation(series_id, video_id)
        finalize_cancel = getattr(container.generation_progress_tracker, "cancel", None)
        if callable(finalize_cancel):
            finalize_cancel(task_id, "任务已取消")
    for video_id in linked_video_ids:
        container.video_download_progress_tracker.request_cancel(build_video_download_task_id(series_id, video_id))
    container.generation_progress_tracker.request_cancel(series_task_id)
    finalize_series_cancel = getattr(container.generation_progress_tracker, "cancel", None)
    if callable(finalize_series_cancel):
        finalize_series_cancel(series_task_id, "任务已取消")
    return {
        "status": "cancelled",
        "task_id": series_task_id,
        "cancelled_video_ids": cancelled_video_ids,
    }


@router.post("/api/videos/{series_id}/{video_id}/mindmap/generate")
def generate_video_mindmap(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
    request: GenerateMindmapRequest = Body(default_factory=GenerateMindmapRequest),
) -> JSONResponse:
    """POST /api/videos/{series_id}/{video_id}/mindmap/generate — 生成视频思维导图。

    基于已有总结调用 LLM 生成思维导图节点树并落盘；通过 SSE 进度端点订阅实时状态。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        JSON 字典，含思维导图节点树。

    Raises:
        HTTPException(404): 总结未生成。
    """
    _ensure_video_exists(container, series_id, video_id)
    try:
        submitted = container.job_repository.submit(
            workspace_id=container.sql_workspace.workspace_id,
            resource_type="video",
            resource_id=video_id,
            operation="generate_video_mindmap",
            request_payload={"series_id": series_id, "video_id": video_id, "max_depth": request.max_depth},
            active_key=f"video:{video_id}:generate_video_mindmap",
            idempotency_scope_id=None,
            idempotency_key=None,
        )
    except ControlPlaneConflictError as error:
        active = container.job_repository.active_for_resource(
            workspace_id=container.sql_workspace.workspace_id,
            resource_id=video_id,
            operation="generate_video_mindmap",
        )
        if active is None:
            raise HTTPException(status_code=409, detail=str(error)) from error
        submitted = active
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


@router.get("/api/series/{series_id}/mindmap")
def get_series_mindmap(series_id: str, container: ApiContainerDep) -> dict[str, object]:
    mindmap = container.get_series_mindmap.run(series_id)
    if mindmap is None:
        raise HTTPException(status_code=404, detail=f"series mindmap not found for '{series_id}'")
    return mindmap.mindmap


@router.post("/api/series/{series_id}/mindmap/generate")
def generate_series_mindmap(
    series_id: str,
    container: ApiContainerDep,
    request: GenerateMindmapRequest = Body(default_factory=GenerateMindmapRequest),
) -> JSONResponse:
    """POST /api/series/{series_id}/mindmap/generate — 触发系列思维导图生成。

    基于系列下已生成概况的视频聚合生成思维导图；通过 SSE 进度端点订阅实时状态。
    同一系列并发请求会返回 409。

    Args:
        series_id: 系列 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        JSON 字典，含思维导图节点树。

    Raises:
        HTTPException(400): 系列下没有已生成概况的视频。
        HTTPException(409): 该系列思维导图正在生成中。
    """
    try:
        submitted = container.job_repository.submit(
            workspace_id=container.sql_workspace.workspace_id,
            resource_type="series",
            resource_id=series_id,
            operation="generate_series_mindmap",
            request_payload={"series_id": series_id, "max_depth": request.max_depth},
            active_key=f"series:{series_id}:generate_series_mindmap",
            idempotency_scope_id=None,
            idempotency_key=None,
        )
    except ControlPlaneConflictError as error:
        active = container.job_repository.active_for_resource(
            workspace_id=container.sql_workspace.workspace_id,
            resource_id=series_id,
            operation="generate_series_mindmap",
        )
        if active is None:
            raise HTTPException(status_code=409, detail=str(error)) from error
        submitted = active
    return JSONResponse(
        status_code=202,
        content={
            "job_id": submitted.id,
            "status": submitted.status,
            "resource": {"type": "series", "id": series_id},
            "status_url": f"/api/jobs/{submitted.id}",
            "events_url": f"/api/jobs/{submitted.id}/events",
        },
    )


@router.get("/api/series/{series_id}/mindmap/export")
def export_series_mindmap(series_id: str, format: str = "md", container: ApiContainerDep = None):
    if format not in ("md", "html"):
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}，仅支持 md / html")
    mindmap = container.get_series_mindmap.run(series_id)
    if mindmap is None:
        raise HTTPException(status_code=404, detail=f"series mindmap not found for '{series_id}'")
    if format == "html":
        content = render_mindmap_html(mindmap.mindmap, mindmap.title)
        filename = f"{mindmap.title}-mindmap.html"
        return _html_response(content, filename)
    markdown = render_mindmap_markdown(mindmap.mindmap)
    filename = f"{mindmap.title}-mindmap.md"
    return _markdown_response(markdown, filename)


@router.get("/api/series/{series_id}/exports/{export_kind}.zip")
def export_series_archive(
    series_id: str,
    export_kind: str,
    container: ApiContainerDep,
    video_ids: str = "",
) -> Response:
    """GET /api/series/{series_id}/exports/{kind}.zip — 批量导出系列制品压缩包。"""
    try:
        selected_video_ids = list(dict.fromkeys(item.strip() for item in video_ids.split(",") if item.strip()))
        archive = (
            container.export_series_archive.run(series_id, export_kind, selected_video_ids)
            if selected_video_ids
            else container.export_series_archive.run(series_id, export_kind)
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _zip_response(archive.content, archive.filename)


@router.delete("/api/series/{series_id}")
def delete_series(series_id: str, container: ApiContainerDep) -> dict[str, object]:
    """DELETE /api/series/{series_id} — 删除整个系列及其全部制品。

    级联删除系列下的所有视频制品文件和 RAG 索引条目。

    Args:
        series_id: 系列 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"status": "deleted", "series_id": ...}

    Raises:
        HTTPException(400): 参数无效。
        HTTPException(404): 系列不存在。
        HTTPException(409): 系列下有进行中的生成任务。
    """
    try:
        deleted = container.delete_series.run(series_id)
    except GenerationInProgressError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "deleted", "series_id": deleted.series_id}


@router.patch("/api/series/{series_id}")
def rename_series(
    series_id: str,
    request: RenameTitleRequest,
    container: ApiContainerDep,
) -> dict[str, str]:
    """更新系列展示名称，不改变文件夹名称或系列 ID。"""
    try:
        renamed = container.rename_series.run(series_id, request.title)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"series_id": renamed.series_id, "title": renamed.title}


@router.delete("/api/videos/{series_id}/{video_id}")
def delete_video_source(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, object]:
    """DELETE /api/videos/{series_id}/{video_id} — 删除单个视频及其全部制品。

    级联删除视频的制品文件（总结、转写、思维导图等）和 RAG 索引条目。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"status": "deleted", "series_id": ..., "video_id": ...}

    Raises:
        HTTPException(404): 视频不存在。
        HTTPException(409): 视频正在进行生成任务。
    """
    try:
        deleted = container.delete_video_source.run(series_id, video_id)
    except GenerationInProgressError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "deleted", "series_id": deleted.series_id, "video_id": deleted.video_id}


@router.patch("/api/videos/{series_id}/{video_id}")
def rename_video(
    series_id: str,
    video_id: str,
    request: RenameTitleRequest,
    container: ApiContainerDep,
) -> dict[str, str]:
    """更新视频展示名称，不重命名原媒体文件或视频 ID。"""
    try:
        renamed = container.rename_video.run(series_id, video_id, request.title)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"series_id": renamed.series_id, "video_id": renamed.video_id, "title": renamed.title}


@router.get("/api/videos/{series_id}/{video_id}/generate/progress")
async def stream_video_generation_progress(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    """GET /api/videos/{series_id}/{video_id}/generate/progress — 订阅单视频生成进度流（SSE）。

    以 SSE 推送视频生成的状态变化、进度百分比与详情（ASR → LLM 总结 → 落盘）；
    到达 terminal 状态后自动关闭。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        StreamingResponse（`text/event-stream`）。
    """
    task_id = _build_task_id(series_id, video_id)
    return StreamingResponse(
        stream_progress_events(
            tracker=container.generation_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/videos/{series_id}/{video_id}/generate/status")
def get_video_generation_status(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    """GET /api/videos/{series_id}/{video_id}/generate/status — 查询单视频生成任务的当前状态（一次性快照）。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"task_id": ..., "snapshot": {status, progress, detail, ...}}
    """
    task_id = _build_task_id(series_id, video_id)
    job_repository = getattr(container, "job_repository", None)
    if job_repository is not None:
        snapshot = job_repository.latest_for_resource(
            workspace_id=container.sql_workspace.workspace_id,
            resource_id=video_id,
            operations=("generate_summary", "generate_transcript"),
        )
        if snapshot is not None:
            event = job_repository.latest_event(snapshot.id, workspace_id=container.sql_workspace.workspace_id)
            return {
                "task_id": task_id,
                "job_id": snapshot.id,
                "snapshot": {
                    "status": snapshot.status,
                    "stage": event.stage if event is not None else snapshot.status,
                    "progress": event.progress if event is not None else (100.0 if snapshot.status == "succeeded" else 0.0),
                    "detail": snapshot.failure_detail or (event.detail if event is not None else None),
                    "error": snapshot.failure_detail if snapshot.status == "failed" else None,
                },
            }
    return {
        "task_id": task_id,
        "snapshot": container.generation_progress_tracker.get_snapshot(task_id).to_dict(),
    }


@router.get("/api/series/{series_id}/generate/progress")
async def stream_series_generation_progress(
    series_id: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    """GET /api/series/{series_id}/generate/progress — 订阅系列级批量生成进度流（SSE）。

    以 SSE 推送整个系列生成批次的进度；到达 terminal 状态后自动关闭。

    Args:
        series_id: 系列 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        StreamingResponse（`text/event-stream`）。
    """
    task_id = _build_series_task_id(series_id)
    return StreamingResponse(
        stream_progress_events(
            tracker=container.generation_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/series/{series_id}/generate/status")
def get_series_generation_status(
    series_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    """GET /api/series/{series_id}/generate/status — 查询系列级生成任务的当前状态（一次性快照）。

    Args:
        series_id: 系列 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"task_id": ..., "snapshot": {status, progress, detail, ...}}
    """
    task_id = _build_series_task_id(series_id)
    return {
        "task_id": task_id,
        "snapshot": container.generation_progress_tracker.get_snapshot(task_id).to_dict(),
    }


def _build_task_id(series_id: str, video_id: str) -> str:
    """构建单个视频的进度跟踪任务 ID。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。

    Returns:
        格式为 `{series_id}/{video_id}` 的任务 ID。
    """
    return f"{series_id}/{video_id}"


def _build_series_task_id(series_id: str) -> str:
    """构建系列级批量生成的进度跟踪任务 ID。

    Args:
        series_id: 系列 ID。

    Returns:
        格式为 `series/{series_id}` 的任务 ID。
    """
    return f"series/{series_id}"


def _build_mindmap_task_id(series_id: str, video_id: str) -> str:
    """构建单视频思维导图生成的进度跟踪任务 ID。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。

    Returns:
        格式为 `mindmap|{series_id}|{video_id}` 的任务 ID。
    """
    return f"mindmap|{series_id}|{video_id}"


def _get_pending_series_videos(container, series_id: str) -> list[object]:
    """获取系列下所有未处理（processed=False）的视频列表。

    Args:
        container: API 容器。
        series_id: 系列 ID。

    Returns:
        未处理视频的列表。

    Raises:
        HTTPException(404): 系列不存在。
    """
    library = container.list_video_library.run()
    series = next((item for item in library.series if item.id == series_id), None)
    if series is None:
        raise HTTPException(status_code=404, detail=f"series not found '{series_id}'")
    return [video for video in series.videos if not video.processed]


def _ensure_video_exists(container, series_id: str, video_id: str):
    """确认视频资源存在；媒体动作由调用方额外要求可用源文件。

    Args:
        container: API 容器。
        series_id: 系列 ID。
        video_id: 视频 ID。

    Returns:
        视频的源文件 DTO。

    Raises:
        HTTPException(404): 视频不存在。
    """
    source_query = getattr(container, "get_video_source", None)
    if source_query is not None and source_query.run(series_id, video_id) is not None:
        return source_query.run(series_id, video_id)
    library_query = getattr(container, "list_video_library", None)
    if library_query is None:
        # Minimal embedded/test containers can expose artifact query use cases
        # without a full library projection. Production SQL containers always
        # provide list_video_library and retain the stronger membership check.
        return None
    library = library_query.run()
    series = next((item for item in library.series if item.id == series_id), None)
    if series is None or not any(video.id == video_id for video in series.videos):
        raise HTTPException(status_code=404, detail=f"未找到该视频，可能尚未下载：{series_id}/{video_id}")
    return source_query.run(series_id, video_id) if source_query is not None else None


def _ensure_source_media_available(source) -> None:
    """将断开的外部媒体引用转换为可读的 HTTP 错误。"""
    if not source.source_path.is_file():
        raise HTTPException(status_code=503, detail=f"source media unavailable: {source.source_path}")


def _require_video_source(container, series_id: str, video_id: str):
    _ensure_video_exists(container, series_id, video_id)
    source = container.get_video_source.run(series_id, video_id)
    if source is None:
        raise HTTPException(status_code=503, detail=f"source media unavailable: {series_id}/{video_id}")
    return source


def _html_response(html: str, filename: str) -> Response:
    """构造带 Content-Disposition 下载头的 HTML HTTP 响应。

    Args:
        html: 渲染后的 HTML 文本内容。
        filename: 下载文件名。

    Returns:
        Response（`text/html; charset=utf-8`）。
    """
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": _content_disposition_attachment(filename)},
    )


def _markdown_response(markdown: str, filename: str) -> Response:
    """构造带 Content-Disposition 下载头的 Markdown HTTP 响应。

    Args:
        markdown: 渲染后的 Markdown 文本内容。
        filename: 下载文件名。

    Returns:
        Response（`text/markdown; charset=utf-8`）。
    """
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": _content_disposition_attachment(filename)},
    )


def _zip_response(content: bytes, filename: str) -> Response:
    """构造带 Content-Disposition 下载头的 ZIP HTTP 响应。"""
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition_attachment(filename)},
    )


def _content_disposition_attachment(filename: str) -> str:
    """构建兼容 ASCII 和 UTF-8 的 Content-Disposition attachment 头。

    Args:
        filename: 原始文件名（可能含中文等非 ASCII 字符）。

    Returns:
        格式为 `attachment; filename="..."; filename*=UTF-8''...` 的头值。
    """
    ascii_filename = filename.encode("ascii", errors="ignore").decode("ascii") or "export.md"
    quoted_filename = ascii_filename.replace("\\", "\\\\").replace('"', r"\"")
    encoded_filename = quote(filename, safe="")
    return f'attachment; filename="{quoted_filename}"; filename*=UTF-8\'\'{encoded_filename}'


def _export_filename(video_id: str, export_name: str, suffix: str = ".md") -> str:
    """构建导出文件的文件名（Markdown 类）。

    Args:
        video_id: 视频 ID。
        export_name: 导出类型名（如 "summary"、"transcript"）。

    Returns:
        格式为 `{safe_video_id}-{export_name}.md` 的文件名。
    """
    return f"{_safe_filename_part(video_id)}-{export_name}{suffix}"


def _video_export_filename(video_id: str, suffix: str) -> str:
    """构建原始视频文件的导出文件名。

    Args:
        video_id: 视频 ID。
        suffix: 原始文件后缀（如 `.mp4`）。

    Returns:
        格式为 `{safe_video_id}{suffix}` 的文件名。
    """
    return f"{_safe_filename_part(video_id)}{suffix}"


def _safe_filename_part(value: str) -> str:
    """将字符串清洗为安全的文件名字段（仅保留字母、数字、连字符和下划线）。

    Args:
        value: 原始字符串。

    Returns:
        清洗后的安全字符串，若清洗后为空则返回 "video"。
    """
    result = []
    for char in value.strip():
        if char.isalnum() or char in {"-", "_"}:
            result.append(char)
        else:
            result.append("-")
    return "".join(result).strip("-") or "video"
