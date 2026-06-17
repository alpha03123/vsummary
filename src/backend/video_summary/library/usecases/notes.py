"""视频笔记的 CRUD 用例集合。

笔记是用户在视频维度上的"个人注释"，与"知识卡"不同：笔记是用户主写、
可编辑、可删除；"AI 生成笔记"作为来源之一在 `source` 字段区分。
写操作完成后会触发 RAG 索引的 upsert，使得笔记内容能被 Agent 即时检索到。
"""

from __future__ import annotations

from backend.video_summary.library.models import VideoNoteDTO, VideoNotesDTO
from backend.video_summary.library.ports import VideoNotesStore, WorkspaceIndexRefresher


class GetVideoNotes:
    """取指定视频的笔记集合。"""

    def __init__(self, workspace: VideoNotesStore) -> None:
        """通过 `VideoNotesStore` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        """返回视频的笔记集合 DTO；不存在则返回 `None`。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。

        Returns:
            包含若干 `VideoNoteDTO` 的集合 DTO；没有笔记时返回 `None`。
        """
        return self._workspace.get_video_notes(series_id, video_id)


class CreateVideoNote:
    """新增一条视频笔记并落盘。

    业务场景：用户在视频工作区写下手写笔记，或由 Agent 把"AI 生成笔记"
    写回；本用例不区分来源，由调用方在 `source` 字段标注。
    副作用：落盘后调用 `WorkspaceIndexRefresher.upsert_video` 让新笔记
    可被 RAG 检索到。
    """

    def __init__(self, workspace: VideoNotesStore, index_refresher: WorkspaceIndexRefresher | None = None) -> None:
        """注入笔记存储与可选的索引刷新器。

        Args:
            workspace: 真正落盘笔记的下游端口。
            index_refresher: 用于在笔记落盘后更新 RAG 索引；
                为 `None` 时跳过索引刷新（适用于测试）。
        """
        self._workspace = workspace
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str, *, title: str, content: str, source: str) -> VideoNoteDTO | None:
        """创建一条笔记并返回落库后的 DTO。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            title: 笔记标题。
            content: 笔记正文（Markdown 文本）。
            source: 笔记来源标识（如 "user" / "agent" 等）。

        Returns:
            包含分配 ID 与时间戳的 `VideoNoteDTO`；存储层失败时返回 `None`。
        """
        note = self._workspace.create_video_note(
            series_id,
            video_id,
            title=title,
            content=content,
            source=source,
        )
        if note is not None and self._index_refresher is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return note


class UpdateVideoNote:
    """更新一条已存在的视频笔记。"""

    def __init__(self, workspace: VideoNotesStore, index_refresher: WorkspaceIndexRefresher | None = None) -> None:
        """注入笔记存储与可选的索引刷新器。

        Args:
            workspace: 真正写回笔记的下游端口。
            index_refresher: 用于在笔记更新后刷新 RAG 索引；
                为 `None` 时跳过索引刷新。
        """
        self._workspace = workspace
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str, note_id: str, *, title: str, content: str) -> VideoNoteDTO | None:
        """更新指定笔记并返回最新 DTO。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            note_id: 笔记 ID。
            title: 新的笔记标题。
            content: 新的笔记正文（Markdown 文本）。

        Returns:
            更新后的 `VideoNoteDTO`；笔记不存在时返回 `None`。
        """
        note = self._workspace.update_video_note(
            series_id,
            video_id,
            note_id,
            title=title,
            content=content,
        )
        if note is not None and self._index_refresher is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return note


class DeleteVideoNote:
    """删除一条视频笔记。"""

    def __init__(self, workspace: VideoNotesStore, index_refresher: WorkspaceIndexRefresher | None = None) -> None:
        """注入笔记存储与可选的索引刷新器。

        Args:
            workspace: 真正删除笔记的下游端口。
            index_refresher: 用于在笔记删除后让 RAG 索引反映最新内容；
                为 `None` 时跳过索引刷新。
        """
        self._workspace = workspace
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str, note_id: str) -> bool | None:
        """删除指定笔记并视情况刷新索引。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            note_id: 笔记 ID。

        Returns:
            `True` 表示实际删除，`False` 表示未找到；`None` 由存储层自定义。
        """
        deleted = self._workspace.delete_video_note(series_id, video_id, note_id)
        if deleted and self._index_refresher is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return deleted
