"""唯一 AI 概括的生成与编辑用例。"""

from __future__ import annotations

from typing import Protocol, Callable

from backend.video_summary.library.models import (
    GeneratedVideoAiNoteDTO,
    VideoAiSummaryDTO,
    VideoAiNoteVisualContextDTO,
    VideoSummaryDTO,
    VideoTranscriptDTO,
    VideoVisualInputFrameDTO,
    AiSummaryVisualEvidenceDTO,
)
from backend.video_summary.library.ports import NoteFrameMaterializer, VideoAiSummaryStore as VideoAiSummaryStorePort, VideoLibraryReader, VisualFramePoolBuilder, WorkspaceIndexRefresher
from backend.video_summary.library.usecases.ai_notes import (
    _split_note_title,
    constrain_ai_note_image_markers,
)
from backend.video_summary.library.note_images import materialize_note_frames


class AiSummaryGenerator(Protocol):
    """复用 AI 笔记生成器的多模态输入和 Markdown 输出能力。"""

    def run_ai_summary(
        self,
        *,
        transcript: VideoTranscriptDTO,
        summary: VideoSummaryDTO | None,
        visual_context,
        template: str,
    ) -> GeneratedVideoAiNoteDTO:
        ...

    async def arun_ai_summary(self, *, transcript: VideoTranscriptDTO, summary: VideoSummaryDTO | None,
        visual_context: VideoAiNoteVisualContextDTO, template: str) -> GeneratedVideoAiNoteDTO:
        ...


class VideoAiSummaryStore(VideoLibraryReader, VideoAiSummaryStorePort, Protocol):
    """AI 概括生成所需的读取和唯一制品写入能力。"""


class GenerateVideoAiSummary:
    """生成并原子替换每个视频唯一的 AI 概括。"""

    def __init__(
        self,
        workspace: VideoAiSummaryStore,
        generator: AiSummaryGenerator,
        index_refresher: WorkspaceIndexRefresher | None = None,
        max_visual_input_images: int | None = None,
        multimodal_enabled: bool = True,
        frame_pool_builder: VisualFramePoolBuilder | None = None,
        note_frame_materializer: NoteFrameMaterializer | None = None,
        multimodal_policy: Callable[[], bool] | None = None,
        saved_visual_context=None,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._index_refresher = index_refresher
        self._max_visual_input_images = max_visual_input_images
        self._multimodal_enabled = multimodal_enabled
        self._multimodal_policy = multimodal_policy
        self._saved_visual_context = saved_visual_context
        self._frame_pool_builder = frame_pool_builder
        self._note_frame_materializer = note_frame_materializer

    def run(self, series_id: str, video_id: str, *, template: str = "general") -> VideoAiSummaryDTO | None:
        workflow = self._generation_requests(series_id, video_id, template=template)
        request = next(workflow)
        generated = self._generator.run_ai_summary(**request)
        try:
            workflow.send(generated)
        except StopIteration as completed:
            return completed.value
        raise AssertionError('AI summary workflow must finish after generation.')

    async def arun(self, series_id: str, video_id: str, *, template: str = "general") -> VideoAiSummaryDTO | None:
        workflow = self._generation_requests(series_id, video_id, template=template)
        request = next(workflow)
        generated = await self._generator.arun_ai_summary(**request)
        try:
            workflow.send(generated)
        except StopIteration as completed:
            return completed.value
        raise AssertionError('AI summary workflow must finish after generation.')

    def _generation_requests(self, series_id: str, video_id: str, *, template: str):
        source = self._workspace.get_video_source(series_id, video_id)
        transcript = self._workspace.get_video_transcript(series_id, video_id)
        if transcript is None:
            raise ValueError("请先生成视频转写，再生成 AI 概括。")
        # B 的事实输入是原始转写和独立帧池，不反向依赖 A 的章节文案或封面图。
        visual_context = VideoAiNoteVisualContextDTO(frames=[])
        if source is None and self._saved_visual_context is not None:
            visual_context = self._saved_visual_context(series_id, video_id)
        multimodal_enabled = self._multimodal_policy() if self._multimodal_policy is not None else self._multimodal_enabled
        if source is not None and multimodal_enabled and self._max_visual_input_images is not None and self._frame_pool_builder is not None:
            visual_context = _build_frame_pool_context(source, visual_context, self._max_visual_input_images, self._frame_pool_builder)
        generated = yield dict(transcript=transcript, summary=None, visual_context=visual_context, template=template)
        title, content = _split_note_title(generated.content, fallback=transcript.title)
        content = constrain_ai_note_image_markers(
            content,
            duration_seconds=transcript.duration_seconds,
            enabled=generated.note_visual_mode == "screenshots",
            max_images=generated.note_max_images,
            min_gap_seconds=generated.note_image_min_gap_seconds,
        )
        if source is not None and self._note_frame_materializer is not None:
            self._note_frame_materializer(video_path=source.source_path, output_dir=source.output_dir, content=content)
        if source is None:
            from backend.video_summary.library.note_images import parse_note_image_markers
            available = {round(frame.timestamp_seconds, 3) for frame in visual_context.frames}
            if any(round(marker.seconds, 3) not in available for marker in parse_note_image_markers(content)):
                raise ValueError('生成内容引用了尚未保存的图片时间点。')
        result = self._workspace.save_video_ai_summary(
            series_id,
            video_id,
            title=title,
            content=content,
            citations=list(generated.citations),
        )
        evidence_writer = getattr(self._workspace, "save_video_ai_summary_visual_evidence", None)
        if result is not None and callable(evidence_writer):
            evidence_writer(series_id, video_id, frames=list(generated.visual_evidence))
        if result is not None and self._index_refresher is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return result


class UpdateVideoAiSummary:
    """编辑既有唯一 AI 概括，不影响时间轴索引或视觉 evidence。"""

    def __init__(self, workspace: VideoAiSummaryStore, index_refresher: WorkspaceIndexRefresher | None = None) -> None:
        self._workspace = workspace
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str, *, title: str, content: str) -> VideoAiSummaryDTO | None:
        result = self._workspace.update_video_ai_summary(series_id, video_id, title=title, content=content)
        if result is not None and self._index_refresher is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return result


def _build_frame_pool_context(source, existing: VideoAiNoteVisualContextDTO, max_input_images: int, frame_pool_builder: VisualFramePoolBuilder) -> VideoAiNoteVisualContextDTO:
    pool = frame_pool_builder(
        video_path=source.source_path,
        output_dir=source.output_dir,
        max_input_images=max_input_images,
    )
    frames = [
        VideoVisualInputFrameDTO(
            chapter_id="visual-frame-pool",
            timestamp_seconds=timestamps[0] if timestamps else 0.0,
            image_filename=path.name,
            image_path=path,
        )
        for path, timestamps in zip(pool.image_paths, pool.timestamps_by_image, strict=True)
    ]
    return VideoAiNoteVisualContextDTO(
        frames=frames,
        evidence_text=existing.evidence_text,
        evidence_timestamps=tuple(timestamp for group in pool.timestamps_by_image for timestamp in group),
    )
