"""视频库管理路由。

提供视频库的增删查改、视频总结/思维导图/知识卡的生成与导出、
本地文件导入、以及生成进度 SSE 流的 HTTP 端点。
"""

from __future__ import annotations

import asyncio
import logging
import json
import mimetypes
from threading import Lock
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse

from backend.api.container import ApiContainerDep
from backend.api.contracts import (
    CancelSeriesSummariesRequest,
    CreateVideoNoteRequest,
    GenerateSeriesSummariesRequest,
    GenerateVideoSummaryRequest,
    UpdateVideoNoteRequest,
)
from backend.api.responses import (
    SeriesResponse,
    VideoCardResponse,
    VideoChapterCardsResponse,
    VideoKnowledgeCardsResponse,
    VideoLibraryResponse,
    VideoNoteResponse,
    VideoNotesResponse,
    VideoWorkspaceToolsResponse,
)
from backend.api.sse import stream_progress_events
from backend.bilibili.ytdlp_bilibili import build_video_download_task_id
from backend.video_summary.infrastructure.video_summary_runtime import AsrModelNotReadyError
from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError
from backend.video_summary.library.markdown_exports import render_knowledge_cards_markdown
from backend.video_summary.library.markdown_exports import render_mixed_overview_markdown
from backend.video_summary.library.markdown_exports import render_notes_markdown
from backend.video_summary.library.markdown_exports import render_transcript_markdown
from backend.video_summary.library.usecases.mutations import GenerationInProgressError
from backend.video_summary.library.usecases.summary_generation import DuplicateSeriesGenerationError
from backend.video_summary.library.usecases.summary_generation import GenerationScopeBusyError
from backend.video_summary.infrastructure.mindmap_export import render_mindmap_html, render_mindmap_markdown

router = APIRouter()
LOGGER = logging.getLogger(__name__)

_series_mindmap_locks: dict[str, Lock] = {}
_series_mindmap_locks_guard = Lock()

def _acquire_series_mindmap_lock(series_id: str) -> bool:
    with _series_mindmap_locks_guard:
        if series_id in _series_mindmap_locks:
            return False
        _series_mindmap_locks[series_id] = Lock()
        return True

def _release_series_mindmap_lock(series_id: str) -> None:
    with _series_mindmap_locks_guard:
        _series_mindmap_locks.pop(series_id, None)


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


@router.get("/api/videos/{series_id}/{video_id}/exports/summary.md")
def export_video_summary_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> FileResponse:
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
    source = _ensure_video_exists(container, series_id, video_id)
    summary_path = source.output_dir / "summary.md"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail=f"summary markdown not found for video '{series_id}/{video_id}'")
    return FileResponse(
        summary_path,
        media_type="text/markdown; charset=utf-8",
        filename=_export_filename(video_id, "summary"),
    )


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
    source = _ensure_video_exists(container, series_id, video_id)
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
    source = _ensure_video_exists(container, series_id, video_id)
    transcript_path = source.output_dir / "transcript.cleaned.json"
    if not transcript_path.exists():
        raise HTTPException(status_code=404, detail=f"transcript not found for video '{series_id}/{video_id}'")
    markdown = render_transcript_markdown(json.loads(transcript_path.read_text(encoding="utf-8")))
    return _markdown_response(markdown, _export_filename(video_id, "transcript"))


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
    source = _ensure_video_exists(container, series_id, video_id)
    summary_path = source.output_dir / "summary.json"
    transcript_path = source.output_dir / "transcript.cleaned.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    if not transcript_path.exists():
        raise HTTPException(status_code=404, detail=f"transcript not found for video '{series_id}/{video_id}'")
    markdown = render_mixed_overview_markdown(
        json.loads(summary_path.read_text(encoding="utf-8")),
        json.loads(transcript_path.read_text(encoding="utf-8")),
    )
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
    source = _ensure_video_exists(container, series_id, video_id)
    cards_path = source.output_dir / "knowledge_cards.json"
    if not cards_path.exists():
        raise HTTPException(status_code=404, detail=f"knowledge cards not found for video '{series_id}/{video_id}'")
    markdown = render_knowledge_cards_markdown(json.loads(cards_path.read_text(encoding="utf-8")))
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
    source = _ensure_video_exists(container, series_id, video_id)
    notes_path = source.output_dir / "notes.json"
    if not notes_path.exists():
        raise HTTPException(status_code=404, detail=f"notes not found for video '{series_id}/{video_id}'")
    payload = json.loads(notes_path.read_text(encoding="utf-8"))
    notes = payload.get("notes")
    if not isinstance(notes, list) or not notes:
        raise HTTPException(status_code=404, detail=f"notes not found for video '{series_id}/{video_id}'")
    markdown = render_notes_markdown(source.title, payload)
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


@router.post("/api/videos/{series_id}/{video_id}/knowledge-cards/generate", response_model=VideoKnowledgeCardsResponse)
def generate_video_knowledge_cards(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> VideoKnowledgeCardsResponse:
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
        video_cards = container.generate_video_cards.run(series_id, video_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if video_cards is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    return VideoKnowledgeCardsResponse.from_model(video_cards)


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
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    return VideoNotesResponse.from_model(video_notes)


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
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
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
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
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
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
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
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    return VideoWorkspaceToolsResponse.from_model(video_tools)


@router.get("/api/videos/{series_id}/{video_id}/preview")
def preview_video(series_id: str, video_id: str, container: ApiContainerDep) -> FileResponse:
    """GET /api/videos/{series_id}/{video_id}/preview — 获取视频源文件用于浏览器预览。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        FileResponse，直接返回原始视频文件。

    Raises:
        HTTPException(404): 视频不存在。
    """
    source = container.get_video_source.run(series_id, video_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    return FileResponse(source.source_path)


@router.post("/api/videos/{series_id}/{video_id}/generate")
async def generate_video_summary(
    series_id: str,
    video_id: str,
    request: GenerateVideoSummaryRequest | None = None,
    container: ApiContainerDep = None,
) -> dict[str, object]:
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
    try:
        video_summary = await container.generate_video_summary.run(
            series_id,
            video_id,
            transcript_enhancement_enabled=(
                None if request is None else request.transcript_enhancement_enabled
            ),
        )
    except AsrModelNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except GenerateCancelledError as error:
        raise HTTPException(status_code=409, detail="generation cancelled") from error
    except GenerationScopeBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if video_summary is None:
        snapshot = container.generation_progress_tracker.get_snapshot(_build_task_id(series_id, video_id))
        if snapshot.status == "cancelled":
            raise HTTPException(status_code=409, detail="generation cancelled")
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    return video_summary.summary


@router.post("/api/videos/{series_id}/{video_id}/generate/cancel")
def cancel_video_summary_generation(
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
    container.generation_progress_tracker.request_cancel(_build_task_id(series_id, video_id))
    return {"status": "cancelled", "task_id": _build_task_id(series_id, video_id)}


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
    try:
        result = await container.generate_series_summaries.run(
            series_id,
            transcript_enhancement_enabled=(None if request is None else request.transcript_enhancement_enabled),
            run_id=(None if request is None else request.run_id),
        )
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
        "cancelled_videos": result.cancelled_videos,
        "cancelled_video_id": result.cancelled_video_id,
    }


@router.post("/api/series/{series_id}/generate/cancel")
def cancel_series_summaries_generation(
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
    container.generation_progress_tracker.request_cancel(series_task_id)
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
        container.generation_progress_tracker.request_cancel(_build_task_id(series_id, video_id))
    for video_id in linked_video_ids:
        container.video_download_progress_tracker.request_cancel(build_video_download_task_id(series_id, video_id))
    if not active_video_ids:
        container.generation_progress_tracker.create_reporter(series_task_id).cancelled("任务已取消")
    return {
        "status": "cancelled",
        "task_id": series_task_id,
        "cancelled_video_ids": cancelled_video_ids,
    }


@router.post("/api/videos/{series_id}/{video_id}/mindmap/generate")
async def generate_video_mindmap(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
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
    import sys
    task_id = _build_mindmap_task_id(series_id, video_id)
    reporter = container.mindmap_progress_tracker.create_reporter(task_id)
    try:
        reporter.update("generate", 0.0, "正在生成思维导图")
        video_mindmap = await container.generate_video_mindmap.run(
            series_id,
            video_id,
            progress_reporter=reporter,
        )
    except Exception:
        reporter.failed(str(sys.exc_info()[1]) if sys.exc_info()[1] else "思维导图生成失败")
        raise
    if video_mindmap is None:
        reporter.failed("总结不存在，无法生成思维导图")
        raise HTTPException(
            status_code=404,
            detail=f"summary not found for video '{series_id}/{video_id}'",
        )
    reporter.completed("思维导图已生成")
    return video_mindmap.mindmap


@router.get("/api/videos/{series_id}/{video_id}/mindmap/generate/progress")
async def stream_mindmap_generation_progress(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    """GET /api/videos/{series_id}/{video_id}/mindmap/generate/progress — 订阅单视频思维导图生成进度流（SSE）。

    以 SSE 推送思维导图生成的状态变化、进度百分比与详情；到达 terminal 状态后自动关闭。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        StreamingResponse（`text/event-stream`）。
    """
    task_id = _build_mindmap_task_id(series_id, video_id)
    return StreamingResponse(
        stream_progress_events(
            tracker=container.mindmap_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/series/{series_id}/mindmap")
def get_series_mindmap(series_id: str, container: ApiContainerDep) -> dict[str, object]:
    mindmap = container.get_series_mindmap.run(series_id)
    if mindmap is None:
        raise HTTPException(status_code=404, detail=f"series mindmap not found for '{series_id}'")
    return mindmap.mindmap


@router.post("/api/series/{series_id}/mindmap/generate")
async def generate_series_mindmap(series_id: str, container: ApiContainerDep) -> dict[str, object]:
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
    import sys
    if not _acquire_series_mindmap_lock(series_id):
        raise HTTPException(status_code=409, detail="该系列导图正在生成中，请稍后再试")
    task_id = _build_series_mindmap_task_id(series_id)
    reporter = container.mindmap_progress_tracker.create_reporter(task_id)
    try:
        reporter.update("generate", 0.0, "正在生成系列思维导图")
        try:
            mindmap = await container.generate_series_mindmap.run(
                series_id,
                progress_reporter=reporter,
            )
        except Exception:
            reporter.failed(str(sys.exc_info()[1]) if sys.exc_info()[1] else "系列思维导图生成失败")
            raise
        if mindmap is None:
            reporter.failed("系列下没有已生成概况的视频")
            raise HTTPException(status_code=400, detail="系列下没有已生成概况的视频")
        reporter.completed("系列思维导图已生成")
        return mindmap.mindmap
    finally:
        _release_series_mindmap_lock(series_id)


@router.get("/api/series/{series_id}/mindmap/generate/progress")
async def stream_series_mindmap_generation_progress(
    series_id: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    """GET /api/series/{series_id}/mindmap/generate/progress — 订阅系列思维导图生成进度流（SSE）。

    以 SSE 推送系列思维导图生成的状态变化、进度百分比与详情；到达 terminal 状态后自动关闭。

    Args:
        series_id: 系列 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        StreamingResponse（`text/event-stream`）。
    """
    task_id = _build_series_mindmap_task_id(series_id)
    return StreamingResponse(
        stream_progress_events(
            tracker=container.mindmap_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
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


@router.post("/api/import/local/series", response_model=SeriesResponse)
async def import_local_series(
    series_title: str = Form(...),
    files: list[UploadFile] = File(...),
    container: ApiContainerDep = None,
) -> SeriesResponse:
    """POST /api/import/local/series — 上传本地视频文件并创建新系列。

    将上传的一组视频文件导入为新的系列；接收 multipart/form-data。

    Args:
        series_title: 系列标题（Form 字段）。
        files: 上传的视频文件列表。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        SeriesResponse，含新创建的系列信息。

    Raises:
        HTTPException(400): 输入参数或文件无效。
    """
    try:
        series = container.import_local_series.run(
            title=series_title,
            files=[(file.filename or "", file.file) for file in files],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await asyncio.gather(*(file.close() for file in files), return_exceptions=True)

    return SeriesResponse.from_model(series)


@router.post("/api/import/local/playground", response_model=list[VideoCardResponse])
async def import_local_playground_videos(
    files: list[UploadFile] = File(...),
    container: ApiContainerDep = None,
) -> list[VideoCardResponse]:
    """POST /api/import/local/playground — 上传本地视频到沙盒演练系列。

    无需指定系列，视频直接导入到内置的 playground 系列；接收 multipart/form-data。

    Args:
        files: 上传的视频文件列表。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        导入后的 VideoCardResponse 列表。

    Raises:
        HTTPException(400): 输入参数或文件无效。
    """
    try:
        videos = container.import_local_playground_videos.run(
            files=[(file.filename or "", file.file) for file in files],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await asyncio.gather(*(file.close() for file in files), return_exceptions=True)

    return [VideoCardResponse.from_model(video) for video in videos]


@router.post("/api/import/local/series/{series_id}", response_model=list[VideoCardResponse])
async def import_local_series_videos(
    series_id: str,
    files: list[UploadFile] = File(...),
    container: ApiContainerDep = None,
) -> list[VideoCardResponse]:
    """POST /api/import/local/series/{series_id} — 上传本地视频追加到已有系列。

    接收 multipart/form-data，将视频文件追加到指定系列的末尾。

    Args:
        series_id: 目标系列 ID。
        files: 上传的视频文件列表。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        导入后的 VideoCardResponse 列表。

    Raises:
        HTTPException(400): 输入参数或文件无效。
    """
    try:
        videos = container.import_local_series_videos.run(
            series_id=series_id,
            files=[(file.filename or "", file.file) for file in files],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await asyncio.gather(*(file.close() for file in files), return_exceptions=True)

    return [VideoCardResponse.from_model(video) for video in videos]


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


def _build_series_mindmap_task_id(series_id: str) -> str:
    """构建系列思维导图生成的进度跟踪任务 ID。

    Args:
        series_id: 系列 ID。

    Returns:
        格式为 `series-mindmap|{series_id}` 的任务 ID。
    """
    return f"series-mindmap|{series_id}"


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
    """确认视频存在并返回其源文件信息；不存在则抛出 404。

    Args:
        container: API 容器。
        series_id: 系列 ID。
        video_id: 视频 ID。

    Returns:
        视频的源文件 DTO。

    Raises:
        HTTPException(404): 视频不存在。
    """
    source = container.get_video_source.run(series_id, video_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
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


def _export_filename(video_id: str, export_name: str) -> str:
    """构建导出文件的文件名（Markdown 类）。

    Args:
        video_id: 视频 ID。
        export_name: 导出类型名（如 "summary"、"transcript"）。

    Returns:
        格式为 `{safe_video_id}-{export_name}.md` 的文件名。
    """
    return f"{_safe_filename_part(video_id)}-{export_name}.md"


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
