from __future__ import annotations

from pydantic import BaseModel, Field

from backend.agent.schemas.action_plan import AgentTurnResult, CitationReference, CitationSlot, CitationSlotCandidate
from backend.video_summary.library.models import (
    ChapterCardDTO,
    KnowledgeCardDTO,
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
    VideoChapterCardsDTO,
    VideoKnowledgeCardsDTO,
    VideoLibraryDTO,
    VideoNoteDTO,
    VideoNotesDTO,
    VideoWorkspaceToolsDTO,
    WorkspaceDTO,
    WorkspaceToolDTO,
)


class HealthResponse(BaseModel):
    status: str


class VideoCardResponse(BaseModel):
    id: str
    title: str
    source_name: str
    processed: bool
    status: str
    is_linked: bool = False
    bilibili_bvid: str = ""
    bilibili_page: int = 0
    source_url: str = ""
    provider: str = ""

    @classmethod
    def from_model(cls, video: LibraryVideoCardDTO) -> "VideoCardResponse":
        return cls(
            id=video.id,
            title=video.title,
            source_name=video.source_name,
            processed=video.processed,
            status=video.status,
            is_linked=video.is_linked,
            bilibili_bvid=video.bilibili_bvid,
            bilibili_page=video.bilibili_page,
            source_url=video.source_url,
            provider=video.provider,
        )

class SeriesResponse(BaseModel):
    id: str
    title: str
    videos: list[VideoCardResponse]
    is_linked: bool
    source_url: str

    @classmethod
    def from_model(cls, series: LibrarySeriesDTO) -> "SeriesResponse":
        return cls(
            id=series.id,
            title=series.title,
            videos=[VideoCardResponse.from_model(video) for video in series.videos],
            is_linked=series.is_linked,
            source_url=series.source_url,
        )

class WorkspaceResponse(BaseModel):
    id: str
    title: str

    @classmethod
    def from_model(cls, workspace: WorkspaceDTO) -> "WorkspaceResponse":
        return cls(id=workspace.id, title=workspace.title)


class VideoLibraryResponse(BaseModel):
    workspace: WorkspaceResponse
    series: list[SeriesResponse]

    @classmethod
    def from_model(cls, library: VideoLibraryDTO) -> "VideoLibraryResponse":
        return cls(
            workspace=WorkspaceResponse.from_model(library.workspace),
            series=[SeriesResponse.from_model(series) for series in library.series],
        )


class WorkspaceToolResponse(BaseModel):
    id: str
    title: str
    available: bool
    generated: bool
    status: str
    preview_url: str | None = None

    @classmethod
    def from_model(cls, tool: WorkspaceToolDTO) -> "WorkspaceToolResponse":
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
    def from_model(cls, tools: VideoWorkspaceToolsDTO) -> "VideoWorkspaceToolsResponse":
        return cls(
            series_id=tools.series_id,
            video_id=tools.video_id,
            overview=WorkspaceToolResponse.from_model(tools.overview),
            knowledge_cards=WorkspaceToolResponse.from_model(tools.knowledge_cards),
            mindmap=WorkspaceToolResponse.from_model(tools.mindmap),
            notes=WorkspaceToolResponse.from_model(tools.notes),
            preview=WorkspaceToolResponse.from_model(tools.preview),
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
    def from_model(cls, card: ChapterCardDTO) -> "ChapterCardResponse":
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
    def from_model(cls, cards: VideoChapterCardsDTO) -> "VideoChapterCardsResponse":
        return cls(
            series_id=cards.series_id,
            video_id=cards.video_id,
            title=cards.title,
            cards=[ChapterCardResponse.from_model(card) for card in cards.cards],
        )


class KnowledgeCardResponse(BaseModel):
    id: str
    title: str
    kind: str
    summary: str
    details: str
    tags: list[str]
    keywords: list[str]
    related_card_ids: list[str]

    @classmethod
    def from_model(cls, card: KnowledgeCardDTO) -> "KnowledgeCardResponse":
        return cls(
            id=card.id,
            title=card.title,
            kind=card.kind,
            summary=card.summary,
            details=card.details,
            tags=card.tags,
            keywords=card.keywords,
            related_card_ids=card.related_card_ids,
        )


class VideoKnowledgeCardsResponse(BaseModel):
    series_id: str
    video_id: str
    title: str
    cards: list[KnowledgeCardResponse]

    @classmethod
    def from_model(cls, cards: VideoKnowledgeCardsDTO) -> "VideoKnowledgeCardsResponse":
        return cls(
            series_id=cards.series_id,
            video_id=cards.video_id,
            title=cards.title,
            cards=[KnowledgeCardResponse.from_model(card) for card in cards.cards],
        )


class VideoNoteResponse(BaseModel):
    id: str
    title: str
    content: str
    source: str
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, note: VideoNoteDTO) -> "VideoNoteResponse":
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
    def from_model(cls, notes: VideoNotesDTO) -> "VideoNotesResponse":
        return cls(
            series_id=notes.series_id,
            video_id=notes.video_id,
            title=notes.title,
            notes=[VideoNoteResponse.from_model(note) for note in notes.notes],
        )


class AgentChatContextRequest(BaseModel):
    scope_type: str | None = None
    series_id: str | None = None
    series_title: str | None = None
    video_id: str | None = None
    video_title: str | None = None
    selected_tool: str | None = None


class ResolveBilibiliSeriesRequest(BaseModel):
    url: str


class ResolveBilibiliVideoRequest(BaseModel):
    url: str
    target_series_id: str | None = None


class LinkedVideoDownloadResponse(BaseModel):
    status: str
    task_id: str

    @classmethod
    def started(cls, task_id: str) -> "LinkedVideoDownloadResponse":
        return cls(status="started", task_id=task_id)


class AgentChatRequest(BaseModel):
    session_id: str
    message: str
    context: AgentChatContextRequest | None = None


class AgentContextUsageRequest(BaseModel):
    session_id: str
    context: AgentChatContextRequest | None = None


class AgentContextUsageSourceResponse(BaseModel):
    id: str
    label: str
    estimated_tokens: int


class AgentContextUsageResponse(BaseModel):
    session_id: str
    scope_type: str
    memory_key: str
    estimated_total_tokens: int
    window_tokens: int
    reserved_output_tokens: int
    warning_threshold_tokens: int
    compact_threshold_tokens: int
    blocking_threshold_tokens: int
    remaining_tokens: int
    usage_percent: float
    level: str
    sources: list[AgentContextUsageSourceResponse]


class AgentSessionMessageResponse(BaseModel):
    role: str
    content: str
    created_at: str
    citations: list["CitationResponse"] = Field(default_factory=list)


class AgentSessionRecoveryRequest(BaseModel):
    session_id: str
    context: AgentChatContextRequest | None = None


class AgentSessionRecoveryResponse(BaseModel):
    session_id: str
    restored: bool
    memory_key: str | None = None
    updated_at: str | None = None
    message_count: int = 0
    messages: list[AgentSessionMessageResponse] = Field(default_factory=list)


class AgentSessionClearRequest(BaseModel):
    session_id: str
    context: AgentChatContextRequest | None = None


class ToolExecutionResultResponse(BaseModel):
    tool_name: str
    status: str
    payload: dict[str, object]


class CitationSlotResponse(BaseModel):
    slot: int
    target_type: str
    series_id: str | None = None
    video_id: str | None = None
    video_title: str | None = None
    chapter_id: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    text: str | None = None
    url: str | None = None
    candidates: list["CitationSlotCandidateResponse"] = Field(default_factory=list)

    @classmethod
    def from_model(cls, slot: CitationSlot) -> "CitationSlotResponse":
        return cls(
            slot=slot.slot,
            target_type=slot.target_type,
            series_id=slot.series_id,
            video_id=slot.video_id,
            video_title=slot.video_title,
            chapter_id=slot.chapter_id,
            start_seconds=slot.start_seconds,
            end_seconds=slot.end_seconds,
            text=slot.text,
            url=slot.url,
            candidates=[CitationSlotCandidateResponse.from_model(item) for item in slot.candidates],
        )


class CitationSlotCandidateResponse(BaseModel):
    start_seconds: float | None = None
    end_seconds: float | None = None
    text: str | None = None

    @classmethod
    def from_model(cls, candidate: CitationSlotCandidate) -> "CitationSlotCandidateResponse":
        return cls(**candidate.model_dump(mode="json"))


class CitationResponse(BaseModel):
    id: str
    label: str
    source_type: str
    search_scope: str
    slots: list[CitationSlotResponse]

    @classmethod
    def from_model(cls, citation: CitationReference) -> "CitationResponse":
        return cls(
            id=citation.id,
            label=citation.label,
            source_type=citation.source_type,
            search_scope=citation.search_scope,
            slots=[CitationSlotResponse.from_model(slot) for slot in citation.slots],
        )


class AgentChatResponse(BaseModel):
    assistant_message: str
    scope_type: str
    reason: str
    tool_results: list[ToolExecutionResultResponse]
    citations: list[CitationResponse] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: AgentTurnResult) -> "AgentChatResponse":
        return cls(
            assistant_message=result.assistant_message,
            scope_type=result.plan.scope_type.value,
            reason=result.plan.reason,
            tool_results=[
                ToolExecutionResultResponse(
                    tool_name=item.tool_name.value,
                    status=item.status,
                    payload=item.payload,
                )
                for item in result.tool_results
            ],
            citations=[CitationResponse.from_model(item) for item in result.citations],
        )
