"""知识卡生成与落盘的用例。

知识卡是基于视频总结数据提炼出的"卡片式"知识条目，区别于总结本身，
更偏问答/概念粒度；本模块把"调用生成器 → 写回制品 → 触发索引刷新"封装为
单一用例，供 API 路由直接调用。
"""

from __future__ import annotations

from backend.video_summary.library.models import VideoKnowledgeCardsDTO
from backend.video_summary.library.ports import KnowledgeCardGenerator, VideoKnowledgeCardStore, WorkspaceIndexRefresher


class GenerateVideoKnowledgeCards:
    """基于已有视频总结生成知识卡并落盘。

    业务场景：在视频已经完成总结后，用户希望进一步获得"问答/概念卡"形式的
    可记忆知识；本用例读取总结 → 调用生成器 → 写回制品目录 → 视情况触发
    RAG 索引刷新，使得后续 Agent 检索能即时看到新增的知识卡。

    前置条件：必须先存在该视频的 `VideoSourceDTO` 与 `VideoSummaryDTO`；
    缺一即短路返回 `None`，避免在残缺制品上做无意义的生成调用。
    """

    def __init__(
        self,
        workspace: VideoKnowledgeCardStore,
        generator: KnowledgeCardGenerator,
        index_refresher: WorkspaceIndexRefresher | None = None,
    ) -> None:
        """注入读/写知识卡的复合端口、生成器与可选的索引刷新器。

        Args:
            workspace: 同时承担"读制品 + 写知识卡"的复合端口。
            generator: 纯函数式的知识卡生成器（不落盘）。
            index_refresher: 落盘后用于把新知识卡 upsert 进 RAG 索引的刷新器，
                若为 `None` 则跳过索引刷新（适用于只读/测试场景）。
        """
        self._workspace = workspace
        self._generator = generator
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        """为指定视频生成知识卡并落盘，返回最终制品 DTO。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。

        Returns:
            落盘后的 `VideoKnowledgeCardsDTO`；若视频源或总结不存在则返回 `None`，
            不会抛异常（由调用方决定如何处理"未生成"场景）。
        """
        if self._workspace.get_video_source(series_id, video_id) is None:
            return None

        summary = self._workspace.get_video_summary(series_id, video_id)
        if summary is None:
            return None

        cards = self._generator.run(title=summary.title, summary_data=summary.summary)
        self._workspace.save_video_knowledge_cards(
            series_id,
            video_id,
            title=summary.title,
            cards=cards,
        )
        if self._index_refresher is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return self._workspace.get_video_knowledge_cards(series_id, video_id)
