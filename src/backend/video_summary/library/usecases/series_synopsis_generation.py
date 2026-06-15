"""系列级知识记忆与目录索引的用例。

"系列知识记忆"是跨视频提炼出的可重用知识（与单视频总结不同），刷新频率
更慢、粒度更粗；本模块提供"重建系列目录 payload → 落盘 → 触发单视频索引
upsert"这一完整闭环，供系列生成用例在每条视频完成后回调。
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.video_summary.library.ports import VideoLibraryReader, WorkspaceIndexRefresher


def build_series_catalog_payload(
    workspace: VideoLibraryReader,
    series_id: str,
    *,
    updated_at: str | None = None,
) -> dict[str, object]:
    """从工作区读出现有总结，拼装出系列目录的可检索 payload。

    业务目的：Agent 在 series scope 下做"目录概览检索"时直接消费这个结构
    而不必遍历所有视频制品；每个视频条目的 `one_sentence_summary` 与
    `chapter_titles` 已能支持上层提示词做精细化召回。

    Args:
        workspace: 用于读取系列清单与各视频总结的只读端口。
        series_id: 目标系列 ID。
        updated_at: 自定义更新时间戳；为 `None` 时回退到当前 UTC 时间。

    Returns:
        形如 `{series_id, series_title, videos: [...], updated_at}` 的字典。

    Raises:
        LookupError: 系列不存在。
    """
    series = next((item for item in workspace.list_series() if item.id == series_id), None)
    if series is None:
        raise LookupError(f"series not found '{series_id}'")

    videos: list[dict[str, object]] = []
    for video in series.videos:
        summary = workspace.get_video_summary(series_id, video.id)
        if summary is None:
            videos.append(
                {
                    "video_id": video.id,
                    "title": video.title,
                    "one_sentence_summary": "",
                    "chapter_titles": [],
                    "processed": video.processed,
                }
            )
            continue

        payload = summary.summary if isinstance(summary.summary, dict) else {}
        chapter_titles = [
            str(chapter.get("title", "")).strip()
            for chapter in payload.get("chapters", [])
            if isinstance(chapter, dict) and str(chapter.get("title", "")).strip()
        ]
        videos.append(
            {
                "video_id": video.id,
                "title": summary.title,
                "one_sentence_summary": str(payload.get("one_sentence_summary", "")).strip(),
                "chapter_titles": chapter_titles,
                "processed": video.processed,
            }
        )

    return {
        "series_id": series.id,
        "series_title": series.title,
        "videos": videos,
        "updated_at": updated_at or _now_iso(),
    }


class RefreshSeriesKnowledgeMemory:
    """刷新某个视频所在的系列目录记忆，并让 RAG 索引反映最新内容。

    业务场景：单视频生成完成后回调——保证 Agent 在 series scope 下做"目录
    概览"时立刻看到新增视频的一行总结与章节列表。

    注意：单视频的"内容"早已由 `WorkspaceIndexRefresher.upsert_video` 负责
    upsert，本用例额外承担"系列目录"这一聚合视图的更新。
    """

    def __init__(
        self,
        *,
        workspace,
        index_refresher: WorkspaceIndexRefresher,
    ) -> None:
        """注入工作区端口与索引刷新器。

        Args:
            workspace: 同时承担"读系列 + 写系列目录 payload"的端口。
            index_refresher: 用于在目录更新后把指定视频重新 upsert 进索引。
        """
        self._workspace = workspace
        self._index_refresher = index_refresher

    def refresh(self, series_id: str, video_id: str) -> None:
        """重建系列目录 payload 并落盘，再触发指定视频的索引 upsert。

        Args:
            series_id: 目标系列 ID。
            video_id: 刚完成生成的视频 ID，用于索引端做"粒度最细的"刷新。

        Raises:
            LookupError: 系列不存在（由 `build_series_catalog_payload` 抛出）。
        """
        catalog = build_series_catalog_payload(self._workspace, series_id)
        self._workspace.save_series_catalog(series_id, catalog)
        self._index_refresher.upsert_video(series_id, video_id)


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串（使用 `Z` 后缀以匹配前端的解析习惯）。"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
