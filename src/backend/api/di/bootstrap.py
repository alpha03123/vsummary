from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.core.context import WorkspaceContextProvider
from backend.core.capabilities import CapabilitySet
from backend.core.quota import QuotaGuard, UsageMeter
from backend.agent import AgentContextBudgetService
from backend.agent_graph.runtime.service import AgentGraphService
from backend.api.adapters.agent_runtime_provider import LazyAgentRuntimeProvider
from backend.api.adapters.linked_video_downloader import ProviderLinkedVideoDownloader
from backend.api.workers.workspace_index_worker import _WorkspaceIndexInvalidator
from backend.api.adapters.durable_workspace_index_refresher import DurableWorkspaceIndexRefresher, submit_workspace_index_refresh
from backend.bilibili import (
    BilibiliDownloader,
    DrissionBilibiliCookieInitializer,
    YtDlpBilibiliResolver,
)
from backend.chaoxing import ChaoxingCourseImporter, ChaoxingDownloaderClient
from backend.external import (
    DrissionCookieInitializer,
    YtDlpPlatform,
    YtDlpPlatformDownloader,
    YtDlpPlatformResolver,
)
from backend.video_summary.infrastructure.asr.faster_whisper_models import FasterWhisperModelManager
from backend.video_summary.infrastructure.asr.whisper_cpp_models import WhisperCppModelManager
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor
from backend.video_summary.infrastructure.visual_frame_pool import build_or_load_visual_frame_pool
from backend.video_summary.library.note_images import materialize_note_frames
from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace
from backend.video_summary.infrastructure.persistence.sql_generation_adapters import (
    SqlBackedSeriesMindmapGenerator,
    SqlBackedVideoMindmapGenerator,
    SqlBackedVideoSummaryGenerator,
)
from backend.video_summary.infrastructure.series_mindmap_workflow import ConfiguredSeriesMindmapWorkflow
from backend.video_summary.infrastructure.llm.litellm_knowledge_card_generator import ConfiguredKnowledgeCardGenerator
from backend.video_summary.infrastructure.llm.litellm_note_generator import ConfiguredNoteGenerator
from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.rag.rag_models import RagModelManager
from backend.video_summary.infrastructure.config.settings_service import SettingsService, SettingsServicePort
from backend.video_summary.infrastructure.config.settings import load_settings
from backend.shared.llm.usage import MySqlLlmUsageStore
from backend.video_summary.infrastructure.persistence.sql_agent_session_store import SqlAgentSessionStore
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository
from backend.video_summary.infrastructure.persistence.job_worker import SqlJobWorker, WorkerOptions
from backend.video_summary.infrastructure.persistence.outbox_repository import SqlOutboxRepository
from backend.video_summary.infrastructure.persistence.outbox_worker import SqlOutboxWorker
from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.library.ports import KnowledgeCardGenerator, VideoMindmapGenerator, VideoSummaryGenerator
from backend.video_summary.library.usecases import (
    CreateAgentLinkedSeries,
    DeleteSeries,
    DeleteVideoSource,
    RenameSeries,
    RenameVideo,
    ExportSeriesArchive,
    GenerateVideoKnowledgeCards,
    GenerateVideoAiSummary,
    AutoGenerateVideoArtifacts,
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
    GetVideoAiSummary,
    GetVideoTranscript,
    GetVideoWorkspaceTools,
    ImportLocalPlaygroundVideos,
    ImportLocalSeries,
    ImportLocalSeriesVideos,
    ListVideoLibrary,
    ResolveBilibiliSeries,
    ResolveBilibiliVideo,
    DownloadLinkedVideo,
    ResolveLinkedSeries,
    ResolveLinkedVideo,
    CreateVideoNote,
    DeleteVideoNote,
    UpdateVideoNote,
    UpdateVideoSummary,
    UpdateVideoTranscript,
    UpdateVideoAiSummary,
)


@dataclass(frozen=True)
class ApiContainer:
    config_path: Path
    root_dir: Path
    sql_workspace: SqlVideoWorkspace
    context_provider: WorkspaceContextProvider
    quota_guard: QuotaGuard
    usage_meter: UsageMeter
    capabilities: CapabilitySet
    job_repository: SqlJobRepository
    job_worker: SqlJobWorker
    outbox_worker: SqlOutboxWorker
    faster_whisper_model_manager: FasterWhisperModelManager
    whisper_cpp_model_manager: WhisperCppModelManager
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
    model_download_progress_tracker: InMemoryProgressTracker
    chaoxing_import_progress_tracker: InMemoryProgressTracker
    knowledge_memory_progress_tracker: InMemoryProgressTracker
    rag_model_manager: RagModelManager
    chaoxing_importer: ChaoxingCourseImporter
    linked_series_workspace: object
    workspace_index_invalidator: object
    settings_service: SettingsServicePort
    usage_store: MySqlLlmUsageStore
    get_agent_graph_service: Callable[[], AgentGraphService]
    get_agent_context_usage: Callable[[], AgentContextBudgetService]
    agent_session_store: object
    invalidate_agent_graph_service: Callable[[], None]
    invalidate_agent_workspace_indexes: Callable[[], None]
    refresh_agent_workspace_indexes: Callable[[], None]


def build_api_container(
    root_dir: Path,
    generator: VideoSummaryGenerator | None = None,
    mindmap_generator: VideoMindmapGenerator | None = None,
    knowledge_card_generator: KnowledgeCardGenerator | None = None,
    faster_whisper_model_manager: FasterWhisperModelManager | None = None,
    whisper_cpp_model_manager: WhisperCppModelManager | None = None,
    workspace_override: object | None = None,
    context_provider: WorkspaceContextProvider | None = None,
    quota_guard: QuotaGuard | None = None,
    usage_meter: UsageMeter | None = None,
    capabilities: CapabilitySet | None = None,
) -> ApiContainer:
    config_path = root_dir / "config" / "settings.toml"
    settings = load_settings(config_path, root_dir)
    if workspace_override is None:
        raise RuntimeError("build_api_container requires an explicit SQL workspace.")
    workspace = workspace_override
    progress_tracker = InMemoryProgressTracker()
    mindmap_progress_tracker = InMemoryProgressTracker()
    video_download_progress_tracker = InMemoryProgressTracker()
    model_download_progress_tracker = InMemoryProgressTracker()
    chaoxing_import_progress_tracker = InMemoryProgressTracker()
    knowledge_memory_progress_tracker = InMemoryProgressTracker()
    rag_model_progress_tracker = InMemoryProgressTracker()
    if not isinstance(workspace, SqlVideoWorkspace):
        raise RuntimeError("build_api_container requires SqlVideoWorkspace.")
    if context_provider is None or quota_guard is None or usage_meter is None or capabilities is None:
        raise RuntimeError("build_api_container requires explicit context, quota, usage, and capability adapters.")
    usage_store = MySqlLlmUsageStore(workspace.session_factory)
    agent_session_store = SqlAgentSessionStore(workspace.session_factory, workspace_id=workspace.workspace_id)
    index_refresher_ref: dict[str, DurableWorkspaceIndexRefresher | None] = {"value": None}

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
    whisper_cpp_manager = whisper_cpp_model_manager or WhisperCppModelManager(
        root_dir / "data" / "models" / "whisper-cpp"
    )
    def queue_ai_summary_index_refresh(series_id: str, video_id: str) -> None:
        index_refresher = index_refresher_ref["value"]
        if index_refresher is None:
            raise RuntimeError("AI 概括索引刷新器尚未初始化。")
        index_refresher.upsert_video(series_id, video_id)

    resolved_generator = generator or SqlBackedVideoSummaryGenerator(
        workspace=workspace,
        workflow=ConfiguredVideoSummaryWorkflow(root_dir, usage_recorder=usage_store),
        temp_root=workspace.cache_root,
    )
    if not isinstance(resolved_generator, SqlBackedVideoSummaryGenerator):
        raise RuntimeError("SQL job execution requires SqlBackedVideoSummaryGenerator.")
    job_repository = SqlJobRepository(workspace.session_factory)
    resolved_mindmap_generator = mindmap_generator or SqlBackedVideoMindmapGenerator(
        workspace=workspace,
        workflow=ConfiguredMindmapWorkflow(root_dir, usage_recorder=usage_store),
        temp_root=workspace.cache_root,
    )
    resolved_series_mindmap_generator = SqlBackedSeriesMindmapGenerator(
        workspace=workspace,
        workflow=ConfiguredSeriesMindmapWorkflow(root_dir, usage_recorder=usage_store),
        temp_root=workspace.cache_root,
    )

    async def run_video_mindmap_job(claim, reporter) -> None:
        payload = claim.request_payload
        max_depth = payload.get("max_depth")
        if max_depth is not None and (isinstance(max_depth, bool) or not isinstance(max_depth, int)):
            raise ValueError("max_depth must be an integer or null.")
        mindmap = await GenerateVideoMindmapFromLibrary(
            workspace,
            resolved_mindmap_generator,
            visual_input=load_settings(config_path, root_dir).generation.mindmap_visual_input,
            max_visual_input_images=load_settings(config_path, root_dir).generation.max_visual_input_images,
            frame_pool_builder=build_or_load_visual_frame_pool,
        ).run(
            str(payload["series_id"]),
            claim.resource_id,
            progress_reporter=reporter,
            max_depth=max_depth,
        )
        if mindmap is None:
            raise LookupError("Summary does not exist; cannot generate a mindmap.")

    async def run_series_mindmap_job(claim, reporter) -> None:
        max_depth = claim.request_payload.get("max_depth")
        if max_depth is not None and (isinstance(max_depth, bool) or not isinstance(max_depth, int)):
            raise ValueError("max_depth must be an integer or null.")
        mindmap = await GenerateSeriesMindmapFromLibrary(
            workspace,
            resolved_series_mindmap_generator,
        ).run(
            claim.resource_id,
            progress_reporter=reporter,
            max_depth=max_depth,
        )
        if mindmap is None:
            raise LookupError("Series has no generated summaries; cannot generate a mindmap.")

    operation_handlers = {
        "generate_video_mindmap": run_video_mindmap_job,
        "generate_series_mindmap": run_series_mindmap_job,
    }
    job_worker = SqlJobWorker(
        repository=job_repository,
        summary_generator=resolved_generator,
        operation_handlers=operation_handlers,
        options=WorkerOptions.local(),
    )
    resolved_knowledge_card_generator = knowledge_card_generator or ConfiguredKnowledgeCardGenerator(
        root_dir,
        usage_recorder=usage_store,
    )
    resolved_note_generator = ConfiguredNoteGenerator(root_dir, usage_recorder=usage_store)
    agent_runtime = LazyAgentRuntimeProvider(
        root_dir=root_dir,
        workspace=workspace,
        session_store=agent_session_store,
        rag_model_manager=rag_model_manager,
        usage_recorder=usage_store,
    )
    index_refresher = DurableWorkspaceIndexRefresher(
        lambda: submit_workspace_index_refresh(
            repository=job_repository,
            workspace_id=workspace.workspace_id,
        ),
    )
    workspace_index_invalidator = _WorkspaceIndexInvalidator(agent_runtime.invalidate_workspace_indexes)
    index_refresher_ref["value"] = index_refresher

    def invalidate_workspace_indexes_from_outbox(_event) -> None:
        agent_runtime.invalidate_workspace_indexes()

    outbox_worker = SqlOutboxWorker(
        repository=SqlOutboxRepository(workspace.session_factory),
        handlers={
            "content_published": invalidate_workspace_indexes_from_outbox,
            "note_published": invalidate_workspace_indexes_from_outbox,
            "knowledge_cards_published": invalidate_workspace_indexes_from_outbox,
        },
    )
    series_memory_refresher = RefreshSeriesKnowledgeMemory(
        workspace=workspace,
        index_refresher=index_refresher,
    )

    async def run_video_knowledge_cards_job(claim, reporter) -> None:
        cards = await asyncio.to_thread(
            GenerateVideoKnowledgeCards(
                workspace,
                resolved_knowledge_card_generator,
                index_refresher,
                visual_input=load_settings(config_path, root_dir).generation.cards_visual_input,
                max_visual_input_images=load_settings(config_path, root_dir).generation.max_visual_input_images,
                frame_pool_builder=build_or_load_visual_frame_pool,
            ).run,
            str(claim.request_payload["series_id"]),
            claim.resource_id,
        )
        if cards is None:
            raise LookupError("Summary does not exist; cannot generate knowledge cards.")

    async def run_video_ai_summary_job(claim, reporter) -> None:
        template = claim.request_payload.get("template", "general")
        if not isinstance(template, str) or not template.strip():
            raise ValueError("template must be a non-empty string.")
        summary = await asyncio.to_thread(
            ai_summary_use_case.run,
            str(claim.request_payload["series_id"]),
            claim.resource_id,
            template=template,
        )
        if summary is None:
            raise LookupError("Video source does not exist; cannot generate an AI summary.")

    operation_handlers["generate_video_knowledge_cards"] = run_video_knowledge_cards_job
    operation_handlers["generate_video_ai_summary"] = run_video_ai_summary_job
    ai_summary_use_case = GenerateVideoAiSummary(
        workspace,
        resolved_note_generator,
        index_refresher,
        max_visual_input_images=settings.generation.max_visual_input_images,
        multimodal_enabled=settings.generation.ai_summary_multimodal_enabled,
        frame_pool_builder=build_or_load_visual_frame_pool,
        note_frame_materializer=lambda *, video_path, output_dir, content: materialize_note_frames(video_path=video_path, output_dir=output_dir, content=content, frame_extractor=FfmpegMediaProcessor()),
    )

    auto_artifacts = AutoGenerateVideoArtifacts(
        load_enabled_artifacts=lambda: load_settings(config_path, root_dir).generation.auto_generate_artifacts,
        generate_mindmap=lambda series_id, video_id: GenerateVideoMindmapFromLibrary(
            workspace,
            resolved_mindmap_generator,
            visual_input=load_settings(config_path, root_dir).generation.mindmap_visual_input,
            max_visual_input_images=load_settings(config_path, root_dir).generation.max_visual_input_images,
            frame_pool_builder=build_or_load_visual_frame_pool,
        ).run(series_id, video_id),
        generate_knowledge_cards=lambda series_id, video_id: GenerateVideoKnowledgeCards(
            workspace,
            resolved_knowledge_card_generator,
            index_refresher,
            visual_input=load_settings(config_path, root_dir).generation.cards_visual_input,
            max_visual_input_images=load_settings(config_path, root_dir).generation.max_visual_input_images,
            frame_pool_builder=build_or_load_visual_frame_pool,
        ).run(series_id, video_id),
    )
    summary_generation_use_case = GenerateVideoSummaryFromLibrary(
        workspace,
        resolved_generator,
        progress_tracker,
        video_generation_concurrency=settings.generation.video_generation_concurrency,
        series_memory_refresher=series_memory_refresher,
        auto_generate_artifacts=auto_artifacts.run,
    )
    series_generation_use_case = GenerateSeriesSummaryFromLibrary(
        workspace,
        summary_generation_use_case,
        progress_tracker,
    )
    bilibili_resolver = YtDlpBilibiliResolver()
    bilibili_cookie_initializer = DrissionBilibiliCookieInitializer(root_dir=root_dir)
    youtube_platform = YtDlpPlatform(
        provider="youtube",
        display_name="YouTube",
        cookie_domain="youtube.com",
        login_url="https://accounts.google.com/ServiceLogin?service=youtube",
        cookie_env="YOUTUBE_COOKIE",
        browser_port=9224,
        login_cookie_names=("SID", "SAPISID", "LOGIN_INFO"),
        format_selector="bv*+ba/best",
    )
    douyin_platform = YtDlpPlatform(
        provider="douyin",
        display_name="抖音",
        cookie_domain="douyin.com",
        login_url="https://www.douyin.com/",
        cookie_env="DOUYIN_COOKIE",
        browser_port=9225,
        login_cookie_names=("s_v_web_id", "sessionid", "sessionid_ss"),
        format_selector="bv*+ba/best",
    )
    external_platforms = (youtube_platform, douyin_platform)
    external_resolvers = {
        "bilibili": bilibili_resolver,
        **{platform.provider: YtDlpPlatformResolver(platform) for platform in external_platforms},
    }
    external_cookie_initializers = {
        platform.provider: DrissionCookieInitializer(root_dir=root_dir, platform=platform)
        for platform in external_platforms
    }
    chaoxing_client = ChaoxingDownloaderClient(
        state_dir=root_dir / "data" / "chaoxing",
        request_delay_seconds=settings.external_import.chaoxing.request_delay_seconds,
        init_course_delay_seconds=settings.external_import.chaoxing.init_course_delay_seconds,
    )
    chaoxing_importer = ChaoxingCourseImporter(client=chaoxing_client)
    durable_linked_downloader = ProviderLinkedVideoDownloader(
        download_root=root_dir / "data" / "downloads",
        bilibili_downloader=BilibiliDownloader(),
        platform_downloaders={platform.provider: YtDlpPlatformDownloader(platform) for platform in external_platforms},
        chaoxing_client=chaoxing_client,
    )

    async def run_linked_video_download_job(claim, reporter) -> None:
        payload = claim.request_payload
        await asyncio.to_thread(
            DownloadLinkedVideo(workspace, durable_linked_downloader).run,
            series_id=str(payload["series_id"]),
            video_id=claim.resource_id,
            reporter=reporter,
        )

    operation_handlers["download_linked_video"] = run_linked_video_download_job

    async def run_agent_video_job(claim, reporter) -> None:
        payload = claim.request_payload
        series_id = str(payload["series_id"])
        processing_mode = str(payload.get("processing_mode") or "summary")
        if processing_mode not in {"summary", "transcript"}:
            raise ValueError("processing_mode must be summary or transcript.")
        linked_video = workspace.get_linked_video_for_download(series_id, claim.resource_id)
        if linked_video is not None:
            reporter.update("download", 0.0, "正在下载外链视频")
            await asyncio.to_thread(
                DownloadLinkedVideo(workspace, durable_linked_downloader).run,
                series_id=series_id,
                video_id=claim.resource_id,
                reporter=reporter,
            )
        await resolved_generator.run(
            series_id=series_id,
            video_id=claim.resource_id,
            processing_mode=processing_mode,
            transcript_enhancement_enabled=payload.get("transcript_enhancement_enabled"),
            progress_reporter=reporter,
            job_id=claim.id,
            worker_id=claim.worker_id,
            lease_token=claim.lease_token,
        )

    operation_handlers["process_agent_video"] = run_agent_video_job

    async def run_series_batch_job(claim, reporter) -> None:
        payload = claim.request_payload
        series_id = claim.resource_id
        processing_mode = str(payload.get("processing_mode") or "summary")
        if processing_mode not in {"summary", "transcript"}:
            raise ValueError("processing_mode must be summary or transcript.")
        series = next((item for item in workspace.list_series() if item.id == series_id), None)
        if series is None:
            raise LookupError(f"series not found '{series_id}'")
        pending = [video for video in series.videos if not video.processed]
        reporter.update("queue", 0.0, f"正在创建 {len(pending)} 个视频子任务")
        for index, video in enumerate(pending, start=1):
            reporter.raise_if_cancelled()
            has_source = workspace.get_video_source(series_id, video.id) is not None
            child_operation = (
                "process_agent_video"
                if not has_source and (video.is_linked or video.status == "linked")
                else ("generate_summary" if processing_mode == "summary" else "generate_transcript")
            )
            if not has_source and child_operation != "process_agent_video":
                reporter.update("queue", index / max(1, len(pending)) * 100.0, f"跳过缺少媒体文件的视频：{video.title}")
                continue
            try:
                job_repository.submit(
                    workspace_id=claim.workspace_id,
                    resource_type="video",
                    resource_id=video.id,
                    operation=child_operation,
                    request_payload={
                        "series_id": series_id,
                        "video_id": video.id,
                        "processing_mode": processing_mode,
                        "transcript_enhancement_enabled": payload.get("transcript_enhancement_enabled"),
                        "use_saved_manual_transcript": True,
                        "parent_job_id": claim.id,
                    },
                    active_key=f"video:{video.id}:{child_operation}",
                    idempotency_scope_id=None,
                    idempotency_key=None,
                )
            except ControlPlaneConflictError:
                pass
            reporter.update("queue", index / max(1, len(pending)) * 100.0, f"已创建 {index}/{len(pending)} 个视频子任务")

    operation_handlers["generate_series_batch"] = run_series_batch_job

    async def run_chaoxing_course_import_job(claim, reporter) -> None:
        course_key = claim.request_payload.get("course_key")
        if not isinstance(course_key, str) or not course_key.strip():
            raise ValueError("course_key must be a non-empty string.")
        linked_series = await asyncio.to_thread(
            chaoxing_importer.import_course,
            course_key,
            progress=reporter,
        )
        reporter.raise_if_cancelled()
        reporter.update("save", 95.0, "正在保存导入结果")
        workspace.save_linked_series(linked_series)
        workspace_index_invalidator.invalidate()

    operation_handlers["import_chaoxing_course"] = run_chaoxing_course_import_job

    async def run_asr_model_prepare_job(claim, reporter) -> None:
        payload = claim.request_payload
        provider = payload.get("provider")
        model_id = payload.get("model_id")
        if not isinstance(provider, str) or not isinstance(model_id, str):
            raise ValueError("ASR model job requires provider and model_id.")
        manager = {"faster_whisper": model_manager, "whisper_cpp": whisper_cpp_manager}.get(provider)
        if manager is None or not manager.is_supported(model_id):
            raise ValueError(f"unsupported {provider} model '{model_id}'")
        await asyncio.to_thread(manager.download, model_id, progress_reporter=reporter)

    async def run_rag_model_prepare_job(claim, reporter) -> None:
        model_key = claim.request_payload.get("model_key")
        if not isinstance(model_key, str) or not model_key.strip():
            raise ValueError("RAG model job requires model_key.")
        await asyncio.to_thread(rag_model_manager.download, model_key, progress_reporter=reporter)

    operation_handlers["prepare_asr_model"] = run_asr_model_prepare_job
    operation_handlers["prepare_rag_model"] = run_rag_model_prepare_job

    async def run_rag_index_refresh_job(_claim, reporter) -> None:
        reporter.update("index", 10.0, "正在重建工作区 RAG 索引")
        await asyncio.to_thread(agent_runtime.refresh_workspace_indexes)
        reporter.update("index", 100.0, "工作区 RAG 索引已更新")

    operation_handlers["refresh_rag_index"] = run_rag_index_refresh_job
    return ApiContainer(
        config_path=config_path,
        root_dir=root_dir,
        sql_workspace=workspace,
        context_provider=context_provider,
        quota_guard=quota_guard,
        usage_meter=usage_meter,
        capabilities=capabilities,
        job_repository=job_repository,
        job_worker=job_worker,
        outbox_worker=outbox_worker,
        faster_whisper_model_manager=model_manager,
        whisper_cpp_model_manager=whisper_cpp_manager,
        list_video_library=ListVideoLibrary(workspace),
        get_video_source=GetVideoSource(workspace),
        get_video_summary=GetVideoSummary(workspace),
        get_video_transcript=GetVideoTranscript(workspace),
        get_video_mindmap=GetVideoMindmap(workspace),
        get_video_chapter_cards=GetVideoChapterCards(workspace),
        get_video_cards=GetVideoKnowledgeCards(workspace),
        generate_video_cards=GenerateVideoKnowledgeCards(
            workspace,
            resolved_knowledge_card_generator,
            index_refresher,
            visual_input=settings.generation.cards_visual_input,
            max_visual_input_images=settings.generation.max_visual_input_images,
            frame_pool_builder=build_or_load_visual_frame_pool,
        ),
        generate_video_ai_summary=ai_summary_use_case,
        get_video_ai_summary=GetVideoAiSummary(workspace),
        get_video_notes=GetVideoNotes(workspace),
        create_video_note=CreateVideoNote(workspace, index_refresher),
        update_video_note=UpdateVideoNote(workspace, index_refresher),
        update_video_ai_summary=UpdateVideoAiSummary(workspace, index_refresher),
        update_video_summary=UpdateVideoSummary(workspace, series_memory_refresher),
        update_video_transcript=UpdateVideoTranscript(workspace, index_refresher),
        delete_video_note=DeleteVideoNote(workspace, index_refresher),
        get_video_workspace_tools=GetVideoWorkspaceTools(workspace),
        generate_video_summary=summary_generation_use_case,
        generate_series_summaries=series_generation_use_case,
        generate_video_mindmap=GenerateVideoMindmapFromLibrary(
            workspace,
            resolved_mindmap_generator,
            visual_input=settings.generation.mindmap_visual_input,
            max_visual_input_images=settings.generation.max_visual_input_images,
            frame_pool_builder=build_or_load_visual_frame_pool,
        ),
        generate_series_mindmap=GenerateSeriesMindmapFromLibrary(workspace, resolved_series_mindmap_generator),
        get_series_mindmap=GetSeriesMindmap(workspace),
        delete_series=DeleteSeries(workspace, index_refresher, generation_activity_checker=series_generation_use_case),
        delete_video_source=DeleteVideoSource(workspace, index_refresher, generation_activity_checker=series_generation_use_case),
        rename_series=RenameSeries(workspace),
        rename_video=RenameVideo(workspace),
        export_series_archive=ExportSeriesArchive(workspace),
        import_local_series=ImportLocalSeries(workspace),
        import_local_playground_videos=ImportLocalPlaygroundVideos(workspace),
        import_local_series_videos=ImportLocalSeriesVideos(workspace),
        create_agent_series=CreateAgentLinkedSeries(workspace, workspace_index_invalidator),
        resolve_bilibili_series=ResolveBilibiliSeries(workspace, bilibili_resolver, workspace_index_invalidator),
        resolve_bilibili_video=ResolveBilibiliVideo(workspace, bilibili_resolver, workspace_index_invalidator),
        resolve_linked_series=ResolveLinkedSeries(workspace, external_resolvers, workspace_index_invalidator),
        resolve_linked_video=ResolveLinkedVideo(workspace, external_resolvers, workspace_index_invalidator),
        bilibili_cookie_initializer=bilibili_cookie_initializer,
        external_cookie_initializers=external_cookie_initializers,
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
            whisper_cpp_model_manager=whisper_cpp_manager,
            rag_model_manager=rag_model_manager,
        ),
        usage_store=usage_store,
        get_agent_graph_service=agent_runtime.get_agent_graph_service,
        get_agent_context_usage=agent_runtime.get_context_budget_service,
        agent_session_store=agent_session_store,
        invalidate_agent_graph_service=agent_runtime.invalidate_agent_graph_service,
        invalidate_agent_workspace_indexes=agent_runtime.invalidate_workspace_indexes,
        refresh_agent_workspace_indexes=agent_runtime.refresh_workspace_indexes,
    )
