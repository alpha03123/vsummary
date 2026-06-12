from __future__ import annotations

from backend.video_summary.workspace.models import KnowledgeCardDTO, VideoKnowledgeCardsDTO
from backend.video_summary.summary_generation.service_ports import KnowledgeCardGenerator, KnowledgeCardResult
from backend.video_summary.workspace.index_ports import WorkspaceIndexRefresher
from backend.video_summary.workspace.ports import VideoKnowledgeCardStore


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

        cards = [_to_workspace_card(card) for card in self._generator.run(title=summary.title, summary_data=summary.summary)]
        self._workspace.save_video_knowledge_cards(
            series_id,
            video_id,
            title=summary.title,
            cards=cards,
        )
        if self._index_refresher is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return self._workspace.get_video_knowledge_cards(series_id, video_id)


def _to_workspace_card(card: KnowledgeCardResult) -> KnowledgeCardDTO:
    return KnowledgeCardDTO(
        id=card.id,
        title=card.title,
        kind=card.kind,
        summary=card.summary,
        details=card.details,
        tags=card.tags,
        keywords=card.keywords,
        related_card_ids=card.related_card_ids,
    )
