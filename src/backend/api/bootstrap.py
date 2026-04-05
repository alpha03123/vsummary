from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable

from backend.agent import AgentService, InMemoryAgentMemoryStore
from backend.agent.agent.execution import RegistryAgentToolExecutor
from backend.agent.infrastructure import OpenAICompatibleChatGateway, WorkspaceAgentContextLoader, WorkspaceTranscriptLookup
from backend.agent.schemas.tool_calls import ToolName
from backend.agent.tools.library_info import (
    create_get_video_summary_handler,
    create_get_video_tools_handler,
    create_list_series_videos_handler,
)
from backend.agent.tools.notes import execute_open_knowledge_cards, execute_open_notes, execute_save_note
from backend.agent.tools.mindmap import execute_generate_mindmap, execute_open_mindmap
from backend.agent.tools.overview import execute_generate_overview, execute_open_overview
from backend.agent.tools.series import execute_open_series_home
from backend.agent.tools.transcript import create_transcript_lookup_handler
from backend.agent.tools.video import execute_open_video, execute_video_seek
from backend.api.settings_service import ApiSettingsService
from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.infrastructure.faster_whisper_models import FasterWhisperModelManager
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.rule_based_knowledge_card_generator import RuleBasedKnowledgeCardGenerator
from backend.video_summary.infrastructure.settings import load_env_settings, normalize_openai_base_url
from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.library.ports import KnowledgeCardGenerator, VideoMindmapGenerator, VideoSummaryGenerator
from backend.video_summary.library.usecases import (
    GenerateVideoKnowledgeCards,
    GenerateVideoMindmapFromLibrary,
    GenerateVideoSummaryFromLibrary,
    GetVideoChapterCards,
    GetVideoKnowledgeCards,
    GetVideoMindmap,
    GetVideoNotes,
    GetVideoSource,
    GetVideoSummary,
    GetVideoWorkspaceTools,
    ListVideoLibrary,
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
    generate_video_mindmap: GenerateVideoMindmapFromLibrary
    generation_progress_tracker: InMemoryProgressTracker
    model_download_progress_tracker: InMemoryProgressTracker
    settings_service: ApiSettingsService
    get_agent_service: Callable[[], AgentService]


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
    resolved_generator = generator or ConfiguredVideoSummaryWorkflow(root_dir)
    resolved_mindmap_generator = mindmap_generator or ConfiguredMindmapWorkflow(root_dir)
    resolved_knowledge_card_generator = knowledge_card_generator or RuleBasedKnowledgeCardGenerator()
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
        generate_video_summary=GenerateVideoSummaryFromLibrary(workspace, resolved_generator, progress_tracker),
        generate_video_mindmap=GenerateVideoMindmapFromLibrary(workspace, resolved_mindmap_generator),
        generation_progress_tracker=progress_tracker,
        model_download_progress_tracker=model_download_progress_tracker,
        settings_service=ApiSettingsService(
            config_path=config_path,
            root_dir=root_dir,
            faster_whisper_model_manager=model_manager,
        ),
        get_agent_service=LazyAgentServiceProvider(root_dir=root_dir, workspace=workspace),
    )

class LazyAgentServiceProvider:
    def __init__(self, *, root_dir: Path, workspace: FileSystemVideoWorkspace) -> None:
        self._root_dir = root_dir
        self._workspace = workspace
        self._lock = Lock()
        self._cached_signature: str | None = None
        self._cached_service: AgentService | None = None

    def __call__(self) -> AgentService:
        signature = self._load_signature()
        with self._lock:
            if self._cached_service is None or self._cached_signature != signature:
                self._cached_service = _build_agent_service(self._root_dir, self._workspace)
                self._cached_signature = signature
            return self._cached_service

    def _load_signature(self) -> str:
        dotenv_path = self._root_dir / ".env"
        if not dotenv_path.exists():
            return ""
        return dotenv_path.read_text(encoding="utf-8")


def _build_agent_service(root_dir: Path, workspace: FileSystemVideoWorkspace) -> AgentService:
    transcript_lookup = WorkspaceTranscriptLookup(workspace)
    list_series_videos = create_list_series_videos_handler(workspace)
    get_video_summary = create_get_video_summary_handler(workspace)
    get_video_tools = create_get_video_tools_handler(workspace)
    env_settings = load_env_settings(root_dir)
    return AgentService(
        gateway=OpenAICompatibleChatGateway(
            model=env_settings.model,
            base_url=normalize_openai_base_url(env_settings.base_url),
            api_key=env_settings.api_key,
        ),
        context_loader=WorkspaceAgentContextLoader(workspace),
        memory_store=InMemoryAgentMemoryStore(),
        tool_executor=RegistryAgentToolExecutor(
            registry={
                ToolName.LIST_SERIES_VIDEOS: list_series_videos,
                ToolName.GET_VIDEO_SUMMARY: get_video_summary,
                ToolName.GET_VIDEO_TOOLS: get_video_tools,
                ToolName.OPEN_SERIES_HOME: execute_open_series_home,
                ToolName.OPEN_OVERVIEW: execute_open_overview,
                ToolName.OPEN_MINDMAP: execute_open_mindmap,
                ToolName.OPEN_KNOWLEDGE_CARDS: execute_open_knowledge_cards,
                ToolName.OPEN_NOTES: execute_open_notes,
                ToolName.OPEN_VIDEO: execute_open_video,
                ToolName.VIDEO_SEEK: execute_video_seek,
                ToolName.GENERATE_OVERVIEW: execute_generate_overview,
                ToolName.GENERATE_MINDMAP: execute_generate_mindmap,
                ToolName.SAVE_NOTE: execute_save_note,
                ToolName.TRANSCRIPT_LOOKUP: create_transcript_lookup_handler(transcript_lookup),
            }
        ),
    )
