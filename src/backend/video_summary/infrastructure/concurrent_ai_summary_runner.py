"""在转写完成后并发生成唯一 AI 概括的运行器。"""

from __future__ import annotations

import json
import logging
import asyncio
from pathlib import Path

from backend.shared.filesystem import atomic_write_text
from backend.video_summary.domain.models import Transcript, VideoAsset
from backend.video_summary.infrastructure.llm.litellm_note_generator import LiteLLMNoteGenerator
from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor
from backend.video_summary.infrastructure.visual_frame_pool import build_or_load_visual_frame_pool
from backend.video_summary.library.models import TranscriptSegmentDTO, VideoAiNoteVisualContextDTO, VideoTranscriptDTO, VideoVisualInputFrameDTO
from backend.video_summary.library.note_images import materialize_note_frames
from backend.video_summary.library.usecases.ai_notes import _split_note_title, constrain_ai_note_image_markers


LOGGER = logging.getLogger(__name__)


class ConcurrentAiSummaryRunner:
    """复用 AI 概括生成器和帧池，在 A 生成期间独立写入 AI 概括制品。"""

    def __init__(
        self,
        *,
        generator: LiteLLMNoteGenerator,
        max_input_images: int,
        multimodal_enabled: bool,
        note_visual_mode: str,
        note_max_images: int,
        note_image_min_gap_seconds: float,
        media_processor: FfmpegMediaProcessor,
    ) -> None:
        self._generator = generator
        self._max_input_images = max_input_images
        self._multimodal_enabled = multimodal_enabled
        self._note_visual_mode = note_visual_mode
        self._note_max_images = note_max_images
        self._note_image_min_gap_seconds = note_image_min_gap_seconds
        self._media_processor = media_processor

    async def run(self, *, video: VideoAsset, transcript: Transcript, output_dir: Path) -> None:
        _write_status(output_dir, "running")
        try:
            await asyncio.to_thread(self._run_sync, video=video, transcript=transcript, output_dir=output_dir)
        except Exception as error:
            _write_status(output_dir, "failed", str(error))
            raise
        else:
            _write_status(output_dir, "ready")

    def _run_sync(self, *, video: VideoAsset, transcript: Transcript, output_dir: Path) -> None:
        pool = (
            build_or_load_visual_frame_pool(
                video_path=video.source_path,
                output_dir=output_dir,
                max_input_images=self._max_input_images,
                media_processor=self._media_processor,
            )
            if self._multimodal_enabled
            else None
        )
        image_paths = pool.image_paths if pool is not None else []
        timestamps_by_image = pool.timestamps_by_image if pool is not None else []
        context = VideoAiNoteVisualContextDTO(
            frames=[
                VideoVisualInputFrameDTO(
                    chapter_id="visual-frame-pool",
                    timestamp_seconds=timestamps[0] if timestamps else 0.0,
                    image_filename=path.name,
                    image_path=path,
                )
                for path, timestamps in zip(image_paths, timestamps_by_image, strict=True)
            ],
            evidence_timestamps=tuple(timestamp for group in timestamps_by_image for timestamp in group),
        )
        generated = self._generator.run_ai_summary(
            transcript=VideoTranscriptDTO(
                series_id="",
                video_id="",
                title=video.title,
                duration_seconds=video.duration_seconds,
                segments=[
                    TranscriptSegmentDTO(start_seconds=item.start_seconds, end_seconds=item.end_seconds, text=item.text)
                    for item in transcript.segments
                ],
            ),
            summary=None,
            visual_context=context,
            template="general",
            multimodal_enabled=self._multimodal_enabled,
            note_visual_mode=self._note_visual_mode,
            note_max_images=self._note_max_images,
            note_image_min_gap_seconds=self._note_image_min_gap_seconds,
        )
        title, content = _split_note_title(generated.content, fallback=video.title)
        content = constrain_ai_note_image_markers(
            content,
            summary=None,
            duration_seconds=video.duration_seconds,
            enabled=generated.note_visual_mode == "screenshots",
            max_images=generated.note_max_images,
            min_gap_seconds=generated.note_image_min_gap_seconds,
        )
        materialize_note_frames(
            video_path=video.source_path,
            output_dir=output_dir,
            content=content,
            frame_extractor=self._media_processor,
        )
        now = _utc_now()
        atomic_write_text(
            output_dir / "ai_summary.json",
            json.dumps(
                {
                    "title": title,
                    "content": content,
                    "citations": [citation.model_dump(mode="json") for citation in generated.citations],
                    "created_at": now,
                    "updated_at": now,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        atomic_write_text(
            output_dir / "ai_summary.visual_evidence.json",
            json.dumps(
                {"frames": [{"timestamp_seconds": frame.timestamp_seconds, "text": frame.text} for frame in generated.visual_evidence]},
                ensure_ascii=False,
                indent=2,
            ),
        )


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_status(output_dir: Path, status: str, error: str = "") -> None:
    atomic_write_text(
        output_dir / "ai_summary.status.json",
        json.dumps({"status": status, "error": error}, ensure_ascii=False, indent=2),
    )
