from __future__ import annotations

from backend.video_summary.library.models import VideoKnowledgeCardsDTO
from backend.video_summary.library.ports import KnowledgeCardGenerator, VideoKnowledgeCardStore, WorkspaceIndexRefresher


class GenerateVideoKnowledgeCards:
    def __init__(
        self,
        workspace: VideoKnowledgeCardStore,
        generator: KnowledgeCardGenerator,
        index_refresher: WorkspaceIndexRefresher | None = None,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
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
