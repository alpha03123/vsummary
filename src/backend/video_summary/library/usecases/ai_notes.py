"""直接生成并保存视频 AI 笔记的用例。"""

from __future__ import annotations

from typing import Protocol

from backend.video_summary.library.models import VideoNoteDTO, VideoSummaryDTO, VideoTranscriptDTO
from backend.video_summary.library.ports import VideoNotesStore, VideoLibraryReader, WorkspaceIndexRefresher


class AiNoteGenerator(Protocol):
    def run(self, *, transcript: VideoTranscriptDTO, summary: VideoSummaryDTO | None, template: str) -> str:
        """根据转写生成 Markdown 笔记。"""


class VideoAiNoteStore(VideoLibraryReader, VideoNotesStore, Protocol):
    """AI 笔记生成需要的读取与写入能力。"""


class GenerateVideoAiNote:
    """读取现有转写，生成一篇 AI 笔记并立即写入笔记列表。"""

    def __init__(
        self,
        workspace: VideoAiNoteStore,
        generator: AiNoteGenerator,
        index_refresher: WorkspaceIndexRefresher | None = None,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str, *, template: str) -> VideoNoteDTO | None:
        if self._workspace.get_video_source(series_id, video_id) is None:
            return None
        transcript = self._workspace.get_video_transcript(series_id, video_id)
        if transcript is None:
            raise ValueError("请先生成视频转写，再生成 AI 笔记。")
        summary = self._workspace.get_video_summary(series_id, video_id)
        content = self._generator.run(transcript=transcript, summary=summary, template=template)
        note = self._workspace.create_video_note(
            series_id,
            video_id,
            title=transcript.title,
            content=content,
            source="agent",
        )
        if note is not None and self._index_refresher is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return note
