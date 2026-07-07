"""Agent 工作区 RAG 索引的轻量刷新包装。

把 `SeriesRetrievalService.refresh` 重新以 `AgentWorkspaceIndexBuilder.refresh`
形式暴露，便于在不需要更细粒度 upsert/delete 时以单一接口调用全量刷新。
"""

from __future__ import annotations

from backend.video_summary.infrastructure.agent_memory.retrieval import SeriesRetrievalService


class AgentWorkspaceIndexBuilder:
    """Agent 工作区索引刷新器。

    业务目的：在 bootstrap 启动后台刷新线程时以一个简短入口触发索引刷新，
    内部把请求转发给 `SeriesRetrievalService`。
    """

    def __init__(self, *, retrieval_service: SeriesRetrievalService) -> None:
        """注入底层的 `SeriesRetrievalService`。

        Args:
            retrieval_service: 实际执行 LanceDB 索引读写的检索服务。
        """
        self._retrieval_service = retrieval_service

    def refresh(self) -> None:
        """触发一次全量索引刷新（语义等同于 `SeriesRetrievalService.refresh`）。"""
        self._retrieval_service.refresh()
