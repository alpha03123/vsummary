from __future__ import annotations

import json
from pathlib import Path

from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset
from backend.video_summary.generation.ports import (
    MediaProcessor,
    ProgressReporter,
    Summarizer,
    TranscriptEnhancer,
    Transcriber,
)


class GenerateVideoSummary:
    def __init__(
        self,
        media_processor: MediaProcessor,
        transcriber: Transcriber,
        transcript_enhancer: TranscriptEnhancer | None,
        summarizer: Summarizer,
    ) -> None:
        self._media_processor = media_processor
        self._transcriber = transcriber
        self._transcript_enhancer = transcript_enhancer
        self._summarizer = summarizer

    def run(
        self,
        video_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
    ) -> SummaryDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path = output_dir / "audio.wav"
        transcript_stem = output_dir / "transcript"

        if progress_reporter is not None:
            progress_reporter.update("probe", 5.0, "正在探测视频时长")
        video = VideoAsset(
            source_path=video_path,
            title=video_path.stem,
            duration_seconds=self._media_processor.probe_duration(video_path),
        )

        if progress_reporter is not None:
            progress_reporter.update("extract_audio", 15.0, "正在提取音频")
        self._media_processor.extract_audio(video_path, audio_path)
        if progress_reporter is not None:
            progress_reporter.update("transcribe", 20.0, "正在转写音频")
        transcript = self._transcriber.transcribe(
            audio_path,
            transcript_stem,
            on_progress=(
                None
                if progress_reporter is None
                else lambda ratio: progress_reporter.update(
                    "transcribe",
                    20.0 + max(0.0, min(1.0, ratio)) * 55.0,
                    "Whisper 正在转写",
                )
            ),
        )

        if self._transcript_enhancer is not None:
            if progress_reporter is not None:
                progress_reporter.update("enhance_transcript", 78.0, "正在纠正转写文本")
            transcript = self._transcript_enhancer.enhance(video, transcript, output_dir)

        (output_dir / "transcript.cleaned.json").write_text(
            json.dumps(_build_transcript_payload(video, transcript), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if progress_reporter is not None:
            progress_reporter.update("summarize", 88.0, "正在生成 AI 概况")
        return self._summarizer.summarize(video, transcript, output_dir)


def _build_transcript_payload(video: VideoAsset, transcript: Transcript) -> dict[str, object]:
    return {
        "title": video.title,
        "language": transcript.language,
        "duration_seconds": video.duration_seconds,
        "segments": [
            {
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "text": segment.text,
            }
            for segment in transcript.segments
        ],
    }
