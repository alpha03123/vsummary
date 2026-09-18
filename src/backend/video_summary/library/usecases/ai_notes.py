"""直接生成并保存视频 AI 笔记的用例。"""

from __future__ import annotations

from typing import Protocol

from backend.video_summary.library.models import VideoNoteDTO, VideoSummaryDTO, VideoTranscriptDTO
from backend.video_summary.library.ports import VideoNotesStore, VideoLibraryReader, WorkspaceIndexRefresher


class AiNoteGenerator(Protocol):
    def run(self, *, transcript: VideoTranscriptDTO, summary: VideoSummaryDTO | None, template: str) -> str:
        """根据转写生成 Markdown 笔记。"""


def _split_note_title(content: str, *, fallback: str) -> tuple[str, str]:
    """把模型输出的首行一级标题拆出来作为笔记标题。

    提示词要求正文第一行是 `# 标题`；拆出后从正文中移除，避免与笔记详情页
    自身的标题重复渲染。首行不是一级标题时标题回退到 `fallback`。

    Args:
        content: 模型返回的 Markdown 笔记。
        fallback: 没有可用标题时的兜底标题（通常是视频标题）。

    Returns:
        `(笔记标题, 去掉标题行后的正文)`。
    """
    stripped = content.lstrip("\n")
    first_line, _, rest = stripped.partition("\n")
    heading = first_line.strip()
    if heading.startswith("# "):
        title = heading[2:].strip().strip("#").strip()
        if title:
            return title, rest.lstrip("\n")
    return fallback, content


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
        note_title, note_content = _split_note_title(content, fallback=transcript.title)
        note = self._workspace.create_video_note(
            series_id,
            video_id,
            title=note_title,
            content=note_content,
            source="agent",
        )
        if note is not None and self._index_refresher is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return note
