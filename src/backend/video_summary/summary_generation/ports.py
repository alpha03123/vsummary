from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

from backend.video_summary.summary_generation.models import SummaryDocument, Transcript, VideoAsset

if TYPE_CHECKING:
    from backend.video_summary.summary_generation.cancellation import GenerationCancellationContext


class MediaProcessor(Protocol):
    def probe_duration(self, video_path: Path) -> float:
        ...

    def extract_audio(
        self,
        video_path: Path,
        audio_path: Path,
        cancellation: "GenerationCancellationContext | None" = None,
    ) -> Path:
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
    async def summarize(
        self,
        video: VideoAsset,
        transcript: Transcript,
        cancellation: "GenerationCancellationContext | None" = None,
    ) -> SummaryDocument:
        ...


class TranscriptEnhancer(Protocol):
    async def enhance(
        self,
        video: VideoAsset,
        transcript: Transcript,
        cancellation: "GenerationCancellationContext | None" = None,
    ) -> Transcript:
        ...


class MindmapGenerator(Protocol):
    async def generate(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
    ) -> dict[str, object]:
        ...


class GenerationArtifactStore(Protocol):
    async def save_cleaned_transcript(
        self,
        *,
        video: VideoAsset,
        transcript: Transcript,
        output_dir: Path,
    ) -> None:
        ...

    async def save_enhanced_transcript(
        self,
        *,
        transcript: Transcript,
        output_dir: Path,
    ) -> None:
        ...

    async def save_summary_document(self, *, document: SummaryDocument, output_dir: Path) -> None:
        ...

    async def save_mindmap(self, *, mindmap: dict[str, object], output_dir: Path) -> None:
        ...


class ProgressReporter(Protocol):
    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        ...

    def completed(self, detail: str | None = None) -> None:
        ...

    def failed(self, message: str) -> None:
        ...

    def cancelled(self, detail: str | None = None) -> None:
        ...

    def is_cancel_requested(self) -> bool:
        ...

    def raise_if_cancelled(self) -> None:
        ...
