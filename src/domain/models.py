from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VideoAsset:
    source_path: Path
    title: str
    duration_seconds: float


@dataclass(frozen=True)
class TranscriptSegment:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class Transcript:
    language: str
    segments: list[TranscriptSegment]

    @property
    def full_text(self) -> str:
        return "\n".join(segment.text.strip() for segment in self.segments if segment.text.strip())


@dataclass(frozen=True)
class SummaryDocument:
    markdown: str
    summary_data: dict[str, Any]
    mindmap_data: dict[str, Any]
