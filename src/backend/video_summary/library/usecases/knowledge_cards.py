from __future__ import annotations

from backend.video_summary.library.ports import KnowledgeCardGenerator, VideoWorkspace
from backend.video_summary.library.views import VideoKnowledgeCardsView


class GenerateVideoKnowledgeCards:
    def __init__(self, workspace: VideoWorkspace, generator: KnowledgeCardGenerator) -> None:
        self._workspace = workspace
        self._generator = generator

    def run(self, series_id: str, video_id: str) -> VideoKnowledgeCardsView | None:
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
        return self._workspace.get_video_knowledge_cards(series_id, video_id)
