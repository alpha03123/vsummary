"""Strongly typed application services bound to exactly one Workspace."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from backend.agent import AgentContextBudgetService
from backend.agent_graph.runtime.service import AgentGraphService
from backend.api.workers.workspace_index_worker import _WorkspaceIndexInvalidator
from backend.bilibili import DrissionBilibiliCookieInitializer
from backend.external import DrissionCookieInitializer
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.persistence.job_repository import ClaimedJob
from backend.video_summary.infrastructure.persistence.job_worker import SqlJobProgressReporter
from backend.video_summary.infrastructure.persistence.sql_agent_session_store import SqlAgentSessionStore
from backend.video_summary.infrastructure.persistence.sql_generation_adapters import SqlBackedVideoSummaryGenerator
from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace
from backend.video_summary.infrastructure.rag.rag_models import RagModelManager
from backend.video_summary.library.models import WorkspaceDTO
from backend.video_summary.library.usecases import (
    CreateAgentLinkedSeries,
    CreateVideoNote,
    DeleteSeries,
    DeleteVideoNote,
    DeleteVideoSource,
    ExportSeriesArchive,
    GenerateSeriesMindmapFromLibrary,
    GenerateSeriesSummaryFromLibrary,
    GenerateVideoAiSummary,
    GenerateVideoKnowledgeCards,
    GenerateVideoMindmapFromLibrary,
    GenerateVideoSummaryFromLibrary,
    GetSeriesMindmap,
    GetVideoAiSummary,
    GetVideoChapterCards,
    GetVideoKnowledgeCards,
    GetVideoMindmap,
    GetVideoNotes,
    GetVideoSource,
    GetVideoSummary,
    GetVideoTranscript,
    GetVideoWorkspaceTools,
    ImportLocalPlaygroundVideos,
    ImportLocalSeries,
    ImportLocalSeriesVideos,
    ListVideoLibrary,
    RenameSeries,
    RenameVideo,
    ResolveBilibiliSeries,
    ResolveBilibiliVideo,
    ResolveLinkedSeries,
    ResolveLinkedVideo,
    UpdateVideoAiSummary,
    UpdateVideoNote,
    UpdateVideoSummary,
    UpdateVideoTranscript,
)


@dataclass(frozen=True)
class WorkspaceServices:
    """Workspace-bound services only. Shared host infrastructure stays outside."""

    workspace_id: str
    check_health: Callable[[], WorkspaceDTO]
    job_summary_generator: SqlBackedVideoSummaryGenerator
    job_operation_handlers: Mapping[str, Callable[[ClaimedJob, SqlJobProgressReporter], Awaitable[None]]]
    list_video_library: ListVideoLibrary
    get_video_source: GetVideoSource
    get_video_summary: GetVideoSummary
    get_video_transcript: GetVideoTranscript
    get_video_mindmap: GetVideoMindmap
    get_video_chapter_cards: GetVideoChapterCards
    get_video_cards: GetVideoKnowledgeCards
    generate_video_cards: GenerateVideoKnowledgeCards
    generate_video_ai_summary: GenerateVideoAiSummary
    get_video_ai_summary: GetVideoAiSummary
    get_video_notes: GetVideoNotes
    create_video_note: CreateVideoNote
    update_video_note: UpdateVideoNote
    update_video_ai_summary: UpdateVideoAiSummary
    update_video_summary: UpdateVideoSummary
    update_video_transcript: UpdateVideoTranscript
    delete_video_note: DeleteVideoNote
    get_video_workspace_tools: GetVideoWorkspaceTools
    generate_video_summary: GenerateVideoSummaryFromLibrary
    generate_series_summaries: GenerateSeriesSummaryFromLibrary
    generate_video_mindmap: GenerateVideoMindmapFromLibrary
    generate_series_mindmap: GenerateSeriesMindmapFromLibrary
    get_series_mindmap: GetSeriesMindmap
    delete_series: DeleteSeries
    delete_video_source: DeleteVideoSource
    rename_series: RenameSeries
    rename_video: RenameVideo
    export_series_archive: ExportSeriesArchive
    import_local_series: ImportLocalSeries
    import_local_playground_videos: ImportLocalPlaygroundVideos
    import_local_series_videos: ImportLocalSeriesVideos
    create_agent_series: CreateAgentLinkedSeries
    resolve_bilibili_series: ResolveBilibiliSeries
    resolve_bilibili_video: ResolveBilibiliVideo
    resolve_linked_series: ResolveLinkedSeries
    resolve_linked_video: ResolveLinkedVideo
    bilibili_cookie_initializer: DrissionBilibiliCookieInitializer
    external_cookie_initializers: dict[str, DrissionCookieInitializer]
    generation_progress_tracker: InMemoryProgressTracker
    mindmap_progress_tracker: InMemoryProgressTracker
    video_download_progress_tracker: InMemoryProgressTracker
    knowledge_memory_progress_tracker: InMemoryProgressTracker
    rag_model_manager: RagModelManager
    linked_series_workspace: SqlVideoWorkspace
    workspace_index_invalidator: _WorkspaceIndexInvalidator
    get_agent_graph_service: Callable[[], AgentGraphService]
    get_agent_context_usage: Callable[[], AgentContextBudgetService]
    agent_session_store: SqlAgentSessionStore
    invalidate_agent_graph_service: Callable[[], None]
    invalidate_agent_workspace_indexes: Callable[[], None]
    refresh_agent_workspace_indexes: Callable[[], None]
    debug_mode: bool
