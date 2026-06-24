from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.agent import AgentContextBudgetService, FileAgentSessionStore
from backend.agent_graph.runtime.service import AgentGraphService
from backend.api.adapters.agent_runtime_provider import LazyAgentRuntimeProvider
from backend.api.workers.workspace_index_worker import _WorkspaceIndexInvalidator, _WorkspaceIndexRefresher
from backend.bilibili import (
    BackgroundBilibiliDownloadStarter,
    BilibiliDownloader,
    BilibiliLinkedVideoDownloadStarter,
    CompositeLinkedVideoDownloadStarter,
    DrissionBilibiliCookieInitializer,
    YtDlpBilibiliResolver,
)
from backend.chaoxing import ChaoxingCourseImporter, ChaoxingDownloaderClient, ChaoxingLinkedVideoDownloadStarter
from backend.video_summary.infrastructure.storage.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.infrastructure.asr.faster_whisper_models import FasterWhisperModelManager
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.storage.library_generation_adapters import (
    WorkspaceBackedSeriesMindmapGenerator,
    WorkspaceBackedVideoMindmapGenerator,
    WorkspaceBackedVideoSummaryGenerator,
)
from backend.video_summary.infrastructure.series_mindmap_workflow import ConfiguredSeriesMindmapWorkflow
from backend.video_summary.infrastructure.llm.litellm_knowledge_card_generator import ConfiguredKnowledgeCardGenerator
from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.rag.rag_models import RagModelManager
from backend.video_summary.infrastructure.config.settings_service import SettingsService, SettingsServicePort
from backend.video_summary.infrastructure.config.settings import load_settings
from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.library.ports import KnowledgeCardGenerator, VideoMindmapGenerator, VideoSummaryGenerator
from backend.video_summary.library.usecases import (
    DeleteSeries,
    DeleteVideoSource,
    GenerateVideoKnowledgeCards,
    RefreshSeriesKnowledgeMemory,
    GenerateSeriesMindmapFromLibrary,
    GenerateSeriesSummaryFromLibrary,
    GenerateVideoMindmapFromLibrary,
    GenerateVideoSummaryFromLibrary,
    GetVideoChapterCards,
    GetVideoKnowledgeCards,
    GetSeriesMindmap,
    GetVideoMindmap,
    GetVideoNotes,
    GetVideoSource,
    GetVideoSummary,
    GetVideoWorkspaceTools,
    ImportLocalPlaygroundVideos,
    ImportLocalSeries,
    ImportLocalSeriesVideos,
    ListVideoLibrary,
    ResolveBilibiliSeries,
    ResolveBilibiliVideo,
    StartLinkedVideoDownload,
    CreateVideoNote,
    DeleteVideoNote,
    UpdateVideoNote,
)


@dataclass(frozen=True)
class ApiContainer:
    config_path: Path
    root_dir: Path
    faster_whisper_model_manager: FasterWhisperModelManager
    list_video_library: ListVideoLibrary
    get_video_source: GetVideoSource
    get_video_summary: GetVideoSummary
    get_video_mindmap: GetVideoMindmap
    get_video_chapter_cards: GetVideoChapterCards
    get_video_cards: GetVideoKnowledgeCards
    generate_video_cards: GenerateVideoKnowledgeCards
    get_video_notes: GetVideoNotes
    create_video_note: CreateVideoNote
    update_video_note: UpdateVideoNote
    delete_video_note: DeleteVideoNote
    get_video_workspace_tools: GetVideoWorkspaceTools
    generate_video_summary: GenerateVideoSummaryFromLibrary
    generate_series_summaries: GenerateSeriesSummaryFromLibrary
    generate_video_mindmap: GenerateVideoMindmapFromLibrary
    generate_series_mindmap: GenerateSeriesMindmapFromLibrary
    get_series_mindmap: GetSeriesMindmap
    delete_series: DeleteSeries
    delete_video_source: DeleteVideoSource
    import_local_series: ImportLocalSeries
    import_local_playground_videos: ImportLocalPlaygroundVideos
    import_local_series_videos: ImportLocalSeriesVideos
    resolve_bilibili_series: ResolveBilibiliSeries
    resolve_bilibili_video: ResolveBilibiliVideo
    bilibili_cookie_initializer: DrissionBilibiliCookieInitializer
    start_linked_video_download: StartLinkedVideoDownload
    generation_progress_tracker: InMemoryProgressTracker
    mindmap_progress_tracker: InMemoryProgressTracker
    video_download_progress_tracker: InMemoryProgressTracker
    model_download_progress_tracker: InMemoryProgressTracker
    chaoxing_import_progress_tracker: InMemoryProgressTracker
    knowledge_memory_progress_tracker: InMemoryProgressTracker
    rag_model_manager: RagModelManager
    chaoxing_importer: ChaoxingCourseImporter
    linked_series_workspace: FileSystemVideoWorkspace
    workspace_index_invalidator: object
    settings_service: SettingsServicePort
    get_agent_graph_service: Callable[[], AgentGraphService]
    get_agent_context_usage: Callable[[], AgentContextBudgetService]
    agent_session_store: FileAgentSessionStore
    invalidate_agent_graph_service: Callable[[], None]
    invalidate_agent_workspace_indexes: Callable[[], None]
    refresh_agent_workspace_indexes: Callable[[], None]


def build_api_container(
    root_dir: Path,
    generator: VideoSummaryGenerator | None = None,
    mindmap_generator: VideoMindmapGenerator | None = None,
    knowledge_card_generator: KnowledgeCardGenerator | None = None,
    faster_whisper_model_manager: FasterWhisperModelManager | None = None,
) -> ApiContainer:
    config_path = root_dir / "config" / "settings.toml"
    settings = load_settings(config_path, root_dir)
    workspace = FileSystemVideoWorkspace(root_dir)
    progress_tracker = InMemoryProgressTracker()
    mindmap_progress_tracker = InMemoryProgressTracker()
    video_download_progress_tracker = InMemoryProgressTracker()
    model_download_progress_tracker = InMemoryProgressTracker()
    chaoxing_import_progress_tracker = InMemoryProgressTracker()
    knowledge_memory_progress_tracker = InMemoryProgressTracker()
    rag_model_progress_tracker = InMemoryProgressTracker()
    index_refresher_ref: dict[str, _WorkspaceIndexRefresher | None] = {"value": None}

    def on_rag_model_download_completed(model_key: str) -> None:
        if model_key != "embedding":
            return
        index_refresher = index_refresher_ref["value"]
        if index_refresher is not None:
            index_refresher.refresh_all()

    rag_model_manager = RagModelManager(
        root_dir=root_dir,
        progress_tracker=rag_model_progress_tracker,
        on_download_completed=on_rag_model_download_completed,
    )
    model_manager = faster_whisper_model_manager or FasterWhisperModelManager(
        root_dir / "data" / "models" / "faster-whisper"
    )
    resolved_generator = generator or WorkspaceBackedVideoSummaryGenerator(
        workspace=workspace,
        workflow=ConfiguredVideoSummaryWorkflow(root_dir),
    )
    resolved_mindmap_generator = mindmap_generator or WorkspaceBackedVideoMindmapGenerator(
        workspace=workspace,
        workflow=ConfiguredMindmapWorkflow(root_dir),
    )
    resolved_knowledge_card_generator = knowledge_card_generator or ConfiguredKnowledgeCardGenerator(root_dir)
    resolved_series_mindmap_generator = WorkspaceBackedSeriesMindmapGenerator(
        workspace=workspace,
        workflow=ConfiguredSeriesMindmapWorkflow(root_dir),
    )
    agent_runtime = LazyAgentRuntimeProvider(
        root_dir=root_dir,
        workspace=workspace,
        rag_model_manager=rag_model_manager,
    )
    index_refresher = _WorkspaceIndexRefresher(
        refresh_all=agent_runtime.refresh_workspace_indexes,
        upsert_video=agent_runtime.upsert_workspace_video,
        delete_video=agent_runtime.delete_workspace_video,
        delete_series=agent_runtime.delete_workspace_series,
        progress_tracker=knowledge_memory_progress_tracker,
    )
    workspace_index_invalidator = _WorkspaceIndexInvalidator(agent_runtime.invalidate_workspace_indexes)
    index_refresher_ref["value"] = index_refresher
    series_memory_refresher = RefreshSeriesKnowledgeMemory(
        workspace=workspace,
        index_refresher=index_refresher,
    )
    summary_generation_use_case = GenerateVideoSummaryFromLibrary(
        workspace,
        resolved_generator,
        progress_tracker,
        video_generation_concurrency=settings.generation.video_generation_concurrency,
        series_memory_refresher=series_memory_refresher,
    )
    series_generation_use_case = GenerateSeriesSummaryFromLibrary(
        workspace,
        summary_generation_use_case,
        progress_tracker,
    )
    bilibili_resolver = YtDlpBilibiliResolver()
    bilibili_cookie_initializer = DrissionBilibiliCookieInitializer(root_dir=root_dir)
    bilibili_download_starter = BackgroundBilibiliDownloadStarter(
        root_dir=root_dir,
        downloader=BilibiliDownloader(),
        progress_tracker=video_download_progress_tracker,
    )
    chaoxing_client = ChaoxingDownloaderClient(
        state_dir=root_dir / "data" / "chaoxing",
        request_delay_seconds=settings.external_import.chaoxing.request_delay_seconds,
        init_course_delay_seconds=settings.external_import.chaoxing.init_course_delay_seconds,
    )
    chaoxing_importer = ChaoxingCourseImporter(client=chaoxing_client)
    linked_download_starter = CompositeLinkedVideoDownloadStarter(
        {
            "bilibili": BilibiliLinkedVideoDownloadStarter(bilibili_download_starter),
            "chaoxing": ChaoxingLinkedVideoDownloadStarter(
                root_dir=root_dir,
                client=chaoxing_client,
                progress_tracker=video_download_progress_tracker,
            ),
        }
    )
    return ApiContainer(
        config_path=config_path,
        root_dir=root_dir,
        faster_whisper_model_manager=model_manager,
        list_video_library=ListVideoLibrary(workspace),
        get_video_source=GetVideoSource(workspace),
        get_video_summary=GetVideoSummary(workspace),
        get_video_mindmap=GetVideoMindmap(workspace),
        get_video_chapter_cards=GetVideoChapterCards(workspace),
        get_video_cards=GetVideoKnowledgeCards(workspace),
        generate_video_cards=GenerateVideoKnowledgeCards(workspace, resolved_knowledge_card_generator, index_refresher),
        get_video_notes=GetVideoNotes(workspace),
        create_video_note=CreateVideoNote(workspace, index_refresher),
        update_video_note=UpdateVideoNote(workspace, index_refresher),
        delete_video_note=DeleteVideoNote(workspace, index_refresher),
        get_video_workspace_tools=GetVideoWorkspaceTools(workspace),
        generate_video_summary=summary_generation_use_case,
        generate_series_summaries=series_generation_use_case,
        generate_video_mindmap=GenerateVideoMindmapFromLibrary(workspace, resolved_mindmap_generator),
        generate_series_mindmap=GenerateSeriesMindmapFromLibrary(workspace, resolved_series_mindmap_generator),
        get_series_mindmap=GetSeriesMindmap(workspace),
        delete_series=DeleteSeries(workspace, index_refresher, generation_activity_checker=series_generation_use_case),
        delete_video_source=DeleteVideoSource(workspace, index_refresher, generation_activity_checker=series_generation_use_case),
        import_local_series=ImportLocalSeries(workspace),
        import_local_playground_videos=ImportLocalPlaygroundVideos(workspace),
        import_local_series_videos=ImportLocalSeriesVideos(workspace),
        resolve_bilibili_series=ResolveBilibiliSeries(workspace, bilibili_resolver, workspace_index_invalidator),
        resolve_bilibili_video=ResolveBilibiliVideo(workspace, bilibili_resolver, workspace_index_invalidator),
        bilibili_cookie_initializer=bilibili_cookie_initializer,
        start_linked_video_download=StartLinkedVideoDownload(workspace, linked_download_starter),
        generation_progress_tracker=progress_tracker,
        mindmap_progress_tracker=mindmap_progress_tracker,
        video_download_progress_tracker=video_download_progress_tracker,
        model_download_progress_tracker=model_download_progress_tracker,
        chaoxing_import_progress_tracker=chaoxing_import_progress_tracker,
        knowledge_memory_progress_tracker=knowledge_memory_progress_tracker,
        rag_model_manager=rag_model_manager,
        chaoxing_importer=chaoxing_importer,
        linked_series_workspace=workspace,
        workspace_index_invalidator=workspace_index_invalidator,
        settings_service=SettingsService(
            config_path=config_path,
            root_dir=root_dir,
            faster_whisper_model_manager=model_manager,
            rag_model_manager=rag_model_manager,
        ),
        get_agent_graph_service=agent_runtime.get_agent_graph_service,
        get_agent_context_usage=agent_runtime.get_context_budget_service,
        agent_session_store=agent_runtime.session_store,
        invalidate_agent_graph_service=agent_runtime.invalidate_agent_graph_service,
        invalidate_agent_workspace_indexes=agent_runtime.invalidate_workspace_indexes,
        refresh_agent_workspace_indexes=agent_runtime.refresh_workspace_indexes,
    )
