from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable
import logging

import dspy

from backend.agent import AgentContextBudgetService, FileAgentSessionStore
from backend.agent.memory.dialog_history import DialogHistoryCompactor
from backend.agent.agent.execution import RegistryAgentToolExecutor
from backend.agent.infrastructure import LiteLLMChatGateway, WorkspaceAgentContextLoader
from backend.agent_graph.actions.action_dispatcher import ActionDispatcher
from backend.agent_graph.runtime.graph import build_agent_graph
from backend.agent_graph.evidence.pinpoint import BGEReranker, VideoGraphPinpointService
from backend.agent_graph.query.series_aggregator import SeriesAggregator
from backend.agent_graph.query.series_planner import SeriesPlanner
from backend.agent_graph.evidence.video_workflow import VideoWorkflowExtractor
from backend.agent_graph.dspy.dspy_lm import ProxyStreamingLM
from backend.agent_graph.dspy.programs import (
    ActionAfterContentReplyProgram,
    AnswerSynthesisProgram,
    NoteSynthesisProgram,
)
from backend.agent_graph.dspy.program_loader import (
    load_or_create_classifier_program,
    load_or_create_split_compare_program,
)
from backend.agent_graph.evidence.retrieval import MetaStateReader, SeriesRetrievalService
from backend.agent_graph.runtime.service import AgentGraphService
from backend.agent.schemas.tool_calls import ToolName
from backend.agent.tools.library_info import (
    create_get_video_summary_handler,
    create_get_video_transcript_handler,
    create_get_video_tools_handler,
    create_list_series_videos_handler,
)
from backend.agent.tools.context_access import render_model_visible_actions_for_scope
from backend.agent.tools.notes import execute_open_knowledge_cards, execute_open_notes, execute_save_note
from backend.agent.tools.mindmap import execute_generate_mindmap, execute_open_mindmap
from backend.agent.tools.overview import execute_generate_overview, execute_open_overview
from backend.agent.tools.series import execute_open_series_home, execute_open_series_overview
from backend.agent.tools.video import execute_open_video, execute_video_seek
from backend.bilibili.download_starter import BackgroundBilibiliDownloadStarter
from backend.bilibili.bilibili_downloader import BilibiliDownloader
from backend.bilibili.bilibili_meta_service import BilibiliMetaService
from backend.shared.settings import SettingsService, SettingsServicePort
from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.infrastructure.faster_whisper_models import FasterWhisperModelManager
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.library_generation_adapters import (
    WorkspaceBackedVideoMindmapGenerator,
    WorkspaceBackedVideoSummaryGenerator,
)
from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.rule_based_knowledge_card_generator import RuleBasedKnowledgeCardGenerator
from backend.video_summary.infrastructure.settings import load_env_settings, normalize_openai_base_url
from backend.video_summary.infrastructure.settings import load_settings
from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.library.parsers import DefaultBilibiliUrlParser
from backend.video_summary.library.ports import KnowledgeCardGenerator, VideoMindmapGenerator, VideoSummaryGenerator
from backend.video_summary.library.usecases import (
    DeleteLinkedSeries,
    DeleteSeries,
    DeleteVideoSource,
    GenerateVideoKnowledgeCards,
    GenerateSeriesSummaryFromLibrary,
    GenerateVideoMindmapFromLibrary,
    GenerateVideoSummaryFromLibrary,
    GetVideoChapterCards,
    GetVideoKnowledgeCards,
    GetVideoMindmap,
    GetVideoNotes,
    GetVideoSource,
    GetVideoSummary,
    GetVideoWorkspaceTools,
    ImportLocalPlaygroundVideos,
    ImportLocalSeries,
    ImportLocalSeriesVideos,
    ListVideoLibrary,
    CreateVideoNote,
    DeleteVideoNote,
    ResolveBilibiliSeries,
    ResolveBilibiliVideo,
    StartLinkedVideoDownload,
    UpdateVideoNote,
)

LOGGER = logging.getLogger(__name__)


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
    delete_series: DeleteSeries
    delete_video_source: DeleteVideoSource
    import_local_series: ImportLocalSeries
    import_local_playground_videos: ImportLocalPlaygroundVideos
    import_local_series_videos: ImportLocalSeriesVideos
    resolve_bilibili_series: ResolveBilibiliSeries
    resolve_bilibili_video: ResolveBilibiliVideo
    start_linked_video_download: StartLinkedVideoDownload
    delete_linked_series: DeleteLinkedSeries
    generation_progress_tracker: InMemoryProgressTracker
    model_download_progress_tracker: InMemoryProgressTracker
    settings_service: SettingsServicePort
    get_agent_graph_service: Callable[[], AgentGraphService]
    get_agent_context_usage: Callable[[], AgentContextBudgetService]
    agent_session_store: FileAgentSessionStore
    video_download_progress_tracker: InMemoryProgressTracker
    invalidate_agent_workspace_indexes: Callable[[], None]


def build_api_container(
    root_dir: Path,
    generator: VideoSummaryGenerator | None = None,
    mindmap_generator: VideoMindmapGenerator | None = None,
    knowledge_card_generator: KnowledgeCardGenerator | None = None,
    faster_whisper_model_manager: FasterWhisperModelManager | None = None,
) -> ApiContainer:
    config_path = root_dir / "config" / "settings.toml"
    workspace = FileSystemVideoWorkspace(root_dir)
    progress_tracker = InMemoryProgressTracker()
    model_download_progress_tracker = InMemoryProgressTracker()
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
    resolved_knowledge_card_generator = knowledge_card_generator or RuleBasedKnowledgeCardGenerator()
    summary_generation_use_case = GenerateVideoSummaryFromLibrary(workspace, resolved_generator, progress_tracker)
    agent_runtime = LazyAgentRuntimeProvider(root_dir=root_dir, workspace=workspace)
    invalidator = _WorkspaceIndexInvalidator(agent_runtime.invalidate_workspace_indexes)
    bilibili_meta_service = BilibiliMetaService()
    bilibili_downloader = BilibiliDownloader()
    video_download_progress_tracker = InMemoryProgressTracker()
    bilibili_url_parser = DefaultBilibiliUrlParser()
    bilibili_download_starter = BackgroundBilibiliDownloadStarter(
        root_dir=root_dir,
        downloader=bilibili_downloader,
        progress_tracker=video_download_progress_tracker,
        logger=LOGGER,
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
        generate_video_cards=GenerateVideoKnowledgeCards(workspace, resolved_knowledge_card_generator),
        get_video_notes=GetVideoNotes(workspace),
        create_video_note=CreateVideoNote(workspace),
        update_video_note=UpdateVideoNote(workspace),
        delete_video_note=DeleteVideoNote(workspace),
        get_video_workspace_tools=GetVideoWorkspaceTools(workspace),
        generate_video_summary=summary_generation_use_case,
        generate_series_summaries=GenerateSeriesSummaryFromLibrary(workspace, summary_generation_use_case, progress_tracker),
        generate_video_mindmap=GenerateVideoMindmapFromLibrary(workspace, resolved_mindmap_generator),
        delete_series=DeleteSeries(workspace, invalidator),
        delete_video_source=DeleteVideoSource(workspace, invalidator),
        import_local_series=ImportLocalSeries(workspace, invalidator),
        import_local_playground_videos=ImportLocalPlaygroundVideos(workspace, invalidator),
        import_local_series_videos=ImportLocalSeriesVideos(workspace, invalidator),
        resolve_bilibili_series=ResolveBilibiliSeries(
            workspace=workspace,
            resolver=bilibili_meta_service,
            invalidator=invalidator,
            parser=bilibili_url_parser,
        ),
        resolve_bilibili_video=ResolveBilibiliVideo(
            workspace=workspace,
            resolver=bilibili_meta_service,
            invalidator=invalidator,
            parser=bilibili_url_parser,
        ),
        start_linked_video_download=StartLinkedVideoDownload(
            workspace=workspace,
            starter=bilibili_download_starter,
        ),
        delete_linked_series=DeleteLinkedSeries(workspace, invalidator),
        generation_progress_tracker=progress_tracker,
        model_download_progress_tracker=model_download_progress_tracker,
        settings_service=SettingsService(
            config_path=config_path,
            root_dir=root_dir,
            faster_whisper_model_manager=model_manager,
        ),
        get_agent_graph_service=agent_runtime.get_agent_graph_service,
        get_agent_context_usage=agent_runtime.get_context_budget_service,
        agent_session_store=agent_runtime.session_store,
        video_download_progress_tracker=video_download_progress_tracker,
        invalidate_agent_workspace_indexes=agent_runtime.invalidate_workspace_indexes,
    )


class _WorkspaceIndexInvalidator:
    def __init__(self, invalidate: Callable[[], None]) -> None:
        self._invalidate = invalidate

    def invalidate(self) -> None:
        self._invalidate()

class LazyAgentRuntimeProvider:
    def __init__(self, *, root_dir: Path, workspace: FileSystemVideoWorkspace) -> None:
        self._root_dir = root_dir
        self._workspace = workspace
        self._context_loader = WorkspaceAgentContextLoader(workspace)
        self.session_store = FileAgentSessionStore(root_dir / "data" / "agent_sessions")
        self._lock = Lock()
        self._cached_agent_graph_service: AgentGraphService | None = None
        self._cached_context_budget_service: AgentContextBudgetService | None = None
        self._cached_retrieval_service: SeriesRetrievalService | None = None

    def get_agent_graph_service(self) -> AgentGraphService:
        with self._lock:
            if self._cached_agent_graph_service is None:
                env_settings = load_env_settings(self._root_dir)
                if not env_settings.api_key.strip():
                    raise RuntimeError("缺少 API Key，无法调用 Agent 模型。")
                dspy.configure(
                    lm=ProxyStreamingLM(
                        model=f"openai/{env_settings.model.strip()}",
                        api_base=normalize_openai_base_url(env_settings.base_url),
                        api_key=env_settings.api_key.strip(),
                    )
                )
                app_settings = load_settings(self._root_dir / "config" / "settings.toml", self._root_dir)
                self._cached_context_budget_service = AgentContextBudgetService(
                    context_loader=self._context_loader,
                    session_store=self.session_store,
                    window_tokens=app_settings.agent_context.window_tokens,
                    reserved_output_tokens=app_settings.agent_context.reserved_output_tokens,
                    warning_threshold_ratio=app_settings.agent_context.warning_threshold_ratio,
                    compact_threshold_ratio=app_settings.agent_context.compact_threshold_ratio,
                    blocking_threshold_ratio=app_settings.agent_context.blocking_threshold_ratio,
                )
                list_series_videos = create_list_series_videos_handler(self._workspace)
                get_video_summary = create_get_video_summary_handler(self._workspace)
                get_video_tools = create_get_video_tools_handler(self._workspace)
                get_video_transcript = create_get_video_transcript_handler(self._workspace)
                classifier_program = load_or_create_classifier_program(
                    artifact_path=self._root_dir / "data" / "agent_graph" / "dspy" / "classifier" / "program.json",
                    available_actions_resolver=render_model_visible_actions_for_scope,
                )
                compare_split_program = load_or_create_split_compare_program(
                    artifact_path=self._root_dir / "data" / "agent_graph" / "dspy" / "split_compare" / "program.json",
                )
                planner_gateway = LiteLLMChatGateway(
                    provider=env_settings.provider,
                    model=env_settings.model,
                    base_url=normalize_openai_base_url(env_settings.base_url),
                    api_key=env_settings.api_key,
                )
                dialog_history_compactor = DialogHistoryCompactor(
                    gateway=planner_gateway,
                    context_window_tokens=app_settings.agent_context.window_tokens,
                    compression_ratio=0.90,
                )
                series_aggregator = SeriesAggregator(gateway=planner_gateway)
                series_planner = SeriesPlanner(workspace=self._workspace, gateway=planner_gateway)
                retrieval_service = SeriesRetrievalService(
                    workspace=self._workspace,
                    db_uri=str(self._root_dir / "data" / "agent_graph" / "lancedb"),
                    root_dir=self._root_dir,
                )
                self._cached_retrieval_service = retrieval_service
                pinpoint_service = VideoGraphPinpointService(
                    workspace=self._workspace,
                    semantic_scorer=BGEReranker(device=app_settings.agent_retrieval.embedding_device),
                )
                workflow_service = VideoWorkflowExtractor(
                    workspace=self._workspace,
                    semantic_scorer=BGEReranker(device=app_settings.agent_retrieval.embedding_device),
                )
                meta_state_reader = MetaStateReader(workspace=self._workspace)
                answer_program = AnswerSynthesisProgram()
                note_program = NoteSynthesisProgram()
                action_reply_program = ActionAfterContentReplyProgram()
                tool_executor = _build_tool_executor(
                    list_series_videos=list_series_videos,
                    get_video_summary=get_video_summary,
                    get_video_tools=get_video_tools,
                    get_video_transcript=get_video_transcript,
                )
                action_dispatcher = ActionDispatcher(tool_executor=tool_executor)
                graph = build_agent_graph(
                    classifier_program=classifier_program,
                    compare_split_program=compare_split_program,
                    series_planner=series_planner,
                    retrieval_service=retrieval_service,
                    pinpoint_service=pinpoint_service,
                    workflow_service=workflow_service,
                    meta_state_reader=meta_state_reader,
                    action_dispatcher=action_dispatcher,
                    answer_program=answer_program,
                    note_program=note_program,
                    action_reply_program=action_reply_program,
                    series_aggregator=series_aggregator,
                )
                self._cached_agent_graph_service = AgentGraphService(
                    context_loader=self._context_loader,
                    graph=graph,
                    session_store=self.session_store,
                    series_aggregator=series_aggregator,
                    dialog_history_compactor=dialog_history_compactor,
                )
            return self._cached_agent_graph_service

    def invalidate_workspace_indexes(self) -> None:
        with self._lock:
            if self._cached_retrieval_service is not None:
                self._cached_retrieval_service.invalidate()

    def get_context_budget_service(self) -> AgentContextBudgetService:
        with self._lock:
            if self._cached_context_budget_service is None:
                app_settings = load_settings(self._root_dir / "config" / "settings.toml", self._root_dir)
                self._cached_context_budget_service = AgentContextBudgetService(
                    context_loader=self._context_loader,
                    session_store=self.session_store,
                    window_tokens=app_settings.agent_context.window_tokens,
                    reserved_output_tokens=app_settings.agent_context.reserved_output_tokens,
                    warning_threshold_ratio=app_settings.agent_context.warning_threshold_ratio,
                    compact_threshold_ratio=app_settings.agent_context.compact_threshold_ratio,
                    blocking_threshold_ratio=app_settings.agent_context.blocking_threshold_ratio,
                )
            return self._cached_context_budget_service

def _build_tool_executor(
    *,
    list_series_videos,
    get_video_summary,
    get_video_tools,
    get_video_transcript,
) -> RegistryAgentToolExecutor:
    return RegistryAgentToolExecutor(
        registry={
            ToolName.LIST_SERIES_VIDEOS: list_series_videos,
            ToolName.GET_VIDEO_SUMMARY: get_video_summary,
            ToolName.GET_VIDEO_TOOLS: get_video_tools,
            ToolName.GET_VIDEO_TRANSCRIPT: get_video_transcript,
            ToolName.OPEN_SERIES_HOME: execute_open_series_home,
            ToolName.OPEN_SERIES_OVERVIEW: execute_open_series_overview,
            ToolName.OPEN_OVERVIEW: execute_open_overview,
            ToolName.OPEN_MINDMAP: execute_open_mindmap,
            ToolName.OPEN_KNOWLEDGE_CARDS: execute_open_knowledge_cards,
            ToolName.OPEN_NOTES: execute_open_notes,
            ToolName.OPEN_VIDEO: execute_open_video,
            ToolName.VIDEO_SEEK: execute_video_seek,
            ToolName.GENERATE_OVERVIEW: execute_generate_overview,
            ToolName.GENERATE_MINDMAP: execute_generate_mindmap,
            ToolName.SAVE_NOTE: execute_save_note,
        }
    )
