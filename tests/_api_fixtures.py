"""Production API containers and interface-constrained collaborators for tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import create_autospec

from backend.api.di import bootstrap as host_types
from backend.api.di import workspace_services as scope_types
from backend.core.capabilities import CapabilitySet
from backend.core.quota import UnlimitedQuotaGuard, NoopUsageMeter
from backend.local.composition import LocalWorkspaceContextProvider, LocalWorkspaceServicesProvider


def mock_service(service_type, **method_results):
    service = create_autospec(service_type, instance=True, spec_set=True)
    for name, result in method_results.items():
        getattr(service, name).return_value = result
    return service


def make_workspace_services(*, workspace_id="workspace-1", **overrides) -> scope_types.WorkspaceServices:
    services = scope_types.WorkspaceServices(
        workspace_id=workspace_id,
        check_health=lambda: scope_types.WorkspaceDTO(id=workspace_id, title="Test workspace"),
        job_summary_generator=mock_service(scope_types.SqlBackedVideoSummaryGenerator),
        job_operation_handlers={},
        list_video_library=mock_service(scope_types.ListVideoLibrary),
        get_video_source=mock_service(scope_types.GetVideoSource),
        get_video_summary=mock_service(scope_types.GetVideoSummary),
        get_video_transcript=mock_service(scope_types.GetVideoTranscript),
        get_video_mindmap=mock_service(scope_types.GetVideoMindmap),
        get_video_chapter_cards=mock_service(scope_types.GetVideoChapterCards),
        get_video_cards=mock_service(scope_types.GetVideoKnowledgeCards),
        generate_video_cards=mock_service(scope_types.GenerateVideoKnowledgeCards),
        generate_video_ai_summary=mock_service(scope_types.GenerateVideoAiSummary),
        get_video_ai_summary=mock_service(scope_types.GetVideoAiSummary),
        get_video_notes=mock_service(scope_types.GetVideoNotes),
        create_video_note=mock_service(scope_types.CreateVideoNote),
        update_video_note=mock_service(scope_types.UpdateVideoNote),
        update_video_ai_summary=mock_service(scope_types.UpdateVideoAiSummary),
        update_video_summary=mock_service(scope_types.UpdateVideoSummary),
        update_video_transcript=mock_service(scope_types.UpdateVideoTranscript),
        delete_video_note=mock_service(scope_types.DeleteVideoNote),
        get_video_workspace_tools=mock_service(scope_types.GetVideoWorkspaceTools),
        generate_video_summary=mock_service(scope_types.GenerateVideoSummaryFromLibrary),
        generate_series_summaries=mock_service(scope_types.GenerateSeriesSummaryFromLibrary),
        generate_video_mindmap=mock_service(scope_types.GenerateVideoMindmapFromLibrary),
        generate_series_mindmap=mock_service(scope_types.GenerateSeriesMindmapFromLibrary),
        get_series_mindmap=mock_service(scope_types.GetSeriesMindmap),
        delete_series=mock_service(scope_types.DeleteSeries),
        delete_video_source=mock_service(scope_types.DeleteVideoSource),
        rename_series=mock_service(scope_types.RenameSeries),
        rename_video=mock_service(scope_types.RenameVideo),
        export_series_archive=mock_service(scope_types.ExportSeriesArchive),
        import_local_series=mock_service(scope_types.ImportLocalSeries),
        import_local_playground_videos=mock_service(scope_types.ImportLocalPlaygroundVideos),
        import_local_series_videos=mock_service(scope_types.ImportLocalSeriesVideos),
        create_agent_series=mock_service(scope_types.CreateAgentLinkedSeries),
        resolve_bilibili_series=mock_service(scope_types.ResolveBilibiliSeries),
        resolve_bilibili_video=mock_service(scope_types.ResolveBilibiliVideo),
        resolve_linked_series=mock_service(scope_types.ResolveLinkedSeries),
        resolve_linked_video=mock_service(scope_types.ResolveLinkedVideo),
        bilibili_cookie_initializer=mock_service(scope_types.DrissionBilibiliCookieInitializer),
        external_cookie_initializers={},
        generation_progress_tracker=scope_types.InMemoryProgressTracker(),
        mindmap_progress_tracker=scope_types.InMemoryProgressTracker(),
        video_download_progress_tracker=scope_types.InMemoryProgressTracker(),
        knowledge_memory_progress_tracker=scope_types.InMemoryProgressTracker(),
        rag_model_manager=mock_service(scope_types.RagModelManager),
        linked_series_workspace=mock_service(scope_types.SqlVideoWorkspace),
        workspace_index_invalidator=mock_service(scope_types._WorkspaceIndexInvalidator),
        get_agent_graph_service=lambda: mock_service(scope_types.AgentGraphService),
        get_agent_context_usage=lambda: mock_service(scope_types.AgentContextBudgetService),
        agent_session_store=mock_service(scope_types.SqlAgentSessionStore),
        invalidate_agent_graph_service=create_autospec(lambda: None),
        invalidate_agent_workspace_indexes=create_autospec(lambda: None),
        refresh_agent_workspace_indexes=create_autospec(lambda: None),
        debug_mode=False,
    )
    return replace(services, **overrides)


def make_api_container(*, services=None, **overrides) -> host_types.ApiContainer:
    services = services if services is not None else make_workspace_services()
    provider = LocalWorkspaceServicesProvider(workspace_id=services.workspace_id)
    provider.install_services(services)
    container = host_types.ApiContainer(
        config_path=Path("config/settings.toml"),
        root_dir=None,
        context_provider=LocalWorkspaceContextProvider(workspace_id=services.workspace_id, actor_id="test-user"),
        workspace_services_provider=provider,
        quota_guard=UnlimitedQuotaGuard(),
        usage_meter=NoopUsageMeter(),
        capabilities=CapabilitySet(),
        job_repository=mock_service(host_types.SqlJobRepository),
        job_worker=mock_service(host_types.SqlJobWorker),
        outbox_worker=mock_service(host_types.SqlOutboxWorker),
        faster_whisper_model_manager=mock_service(host_types.FasterWhisperModelManager),
        whisper_cpp_model_manager=mock_service(host_types.WhisperCppModelManager),
        model_download_progress_tracker=host_types.InMemoryProgressTracker(),
        chaoxing_import_progress_tracker=host_types.InMemoryProgressTracker(),
        knowledge_memory_progress_tracker=host_types.InMemoryProgressTracker(),
        rag_model_manager=mock_service(host_types.RagModelManager),
        chaoxing_importer=mock_service(host_types.ChaoxingCourseImporter),
        settings_service=mock_service(host_types.SettingsServicePort),
        usage_store=mock_service(host_types.MySqlLlmUsageStore),
    )
    return replace(container, **overrides)


def get_test_services(container) -> scope_types.WorkspaceServices:
    context = container.context_provider.get_context(request_id="test-request")
    return container.workspace_services_provider.get_services(context)


def replace_test_services(container, **overrides) -> None:
    provider = container.workspace_services_provider
    provider.install_services(replace(get_test_services(container), **overrides))
