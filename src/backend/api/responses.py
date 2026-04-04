from __future__ import annotations

from pydantic import BaseModel

from backend.agent.schemas.action_plan import AgentTurnResult
from backend.video_summary.library.views import (
    ChapterCardView,
    KnowledgeCardView,
    KnowledgeCardSourceRefView,
    VideoChapterCardsView,
    VideoCardView,
    VideoKnowledgeCardsView,
    VideoLibraryView,
    VideoNoteView,
    VideoNotesView,
    VideoWorkspaceToolsView,
    WorkspaceToolView,
)


class HealthResponse(BaseModel):
    status: str


class VideoCardResponse(BaseModel):
    id: str
    title: str
    source_name: str
    processed: bool
    status: str

    @classmethod
    def from_view(cls, video: VideoCardView) -> "VideoCardResponse":
        return cls(
            id=video.id,
            title=video.title,
            source_name=video.source_name,
            processed=video.processed,
            status=video.status,
        )


class SeriesResponse(BaseModel):
    id: str
    title: str
    videos: list[VideoCardResponse]


class WorkspaceResponse(BaseModel):
    id: str
    title: str


class VideoLibraryResponse(BaseModel):
    workspace: WorkspaceResponse
    series: list[SeriesResponse]

    @classmethod
    def from_view(cls, library: VideoLibraryView) -> "VideoLibraryResponse":
        return cls(
            workspace=WorkspaceResponse(
                id=library.workspace.id,
                title=library.workspace.title,
            ),
            series=[
                SeriesResponse(
                    id=series.id,
                    title=series.title,
                    videos=[VideoCardResponse.from_view(video) for video in series.videos],
                )
                for series in library.series
            ],
        )


class WorkspaceToolResponse(BaseModel):
    id: str
    title: str
    available: bool
    generated: bool
    status: str
    preview_url: str | None = None

    @classmethod
    def from_view(cls, tool: WorkspaceToolView) -> "WorkspaceToolResponse":
        return cls(
            id=tool.id,
            title=tool.title,
            available=tool.available,
            generated=tool.generated,
            status=tool.status,
            preview_url=tool.preview_url,
        )


class VideoWorkspaceToolsResponse(BaseModel):
    series_id: str
    video_id: str
    overview: WorkspaceToolResponse
    knowledge_cards: WorkspaceToolResponse
    mindmap: WorkspaceToolResponse
    notes: WorkspaceToolResponse
    preview: WorkspaceToolResponse
    ai_todo: str

    @classmethod
    def from_view(cls, tools: VideoWorkspaceToolsView) -> "VideoWorkspaceToolsResponse":
        return cls(
            series_id=tools.series_id,
            video_id=tools.video_id,
            overview=WorkspaceToolResponse.from_view(tools.overview),
            knowledge_cards=WorkspaceToolResponse.from_view(tools.knowledge_cards),
            mindmap=WorkspaceToolResponse.from_view(tools.mindmap),
            notes=WorkspaceToolResponse.from_view(tools.notes),
            preview=WorkspaceToolResponse.from_view(tools.preview),
            ai_todo=tools.ai_todo,
        )


class ChapterCardResponse(BaseModel):
    id: str
    title: str
    summary: str
    key_points: list[str]
    start_seconds: float | None = None
    end_seconds: float | None = None
    kind: str

    @classmethod
    def from_view(cls, card: ChapterCardView) -> "ChapterCardResponse":
        return cls(
            id=card.id,
            title=card.title,
            summary=card.summary,
            key_points=card.key_points,
            start_seconds=card.start_seconds,
            end_seconds=card.end_seconds,
            kind=card.kind,
        )


class VideoChapterCardsResponse(BaseModel):
    series_id: str
    video_id: str
    title: str
    cards: list[ChapterCardResponse]

    @classmethod
    def from_view(cls, cards: VideoChapterCardsView) -> "VideoChapterCardsResponse":
        return cls(
            series_id=cards.series_id,
            video_id=cards.video_id,
            title=cards.title,
            cards=[ChapterCardResponse.from_view(card) for card in cards.cards],
        )


class KnowledgeCardSourceRefResponse(BaseModel):
    chapter_id: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    quote: str

    @classmethod
    def from_view(cls, source_ref: KnowledgeCardSourceRefView) -> "KnowledgeCardSourceRefResponse":
        return cls(
            chapter_id=source_ref.chapter_id,
            start_seconds=source_ref.start_seconds,
            end_seconds=source_ref.end_seconds,
            quote=source_ref.quote,
        )


class KnowledgeCardResponse(BaseModel):
    id: str
    title: str
    kind: str
    summary: str
    details: str
    tags: list[str]
    keywords: list[str]
    source_refs: list[KnowledgeCardSourceRefResponse]
    related_card_ids: list[str]

    @classmethod
    def from_view(cls, card: KnowledgeCardView) -> "KnowledgeCardResponse":
        return cls(
            id=card.id,
            title=card.title,
            kind=card.kind,
            summary=card.summary,
            details=card.details,
            tags=card.tags,
            keywords=card.keywords,
            source_refs=[KnowledgeCardSourceRefResponse.from_view(item) for item in card.source_refs],
            related_card_ids=card.related_card_ids,
        )


class VideoKnowledgeCardsResponse(BaseModel):
    series_id: str
    video_id: str
    title: str
    cards: list[KnowledgeCardResponse]

    @classmethod
    def from_view(cls, cards: VideoKnowledgeCardsView) -> "VideoKnowledgeCardsResponse":
        return cls(
            series_id=cards.series_id,
            video_id=cards.video_id,
            title=cards.title,
            cards=[KnowledgeCardResponse.from_view(card) for card in cards.cards],
        )


class VideoNoteResponse(BaseModel):
    id: str
    title: str
    content: str
    source: str
    created_at: str
    updated_at: str

    @classmethod
    def from_view(cls, note: VideoNoteView) -> "VideoNoteResponse":
        return cls(
            id=note.id,
            title=note.title,
            content=note.content,
            source=note.source,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )


class VideoNotesResponse(BaseModel):
    series_id: str
    video_id: str
    title: str
    notes: list[VideoNoteResponse]

    @classmethod
    def from_view(cls, notes: VideoNotesView) -> "VideoNotesResponse":
        return cls(
            series_id=notes.series_id,
            video_id=notes.video_id,
            title=notes.title,
            notes=[VideoNoteResponse.from_view(note) for note in notes.notes],
        )


class AgentChatContextRequest(BaseModel):
    scope_type: str | None = None
    series_id: str | None = None
    series_title: str | None = None
    video_id: str | None = None
    video_title: str | None = None
    selected_tool: str | None = None


class AgentChatRequest(BaseModel):
    session_id: str
    message: str
    context: AgentChatContextRequest | None = None


class ToolExecutionResultResponse(BaseModel):
    tool_name: str
    status: str
    payload: dict[str, object]


class AgentChatResponse(BaseModel):
    assistant_message: str
    intent_type: str
    scope_type: str
    reason: str
    out_of_scope_reason: str
    tool_results: list[ToolExecutionResultResponse]

    @classmethod
    def from_result(cls, result: AgentTurnResult) -> "AgentChatResponse":
        return cls(
            assistant_message=result.assistant_message,
            intent_type=result.plan.intent_type.value,
            scope_type=result.plan.scope_type.value,
            reason=result.plan.reason,
            out_of_scope_reason=result.plan.out_of_scope_reason,
            tool_results=[
                ToolExecutionResultResponse(
                    tool_name=item.tool_name.value,
                    status=item.status,
                    payload=item.payload,
                )
                for item in result.tool_results
            ],
        )
