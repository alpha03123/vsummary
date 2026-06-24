"""API 响应模型集合。

把领域层的内部 DTO 转换为 Pydantic 响应模型，供 FastAPI 路由返回与
OpenAPI 文档自动生成。所有 ``from_model`` 类方法负责 DTO → Response 的映射。
"""

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
    """健康检查端点响应。"""

    status: str


class VideoCardResponse(BaseModel):
    """视频卡片在 API 层的展示模型。

    与 ``LibraryVideoCardDTO`` 一一映射，额外提供前端展示所需的默认值。
    """

    id: str
    title: str
    source_name: str
    source_type: str
    processed: bool
    status: str
    core_problem: str = ""
    is_linked: bool = False
    bilibili_bvid: str = ""
    bilibili_page: int = 0
    source_url: str = ""
    provider: str = ""

    @classmethod
    def from_model(cls, video: LibraryVideoCardDTO) -> "VideoCardResponse":
        """从 ``LibraryVideoCardDTO`` 构建 API 响应模型。

        Args:
            video: 库层的视频卡片 DTO。

        Returns:
            API 层的视频卡片响应。
        """
        return cls(
            id=video.id,
            title=video.title,
            source_name=video.source_name,
            source_type=video.source_type,
            processed=video.processed,
            status=video.status,
            core_problem=video.core_problem,
            is_linked=video.is_linked,
            bilibili_bvid=video.bilibili_bvid,
            bilibili_page=video.bilibili_page,
            source_url=video.source_url,
            provider=video.provider,
        )

class SeriesResponse(BaseModel):
    """系列的 API 响应模型。

    包含系列元数据及其全部子视频的卡片列表。
    """

    id: str
    title: str
    videos: list[VideoCardResponse]
    is_linked: bool
    source_url: str

    @classmethod
    def from_model(cls, series: LibrarySeriesDTO) -> "SeriesResponse":
        """从 ``LibrarySeriesDTO`` 构建 API 响应模型。

        Args:
            series: 库层的系列 DTO。

        Returns:
            API 层的系列响应，含所有子视频卡片。
        """
        return cls(
            id=series.id,
            title=series.title,
            videos=[VideoCardResponse.from_model(video) for video in series.videos],
            is_linked=series.is_linked,
            source_url=series.source_url,
        )

class WorkspaceResponse(BaseModel):
    """工作区的 API 响应模型。"""

    id: str
    title: str

    @classmethod
    def from_model(cls, workspace: WorkspaceDTO) -> "WorkspaceResponse":
        """从 ``WorkspaceDTO`` 构建 API 响应模型。

        Args:
            workspace: 库层的工作区 DTO。

        Returns:
            API 层的工作区响应。
        """
        return cls(id=workspace.id, title=workspace.title)


class VideoLibraryResponse(BaseModel):
    """整个视频库的 API 响应模型。

    同时返回工作区基本信息和所有系列（含子视频）。
    """

    workspace: WorkspaceResponse
    series: list[SeriesResponse]

    @classmethod
    def from_model(cls, library: VideoLibraryDTO) -> "VideoLibraryResponse":
        """从 ``VideoLibraryDTO`` 构建 API 响应模型。

        Args:
            library: 库层的视频库 DTO。

        Returns:
            API 层的完整视频库响应。
        """
        return cls(
            workspace=WorkspaceResponse.from_model(library.workspace),
            series=[SeriesResponse.from_model(series) for series in library.series],
        )


class WorkspaceToolResponse(BaseModel):
    """单个工作区工具的 API 响应模型。

    每个视频最多关联一个同类型工具（概览、知识卡、思维导图、笔记等）；
    ``available`` 表示工具可触发生成，``generated`` 表示制品已存在。
    """

    id: str
    title: str
    available: bool
    generated: bool
    status: str
    preview_url: str | None = None

    @classmethod
    def from_model(cls, tool: WorkspaceToolDTO) -> "WorkspaceToolResponse":
        """从 ``WorkspaceToolDTO`` 构建 API 响应模型。

        Args:
            tool: 库层的工具 DTO。

        Returns:
            API 层的工具响应。
        """
        return cls(
            id=tool.id,
            title=tool.title,
            available=tool.available,
            generated=tool.generated,
            status=tool.status,
            preview_url=tool.preview_url,
        )


class VideoWorkspaceToolsResponse(BaseModel):
    """视频工作区各工具状态的聚合响应。

    一次性返回概览、知识卡、思维导图、笔记、预览五个工具的状态，
    供前端渲染视频阅读面板的工具栏。
    """

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
        """从 ``VideoWorkspaceToolsDTO`` 构建 API 响应模型。

        Args:
            tools: 库层的视频工作区工具 DTO。

        Returns:
            API 层的工具集合响应。
        """
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
    """章节卡的 API 响应模型。

    一条章节卡对应视频中的一段连续时间区间；
    start_seconds/end_seconds 若为 None 表示无精确时间戳。
    """

    id: str
    title: str
    summary: str
    key_points: list[str]
    start_seconds: float | None = None
    end_seconds: float | None = None
    kind: str

    @classmethod
    def from_model(cls, card: ChapterCardDTO) -> "ChapterCardResponse":
        """从 ``ChapterCardDTO`` 构建 API 响应模型。

        Args:
            card: 库层的章节卡 DTO。

        Returns:
            API 层的章节卡响应。
        """
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
    """单个视频的章节卡集合响应。"""

    series_id: str
    video_id: str
    title: str
    cards: list[ChapterCardResponse]

    @classmethod
    def from_model(cls, cards: VideoChapterCardsDTO) -> "VideoChapterCardsResponse":
        """从 ``VideoChapterCardsDTO`` 构建 API 响应模型。

        Args:
            cards: 库层的章节卡集合 DTO。

        Returns:
            API 层的章节卡集合响应。
        """
        return cls(
            series_id=cards.series_id,
            video_id=cards.video_id,
            title=cards.title,
            cards=[ChapterCardResponse.from_model(card) for card in cards.cards],
        )


class KnowledgeCardResponse(BaseModel):
    """知识卡的 API 响应模型。

    每张知识卡提炼一个核心概念，包含摘要、标签、关键词及关联卡引用。
    """

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
        """从 ``KnowledgeCardDTO`` 构建 API 响应模型。

        Args:
            card: 库层的知识卡 DTO。

        Returns:
            API 层的知识卡响应。
        """
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
    """单个视频的知识卡集合响应。"""

    series_id: str
    video_id: str
    title: str
    cards: list[KnowledgeCardResponse]

    @classmethod
    def from_model(cls, cards: VideoKnowledgeCardsDTO) -> "VideoKnowledgeCardsResponse":
        """从 ``VideoKnowledgeCardsDTO`` 构建 API 响应模型。

        Args:
            cards: 库层的知识卡集合 DTO。

        Returns:
            API 层的知识卡集合响应。
        """
        return cls(
            series_id=cards.series_id,
            video_id=cards.video_id,
            title=cards.title,
            cards=[KnowledgeCardResponse.from_model(card) for card in cards.cards],
        )


class VideoNoteResponse(BaseModel):
    """视频笔记的 API 响应模型。

    笔记由"用户手写"与"AI 生成"两种来源共存，通过 source 字段区分。
    """

    id: str
    title: str
    content: str
    source: str
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, note: VideoNoteDTO) -> "VideoNoteResponse":
        """从 ``VideoNoteDTO`` 构建 API 响应模型。

        Args:
            note: 库层的笔记 DTO。

        Returns:
            API 层的笔记响应。
        """
        return cls(
            id=note.id,
            title=note.title,
            content=note.content,
            source=note.source,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )


class VideoNotesResponse(BaseModel):
    """单个视频的笔记集合响应。"""

    series_id: str
    video_id: str
    title: str
    notes: list[VideoNoteResponse]

    @classmethod
    def from_model(cls, notes: VideoNotesDTO) -> "VideoNotesResponse":
        """从 ``VideoNotesDTO`` 构建 API 响应模型。

        Args:
            notes: 库层的笔记集合 DTO。

        Returns:
            API 层的笔记集合响应。
        """
        return cls(
            series_id=notes.series_id,
            video_id=notes.video_id,
            title=notes.title,
            notes=[VideoNoteResponse.from_model(note) for note in notes.notes],
        )


class AgentChatContextRequest(BaseModel):
    """Agent 对话的上下文请求体。

    前端在发起对话前发送此请求，告知 Agent 当前用户在查看哪个系列/视频，
    以及选中的工具类型。所有字段均为可选，允许渐进式传递上下文。
    """

    scope_type: str | None = None
    series_id: str | None = None
    series_title: str | None = None
    video_id: str | None = None
    video_title: str | None = None
    selected_tool: str | None = None


class ResolveBilibiliSeriesRequest(BaseModel):
    """解析 Bilibili 合集/系列 URL 的请求体。"""

    url: str


class ResolveBilibiliVideoRequest(BaseModel):
    """解析 Bilibili 单视频 URL 的请求体。

    target_series_id 指定将视频添加到哪个系列；若为 None 则自动创建新系列。
    """

    url: str
    target_series_id: str | None = None


class LinkedVideoDownloadResponse(BaseModel):
    """链接视频下载启动的响应模型。

    返回 download task_id，前端通过 SSE 订阅下载进度。
    """

    status: str
    task_id: str

    @classmethod
    def started(cls, task_id: str) -> "LinkedVideoDownloadResponse":
        """构建"下载已启动"的快捷响应。

        Args:
            task_id: 下载任务 ID。

        Returns:
            status="started" 的响应实例。
        """
        return cls(status="started", task_id=task_id)


class AgentChatRequest(BaseModel):
    """Agent 对话的请求体。

    每次对话轮次包含 session_id 和 message，以及可选的上下文快照。
    """

    session_id: str
    message: str
    context: AgentChatContextRequest | None = None


class AgentContextUsageRequest(BaseModel):
    """查询 Agent 上下文用量预算的请求体。"""

    session_id: str
    context: AgentChatContextRequest | None = None


class AgentContextUsageSourceResponse(BaseModel):
    """上下文用量中各来源的细分响应。

    一个来源对应一份被注入 Agent 上下文的制品（如转写、总结、RAG 结果）。
    """

    id: str
    label: str
    estimated_tokens: int


class AgentContextUsageResponse(BaseModel):
    """Agent 上下文预算用量的完整响应模型。

    返回当前会话的 token 预算使用情况，包括总量、各阈值、使用百分比和级别。
    前端据此展示用量条并决定是否触发压缩/警告。
    """

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
    """历史对话消息的 API 响应模型。

    每条消息包含角色、内容、创建时间和引用列表。
    """

    role: str
    content: str
    created_at: str
    citations: list["CitationResponse"] = Field(default_factory=list)


class AgentSessionRecoveryRequest(BaseModel):
    """请求恢复历史对话会话。"""

    session_id: str
    context: AgentChatContextRequest | None = None


class AgentSessionRecoveryResponse(BaseModel):
    """会话恢复操作的响应模型。

    restored 为 True 表示找到历史会话并成功加载；为 False 表示无历史数据。
    """

    session_id: str
    restored: bool
    memory_key: str | None = None
    updated_at: str | None = None
    message_count: int = 0
    messages: list[AgentSessionMessageResponse] = Field(default_factory=list)


class AgentSessionClearRequest(BaseModel):
    """请求清空历史对话会话。

    清空后 session_id 仍然保留，但消息历史被移除。
    """

    session_id: str
    context: AgentChatContextRequest | None = None


class ToolExecutionResultResponse(BaseModel):
    """Agent 工具执行结果的 API 响应模型。

    每个工具执行完成后返回状态和业务负载，供前端渲染工具输出卡片。
    """

    tool_name: str
    status: str
    payload: dict[str, object]


class CitationSlotResponse(BaseModel):
    """引用槽位的 API 响应模型。

    一条引用可包含多个槽位（如多处文本证据），每个槽位指向一个具体来源
    （视频片段、URL 等）并附带候选片段列表供前端切换展示。
    """

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
        """从 ``CitationSlot`` 构建 API 响应模型。

        Args:
            slot: Agent 层的引用槽位。

        Returns:
            API 层的引用槽位响应，含候选片段列表。
        """
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
    """引用槽位中单个候选片段的响应模型。

    当检索返回多条可能相关的原文时，每个候选项包含时间戳和匹配文本。
    """

    start_seconds: float | None = None
    end_seconds: float | None = None
    text: str | None = None

    @classmethod
    def from_model(cls, candidate: CitationSlotCandidate) -> "CitationSlotCandidateResponse":
        """从 ``CitationSlotCandidate`` 构建 API 响应模型。

        Args:
            candidate: Agent 层的引用候选片段。

        Returns:
            API 层的候选片段响应。
        """
        return cls(**candidate.model_dump(mode="json"))


class CitationResponse(BaseModel):
    """完整引用的 API 响应模型。

    每条引用标注了回答中引用的证据来源，包含来源类型、检索范围和槽位列表。
    """

    id: str
    label: str
    source_type: str
    search_scope: str
    slots: list[CitationSlotResponse]

    @classmethod
    def from_model(cls, citation: CitationReference) -> "CitationResponse":
        """从 ``CitationReference`` 构建 API 响应模型。

        Args:
            citation: Agent 层的引用参考。

        Returns:
            API 层的引用响应，含所有槽位。
        """
        return cls(
            id=citation.id,
            label=citation.label,
            source_type=citation.source_type,
            search_scope=citation.search_scope,
            slots=[CitationSlotResponse.from_model(slot) for slot in citation.slots],
        )


class AgentChatResponse(BaseModel):
    """Agent 对话的最终响应模型。

    将内部的 ``AgentTurnResult`` 转换为 Pydantic 兼容结构，包含助手回答、
    作用域类型、规划理由、工具执行结果和引用列表，供前端一次性反序列化。
    """

    assistant_message: str
    scope_type: str
    reason: str
    tool_results: list[ToolExecutionResultResponse]
    citations: list[CitationResponse] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: AgentTurnResult) -> "AgentChatResponse":
        """从 ``AgentTurnResult`` 构建 API 响应模型。

        Args:
            result: LangGraph 完成一轮对话后的完整结果。

        Returns:
            API 层的对话响应，已完成 DTO 映射。
        """
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
