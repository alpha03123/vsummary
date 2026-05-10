from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from threading import Thread
from typing import Callable
import logging

import dspy

from backend.agent import AgentContextBudgetService, FileAgentSessionStore
from backend.agent.memory.messages import MemoryMessageCompactor
from backend.agent.infrastructure import LiteLLMChatGateway
from backend.agent.schemas.tool_calls import ToolName
from backend.agent_graph.actions.video_action_planner import VideoActionPlanner
from backend.agent_graph.runtime.graph import build_agent_graph
from backend.agent_graph.query.series_answer_synthesizer import SeriesAnswerSynthesizer
from backend.agent_graph.query.series_query_processor import SeriesQueryProcessor
from backend.agent_graph.dspy.dspy_lm import ProxyStreamingLM
from backend.agent_graph.dspy.programs import (
    AnswerSynthesisProgram,
)
from backend.agent_graph.runtime.service import AgentGraphService
from backend.shared.llm.base_url import resolve_openai_compatible_api_base_url
from backend.shared.settings import SettingsService, SettingsServicePort
from backend.video_summary.infrastructure.agent_memory import (
    AgentWorkspaceIndexBuilder,
    BGEReranker,
    SeriesRetrievalService,
)
from backend.video_summary.agent import RegistryAgentToolExecutor, WorkspaceAgentContextLoader
from backend.video_summary.agent.tools.notes import execute_open_notes, execute_save_note
from backend.video_summary.agent.tools.video import execute_video_seek
from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.infrastructure.faster_whisper_models import FasterWhisperModelManager
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.library_generation_adapters import (
    WorkspaceBackedVideoMindmapGenerator,
    WorkspaceBackedVideoSummaryGenerator,
)
from backend.video_summary.infrastructure.litellm_web_search import LiteLLMNativeWebSearchGateway
from backend.video_summary.infrastructure.litellm_knowledge_card_generator import ConfiguredKnowledgeCardGenerator
from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.rag_models import RAG_EMBEDDING_REQUIRED_MESSAGE, RagModelManager
from backend.video_summary.infrastructure.settings import load_env_settings, normalize_openai_base_url
from backend.video_summary.infrastructure.settings import load_settings
from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.library.ports import KnowledgeCardGenerator, VideoMindmapGenerator, VideoSummaryGenerator
from backend.video_summary.library.usecases import (
    DeleteSeries,
    DeleteVideoSource,
    GenerateVideoKnowledgeCards,
    RefreshSeriesKnowledgeMemory,
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
    generation_progress_tracker: InMemoryProgressTracker
    model_download_progress_tracker: InMemoryProgressTracker
    knowledge_memory_progress_tracker: InMemoryProgressTracker
    rag_model_manager: RagModelManager
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
    model_download_progress_tracker = InMemoryProgressTracker()
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
        delete_series=DeleteSeries(workspace, index_refresher, generation_activity_checker=series_generation_use_case),
        delete_video_source=DeleteVideoSource(workspace, index_refresher, generation_activity_checker=series_generation_use_case),
        import_local_series=ImportLocalSeries(workspace),
        import_local_playground_videos=ImportLocalPlaygroundVideos(workspace),
        import_local_series_videos=ImportLocalSeriesVideos(workspace),
        generation_progress_tracker=progress_tracker,
        model_download_progress_tracker=model_download_progress_tracker,
        knowledge_memory_progress_tracker=knowledge_memory_progress_tracker,
        rag_model_manager=rag_model_manager,
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


class _WorkspaceIndexInvalidator:
    def __init__(self, invalidate: Callable[[], None]) -> None:
        self._invalidate = invalidate

    def invalidate(self) -> None:
        self._invalidate()


class _WorkspaceIndexRefresher:
    def __init__(
        self,
        refresh_all: Callable[[], None],
        upsert_video: Callable[[str, str], None],
        delete_video: Callable[[str, str], None],
        delete_series: Callable[[str], None],
        *,
        progress_tracker: InMemoryProgressTracker,
        task_id: str = "agent-memory-refresh",
    ) -> None:
        self._refresh_all = refresh_all
        self._upsert_video = upsert_video
        self._delete_video = delete_video
        self._delete_series = delete_series
        self._progress_tracker = progress_tracker
        self._task_id = task_id
        self._lock = Lock()
        self._in_flight = False
        self._pending_full_rebuild = False
        self._pending_video_upserts: set[tuple[str, str]] = set()
        self._pending_video_deletes: set[tuple[str, str]] = set()
        self._pending_series_deletes: set[str] = set()

    def refresh(self) -> None:
        with self._lock:
            self._pending_full_rebuild = True
            self._pending_video_upserts.clear()
            self._pending_video_deletes.clear()
            self._pending_series_deletes.clear()
            should_start = self._mark_worker_in_flight_locked()
        if should_start:
            self._start_worker()

    def refresh_all(self) -> None:
        self.refresh()

    def upsert_video(self, series_id: str, video_id: str) -> None:
        with self._lock:
            if not self._pending_full_rebuild and series_id not in self._pending_series_deletes:
                self._pending_video_deletes.discard((series_id, video_id))
                self._pending_video_upserts.add((series_id, video_id))
            should_start = self._mark_worker_in_flight_locked()
        if should_start:
            self._start_worker()

    def delete_video(self, series_id: str, video_id: str) -> None:
        with self._lock:
            if not self._pending_full_rebuild and series_id not in self._pending_series_deletes:
                self._pending_video_upserts.discard((series_id, video_id))
                self._pending_video_deletes.add((series_id, video_id))
            should_start = self._mark_worker_in_flight_locked()
        if should_start:
            self._start_worker()

    def delete_series(self, series_id: str) -> None:
        with self._lock:
            if not self._pending_full_rebuild:
                self._pending_series_deletes.add(series_id)
                self._pending_video_upserts = {
                    item for item in self._pending_video_upserts if item[0] != series_id
                }
                self._pending_video_deletes = {
                    item for item in self._pending_video_deletes if item[0] != series_id
                }
            should_start = self._mark_worker_in_flight_locked()
        if should_start:
            self._start_worker()

    def _mark_worker_in_flight_locked(self) -> bool:
        if self._in_flight:
            return False
        self._in_flight = True
        return True

    def _start_worker(self) -> None:
        self._progress_tracker.create_reporter(self._task_id).update(
            "index",
            5.0,
            "数据库整理任务已进入后台队列",
        )
        Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        reporter = self._progress_tracker.create_reporter(self._task_id)
        while True:
            try:
                batch = self._drain_pending_batch()
                if batch is None:
                    with self._lock:
                        self._in_flight = False
                    return

                if batch["full_rebuild"]:
                    reporter.update("index", 20.0, "正在重建数据库索引")
                    self._refresh_all()
                else:
                    operations = batch["operations"]
                    total_operations = len(operations)
                    reporter.update("index", 0.0, f"正在更新数据库索引：0/{total_operations}")
                    for completed_count, operation in enumerate(operations, start=1):
                        self._apply_operation(operation)
                        reporter.update(
                            "index",
                            (completed_count / total_operations) * 100.0,
                            f"正在更新数据库索引：{completed_count}/{total_operations}",
                        )
            except Exception as error:
                LOGGER.exception("workspace index refresh failed")
                reporter.failed(str(error))
                with self._lock:
                    self._in_flight = False
                    self._pending_full_rebuild = False
                    self._pending_video_upserts.clear()
                    self._pending_video_deletes.clear()
                    self._pending_series_deletes.clear()
                return

            with self._lock:
                if self._has_pending_operations_locked():
                    continue
                self._in_flight = False
                break

        reporter.completed("数据库整理完成")

    def _drain_pending_batch(self) -> dict[str, object] | None:
        with self._lock:
            if self._pending_full_rebuild:
                self._pending_full_rebuild = False
                return {"full_rebuild": True, "operations": []}

            operations: list[tuple[str, str, str | None]] = []
            for series_id in sorted(self._pending_series_deletes):
                operations.append(("delete_series", series_id, None))
            for series_id, video_id in sorted(self._pending_video_deletes):
                if series_id not in self._pending_series_deletes:
                    operations.append(("delete_video", series_id, video_id))
            for series_id, video_id in sorted(self._pending_video_upserts):
                if series_id not in self._pending_series_deletes and (series_id, video_id) not in self._pending_video_deletes:
                    operations.append(("upsert_video", series_id, video_id))

            self._pending_series_deletes.clear()
            self._pending_video_deletes.clear()
            self._pending_video_upserts.clear()
            if not operations:
                return None
            return {"full_rebuild": False, "operations": operations}

    def _has_pending_operations_locked(self) -> bool:
        return bool(
            self._pending_full_rebuild
            or self._pending_video_upserts
            or self._pending_video_deletes
            or self._pending_series_deletes
        )

    def _apply_operation(self, operation: tuple[str, str, str | None]) -> None:
        kind, series_id, video_id = operation
        if kind == "upsert_video":
            self._upsert_video(series_id, str(video_id))
            return
        if kind == "delete_video":
            self._delete_video(series_id, str(video_id))
            return
        if kind == "delete_series":
            self._delete_series(series_id)
            return
        raise RuntimeError(f"unsupported workspace index operation '{kind}'")

class LazyAgentRuntimeProvider:
    def __init__(
        self,
        *,
        root_dir: Path,
        workspace: FileSystemVideoWorkspace,
        rag_model_manager: RagModelManager | None = None,
    ) -> None:
        self._root_dir = root_dir
        self._workspace = workspace
        self._rag_model_manager = rag_model_manager
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
                        api_base=resolve_openai_compatible_api_base_url(env_settings.base_url),
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
                planner_gateway = LiteLLMChatGateway(
                    provider=env_settings.provider,
                    model=env_settings.model,
                    base_url=normalize_openai_base_url(env_settings.base_url),
                    api_key=env_settings.api_key,
                )
                memory_compactor = MemoryMessageCompactor(
                    gateway=planner_gateway,
                    context_window_tokens=app_settings.agent_context.window_tokens,
                    compression_ratio=0.90,
                )
                series_query_processor = SeriesQueryProcessor(gateway=planner_gateway)
                series_answer_synthesizer = SeriesAnswerSynthesizer(gateway=planner_gateway)
                video_action_planner = VideoActionPlanner(gateway=planner_gateway)
                tool_executor = RegistryAgentToolExecutor(
                    registry={
                        ToolName.OPEN_NOTES: execute_open_notes,
                        ToolName.SAVE_NOTE: execute_save_note,
                        ToolName.VIDEO_SEEK: execute_video_seek,
                    }
                )
                retrieval_service = self._cached_retrieval_service
                if retrieval_service is None:
                    retrieval_service = self._build_lazy_retrieval_service()
                    self._cached_retrieval_service = retrieval_service
                web_search_gateway = self._build_web_search_gateway(
                    settings=app_settings,
                    env_settings=env_settings,
                )
                answer_program = AnswerSynthesisProgram()
                graph = build_agent_graph(
                    retrieval_service=retrieval_service,
                    answer_program=answer_program,
                    series_query_processor=series_query_processor,
                    series_answer_synthesizer=series_answer_synthesizer,
                    workspace=self._workspace,
                    video_action_planner=video_action_planner,
                    tool_executor=tool_executor,
                    context_window_tokens=app_settings.agent_context.window_tokens,
                    reserved_output_tokens=app_settings.agent_context.reserved_output_tokens,
                    web_search_gateway=web_search_gateway,
                    web_search_settings=app_settings.web_search,
                )
                self._cached_agent_graph_service = AgentGraphService(
                    context_loader=self._context_loader,
                    graph=graph,
                    session_store=self.session_store,
                    memory_compactor=memory_compactor,
                )
            return self._cached_agent_graph_service

    def invalidate_agent_graph_service(self) -> None:
        with self._lock:
            self._cached_agent_graph_service = None
            self._cached_context_budget_service = None

    def invalidate_workspace_indexes(self) -> None:
        with self._lock:
            if self._cached_retrieval_service is not None:
                self._cached_retrieval_service.invalidate()

    def refresh_workspace_indexes(self) -> None:
        AgentWorkspaceIndexBuilder(retrieval_service=self._get_or_create_retrieval_service()).refresh()

    def upsert_workspace_video(self, series_id: str, video_id: str) -> None:
        self._get_or_create_retrieval_service().upsert_video(series_id, video_id)

    def delete_workspace_video(self, series_id: str, video_id: str) -> None:
        self._get_or_create_retrieval_service().delete_video(series_id, video_id)

    def delete_workspace_series(self, series_id: str) -> None:
        self._get_or_create_retrieval_service().delete_series(series_id)

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

    def _get_or_create_retrieval_service(self) -> SeriesRetrievalService:
        with self._lock:
            retrieval_service = self._cached_retrieval_service
            if retrieval_service is None:
                retrieval_service = self._build_lazy_retrieval_service()
                self._cached_retrieval_service = retrieval_service
            return retrieval_service

    def _build_lazy_retrieval_service(self):
        if self._rag_model_manager is None:
            return self._build_series_retrieval_service()
        return _RagModelAwareRetrievalService(
            rag_model_manager=self._rag_model_manager,
            factory=self._build_series_retrieval_service,
            settings_loader=lambda: load_settings(self._root_dir / "config" / "settings.toml", self._root_dir),
        )

    def _build_series_retrieval_service(self) -> SeriesRetrievalService:
        return SeriesRetrievalService(
            workspace=self._workspace,
            db_uri=str(self._root_dir / "data" / "agent_graph" / "lancedb"),
            reranker=self._build_reranker(self._resolve_retrieval_device()),
            root_dir=self._root_dir,
        )

    def _resolve_retrieval_device(self) -> str:
        settings_path = self._root_dir / "config" / "settings.toml"
        if not settings_path.exists():
            return "cpu"
        return load_settings(settings_path, self._root_dir).agent_retrieval.embedding_device

    def _build_reranker(self, device: str) -> BGEReranker | None:
        if self._rag_model_manager is not None:
            if not self._rag_model_manager.is_downloaded("reranker"):
                return None
            return BGEReranker(
                model_name=str(self._rag_model_manager.local_model_dir("reranker")),
                device=device,
            )
        return BGEReranker(
            model_name=_resolve_local_reranker_model_name(self._root_dir),
            device=device,
        )

    def _build_web_search_gateway(self, *, settings, env_settings):
        web_search_settings = settings.web_search
        if not web_search_settings.enabled:
            return None
        if web_search_settings.provider == "litellm" and web_search_settings.mode == "native":
            return LiteLLMNativeWebSearchGateway(
                provider=env_settings.provider,
                model=env_settings.model,
                base_url=normalize_openai_base_url(env_settings.base_url),
                api_key=env_settings.api_key,
                search_context_size=web_search_settings.search_context_size,
            )
        raise RuntimeError(
            "Unsupported web_search provider/mode: "
            f"{web_search_settings.provider}/{web_search_settings.mode}"
        )


class _RagModelAwareRetrievalService:
    def __init__(
        self,
        *,
        rag_model_manager: RagModelManager,
        factory: Callable[[], SeriesRetrievalService],
        settings_loader: Callable[[], object],
    ) -> None:
        self._rag_model_manager = rag_model_manager
        self._factory = factory
        self._settings_loader = settings_loader
        self._service: SeriesRetrievalService | None = None
        self._signature: tuple[bool, bool, str] | None = None
        self._lock = Lock()

    def search(self, **kwargs):
        return self._require_service().search(**kwargs)

    def default_max_hits(self) -> int:
        return self._settings_loader().agent_retrieval.max_hits

    def refresh(self) -> None:
        self._require_service().refresh()

    def refresh_all(self) -> None:
        self._require_service().refresh_all()

    def upsert_video(self, series_id: str, video_id: str) -> None:
        self._require_service().upsert_video(series_id, video_id)

    def delete_video(self, series_id: str, video_id: str) -> None:
        self._require_service().delete_video(series_id, video_id)

    def delete_series(self, series_id: str) -> None:
        self._require_service().delete_series(series_id)

    def invalidate(self) -> None:
        with self._lock:
            if self._service is not None:
                self._service.invalidate()

    def _require_service(self) -> SeriesRetrievalService:
        with self._lock:
            if not self._rag_model_manager.is_downloaded("embedding"):
                raise RuntimeError(RAG_EMBEDDING_REQUIRED_MESSAGE)
            signature = self._build_signature()
            if self._service is None or self._signature != signature:
                self._service = self._factory()
                self._signature = signature
            return self._service

    def _build_signature(self) -> tuple[bool, bool, str]:
        settings = self._settings_loader()
        return (
            self._rag_model_manager.is_downloaded("embedding"),
            self._rag_model_manager.is_downloaded("reranker"),
            settings.agent_retrieval.embedding_device,
        )


def _resolve_local_reranker_model_name(root_dir: Path) -> str:
    local_dir = root_dir / "data" / "models" / "huggingface" / "bge-reranker-v2-m3"
    if local_dir.is_dir():
        return str(local_dir)
    return "BAAI/bge-reranker-v2-m3"
