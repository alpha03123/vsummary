from __future__ import annotations

from backend.video_summary.adapters.rag.agent_memory.retrieval import SeriesRetrievalService


class AgentWorkspaceIndexBuilder:
    def __init__(self, *, retrieval_service: SeriesRetrievalService) -> None:
        self._retrieval_service = retrieval_service

    def refresh(self) -> None:
        self._retrieval_service.refresh()
