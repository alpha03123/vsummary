from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset


class MediaProcessor(Protocol):
    def probe_duration(self, video_path: Path) -> float:
        ...

    def extract_audio(self, video_path: Path, audio_path: Path) -> Path:
        ...


class Transcriber(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        output_stem: Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> Transcript:
        ...


class Summarizer(Protocol):
    def summarize(
        self,
        video: VideoAsset,
        transcript: Transcript,
        output_dir: Path,
    ) -> SummaryDocument:
        ...


class TranscriptEnhancer(Protocol):
    def enhance(
        self,
        video: VideoAsset,
        transcript: Transcript,
        output_dir: Path,
    ) -> Transcript:
        ...


class MindmapGenerator(Protocol):
    def generate(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
        output_dir: Path,
    ) -> dict[str, object]:
        ...


class ProgressReporter(Protocol):
    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        ...

    def completed(self, detail: str | None = None) -> None:
        ...

    def failed(self, message: str) -> None:
        ...
