from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from backend.video_summary.library.models import (
    KnowledgeCardDTO,
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
    TranscriptSegmentDTO,
    VideoKnowledgeCardsDTO,
    VideoMindmapDTO,
    VideoSummaryDTO,
    VideoTranscriptDTO,
)
from backend.video_summary.library.usecases import ExportSeriesArchive


def test_exports_mixed_overviews_as_zip_and_skips_incomplete_videos() -> None:
    workspace = FakeWorkspace()
    use_case = ExportSeriesArchive(workspace)

    archive = use_case.run("series-1", "mixed")

    assert archive.filename == "series-1-mixed.zip"
    entries = _read_zip(archive.content)
    assert list(entries) == ["01-video-1-mixed.md"]
    assert "# 第一讲" in entries["01-video-1-mixed.md"]
    assert "核心问题" in entries["01-video-1-mixed.md"]
    assert "查看本章原文" in entries["01-video-1-mixed.md"]


def test_exports_knowledge_cards_as_zip() -> None:
    workspace = FakeWorkspace()
    use_case = ExportSeriesArchive(workspace)

    archive = use_case.run("series-1", "knowledge-cards")

    entries = _read_zip(archive.content)
    assert list(entries) == ["01-video-1-knowledge-cards.md"]
    assert "# 第一讲 知识卡片" in entries["01-video-1-knowledge-cards.md"]
    assert "## 冷启动" in entries["01-video-1-knowledge-cards.md"]


def test_exports_mindmaps_as_zip() -> None:
    workspace = FakeWorkspace()
    use_case = ExportSeriesArchive(workspace)

    archive = use_case.run("series-1", "mindmaps")

    entries = _read_zip(archive.content)
    assert list(entries) == ["01-video-1-mindmap.md"]
    assert "- **根节点**" in entries["01-video-1-mindmap.md"]


def test_raises_when_no_exportable_artifacts_exist() -> None:
    workspace = FakeWorkspace()
    workspace.summaries.clear()
    workspace.transcripts.clear()
    use_case = ExportSeriesArchive(workspace)

    with pytest.raises(LookupError, match="no exportable mixed artifacts"):
        use_case.run("series-1", "mixed")


def test_rejects_unknown_export_kind() -> None:
    workspace = FakeWorkspace()
    use_case = ExportSeriesArchive(workspace)

    with pytest.raises(ValueError, match="unsupported series export kind"):
        use_case.run("series-1", "bad")


def _read_zip(content: bytes) -> dict[str, str]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return {
            name: archive.read(name).decode("utf-8")
            for name in archive.namelist()
        }


class FakeWorkspace:
    def __init__(self) -> None:
        self.series = LibrarySeriesDTO(
            id="series-1",
            title="课程",
            videos=[
                LibraryVideoCardDTO(
                    id="video-1",
                    title="第一讲",
                    source_name="video-1.mp4",
                    processed=True,
                    status="ready",
                ),
                LibraryVideoCardDTO(
                    id="video-2",
                    title="第二讲",
                    source_name="video-2.mp4",
                    processed=False,
                    status="pending",
                ),
            ],
        )
        self.summaries = {
            "video-1": VideoSummaryDTO(
                series_id="series-1",
                video_id="video-1",
                title="第一讲",
                summary={
                    "title": "第一讲",
                    "core_problem": "核心问题",
                    "key_takeaways": ["要点一"],
                    "chapters": [
                        {
                            "title": "开场",
                            "start_seconds": 0.0,
                            "end_seconds": 3.0,
                            "summary": "介绍主题",
                            "key_points": ["背景"],
                        }
                    ],
                },
            )
        }
        self.transcripts = {
            "video-1": VideoTranscriptDTO(
                series_id="series-1",
                video_id="video-1",
                title="第一讲",
                duration_seconds=3.0,
                segments=[
                    TranscriptSegmentDTO(start_seconds=0.0, end_seconds=3.0, text="开场介绍"),
                ],
            )
        }
        self.knowledge_cards = {
            "video-1": VideoKnowledgeCardsDTO(
                series_id="series-1",
                video_id="video-1",
                title="第一讲",
                cards=[
                    KnowledgeCardDTO(
                        id="card-1",
                        title="冷启动",
                        kind="method",
                        summary="先解决曝光。",
                        details="围绕目标用户发布内容。",
                        tags=["增长"],
                        keywords=["曝光"],
                        related_card_ids=[],
                    )
                ],
            )
        }
        self.mindmaps = {
            "video-1": VideoMindmapDTO(
                series_id="series-1",
                video_id="video-1",
                title="第一讲",
                mindmap={"title": "根节点", "summary": "概要", "children": []},
            )
        }

    def list_series(self) -> list[LibrarySeriesDTO]:
        return [self.series]

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        return self.summaries.get(video_id)

    def get_video_transcript(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        return self.transcripts.get(video_id)

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        return self.knowledge_cards.get(video_id)

    def get_video_mindmap(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        return self.mindmaps.get(video_id)
