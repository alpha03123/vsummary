from __future__ import annotations

import json
from pathlib import Path

from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset
from backend.video_summary.generation.ports import MediaProcessor, Summarizer, Transcriber


class GenerateVideoSummary:
    def __init__(
        self,
        media_processor: MediaProcessor,
        transcriber: Transcriber,
        summarizer: Summarizer,
    ) -> None:
        self._media_processor = media_processor
        self._transcriber = transcriber
        self._summarizer = summarizer

    def run(self, video_path: Path, output_dir: Path) -> SummaryDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path = output_dir / "audio.wav"
        transcript_stem = output_dir / "transcript"

        video = VideoAsset(
            source_path=video_path,
            title=video_path.stem,
            duration_seconds=self._media_processor.probe_duration(video_path),
        )
        self._media_processor.extract_audio(video_path, audio_path)
        transcript = self._transcriber.transcribe(audio_path, transcript_stem)

        (output_dir / "transcript.cleaned.json").write_text(
            json.dumps(_build_transcript_payload(video, transcript), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
