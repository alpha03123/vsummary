from __future__ import annotations

import json
from pathlib import Path

from app.contracts import Summarizer, Transcriber
from domain.models import SummaryDocument, VideoAsset
from infra.media_tools import extract_audio, probe_duration


class VideoSummaryPipeline:
    def __init__(
        self,
        transcriber: Transcriber,
        summarizer: Summarizer,
    ) -> None:
        self._transcriber = transcriber
        self._summarizer = summarizer

    def run(self, video_path: Path, output_dir: Path) -> SummaryDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path = output_dir / "audio.wav"
        transcript_stem = output_dir / "transcript"

        video = VideoAsset(
            source_path=video_path,
            title=video_path.stem,
            duration_seconds=probe_duration(video_path),
        )
        extract_audio(video_path, audio_path)
        transcript = self._transcriber.transcribe(audio_path, transcript_stem)

        transcript_json = {
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
        (output_dir / "transcript.cleaned.json").write_text(
            json.dumps(transcript_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return self._summarizer.summarize(video, transcript, output_dir)
