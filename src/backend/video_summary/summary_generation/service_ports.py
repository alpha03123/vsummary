from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from backend.video_summary.summary_generation.ports import ProgressReporter


@dataclass(frozen=True)
class KnowledgeCardResult:
    id: str
    title: str
    kind: str
    summary: str
    details: str
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    related_card_ids: list[str] = field(default_factory=list)


class VideoSummaryGenerator(Protocol):
    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> None:
        ...


class VideoMindmapGenerator(Protocol):
    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        summary_data: dict[str, object],
    ) -> None:
        ...


class KnowledgeCardGenerator(Protocol):
    def run(self, *, title: str, summary_data: dict[str, object]) -> list[KnowledgeCardResult]:
        ...


class VideoGenerationProgressTracker(Protocol):
    def create_reporter(self, task_id: str) -> ProgressReporter:
        ...
