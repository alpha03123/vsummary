from __future__ import annotations

from pathlib import Path
from threading import Lock

from backend.agent import AgentContextBudgetService, FileAgentSessionStore
from backend.agent.memory.messages import MemoryMessageCompactor
from backend.agent.infrastructure import LiteLLMChatGateway
from backend.agent.schemas.tool_calls import ToolName
from backend.agent_graph.actions.video_action_planner import VideoActionPlanner
from backend.agent_graph.runtime.graph import build_agent_graph
from backend.agent_graph.query.series_answer_synthesizer import SeriesAnswerSynthesizer
from backend.agent_graph.query.series_query_processor import SeriesQueryProcessor
from backend.agent_graph.query.video_answer_synthesizer import AnswerSynthesisProgram
from backend.agent_graph.runtime.service import AgentGraphService
from backend.api.adapters.rag_retrieval_proxy import _RagModelAwareRetrievalService
from backend.video_summary.agent_adapter import WorkspaceAgentContextLoader
from backend.video_summary.infrastructure.llm.litellm_web_search import LiteLLMNativeWebSearchGateway
from backend.video_summary.infrastructure.rag.agent_memory import AgentWorkspaceIndexBuilder, BGEReranker, SeriesRetrievalService
from backend.video_summary.infrastructure.rag.rag_models import RagModelManager
from backend.video_summary.infrastructure.config.settings import load_env_settings, load_settings, normalize_openai_base_url
from backend.video_summary.infrastructure.storage.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.tool_executor import RegistryAgentToolExecutor
from backend.video_summary.tools.notes import execute_open_notes, execute_save_note
from backend.video_summary.tools.video import execute_video_seek


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
                if env_settings.provider != "ollama" and not env_settings.api_key.strip():
                    raise RuntimeError("缺少 API Key，无法调用 Agent 模型。")
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
                    reasoning_effort=app_settings.agent_context.reasoning_effort,
                )
                memory_compactor = MemoryMessageCompactor(
                    gateway=planner_gateway,
                    context_window_tokens=app_settings.agent_context.window_tokens,
                    compression_ratio=0.90,
                )
                series_query_processor = SeriesQueryProcessor(gateway=planner_gateway)
                series_answer_synthesizer = SeriesAnswerSynthesizer(
                    gateway=planner_gateway,
                    answer_detail_level=app_settings.agent_context.answer_detail_level,
                    talk_custom_prompt=app_settings.agent_context.talk_custom_prompt,
                )
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
                answer_program = AnswerSynthesisProgram(
                    gateway=planner_gateway,
                    answer_detail_level=app_settings.agent_context.answer_detail_level,
                    talk_custom_prompt=app_settings.agent_context.talk_custom_prompt,
                )
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
                    answer_stream_gateway=planner_gateway,
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
                model_name="BAAI/bge-reranker-base",
                cache_dir=str(self._rag_model_manager.local_model_dir("reranker").parent),
                device=device,
            )
        return BGEReranker(device=device, cache_dir=_resolve_local_reranker_cache_dir(self._root_dir))

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


def _resolve_local_reranker_cache_dir(root_dir: Path) -> str | None:
    cache_dir = root_dir / "data" / "models" / "fastembed"
    local_dir = cache_dir / "models--BAAI--bge-reranker-base"
    if local_dir.is_dir():
        return str(cache_dir)
    return None