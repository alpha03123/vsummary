"""Agent 可调用的工具集合：工具枚举、调用载荷、执行结果。

业务意图：LLM 一次决策可能产出"调用工具 / 不调用工具"两种分支。本模块
把所有可调用工具以 `Enum` 形式集中声明，并把每种工具的参数定义成一个
Pydantic 模型；用 Pydantic 的 `Annotated` + `discriminator` 把它们聚合为
`ToolCall` 联合类型，供 `ActionPlan` 等上层结构直接消费。
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ToolName(str, Enum):
    """Agent 可调用的所有工具的"标识 + 字符串值"映射。

    字符串值与下游执行器（`AgentToolExecutor`）的派发键保持一致；
    添加新工具时需同时更新 `ToolDefinition` 表、对应 `*Call` 模型和
    `ToolCall` 联合类型。
    """

    LIST_SERIES_VIDEOS = "list_series_videos"
    GET_VIDEO_SUMMARY = "get_video_summary"
    GET_VIDEO_TOOLS = "get_video_tools"
    GET_VIDEO_TRANSCRIPT = "get_video_transcript"
    OPEN_SERIES_HOME = "open_series_home"
    OPEN_SERIES_OVERVIEW = "open_series_overview"
    OPEN_OVERVIEW = "open_overview"
    OPEN_MINDMAP = "open_mindmap"
    OPEN_KNOWLEDGE_CARDS = "open_knowledge_cards"
    OPEN_NOTES = "open_notes"
    OPEN_VIDEO = "open_video"
    VIDEO_SEEK = "video_seek"
    GENERATE_OVERVIEW = "generate_overview"
    GENERATE_MINDMAP = "generate_mindmap"
    SAVE_NOTE = "save_note"


class ToolContextTag(str, Enum):
    """工具可被调用的目标范围标签，用于前端与执行器做上下文校验。

    Attributes:
        SERIES: 工具只能在 `scope_type=series` 时被调用。
        VIDEO: 工具只能在 `scope_type=video` 时被调用。
    """

    SERIES = "series"
    VIDEO = "video"


class ToolPlane(str, Enum):
    """工具的"执行平面"，决定其对前端的影响方式。

    Attributes:
        BUSINESS_READ: 业务读取类工具，结果会作为证据参与最终答案。
        UI_ACTION: 前端交互类工具，结果是"通知前端打开某个视图/跳转到某个时间点"。
    """

    BUSINESS_READ = "business_read"
    UI_ACTION = "ui_action"


class ToolDefinition(BaseModel):
    """一个工具的元数据（供规划器提示词与前端 UI 使用）。

    Attributes:
        name: 工具枚举名。
        title: 人类可读的中文/英文短名。
        description: 工具功能描述，用于拼装 LLM 提示词。
        plane: 工具所属的执行平面（业务读取 / 前端交互）。
        arguments: 工具参数说明字典，键为参数名、值为参数说明文本。
        contexts: 工具可被调用的目标范围标签集合。
    """

    name: ToolName
    title: str
    description: str
    plane: ToolPlane
    arguments: dict[str, str] = Field(default_factory=dict)
    contexts: tuple[ToolContextTag, ...] = ()


class ListSeriesVideosCall(BaseModel):
    """`list_series_videos` 工具的调用载荷：列出某系列下的所有视频卡片。"""

    tool_name: Literal[ToolName.LIST_SERIES_VIDEOS] = ToolName.LIST_SERIES_VIDEOS
    series_id: str | None = None


class GetVideoSummaryCall(BaseModel):
    """`get_video_summary` 工具的调用载荷：取指定视频的结构化总结。"""

    tool_name: Literal[ToolName.GET_VIDEO_SUMMARY] = ToolName.GET_VIDEO_SUMMARY
    series_id: str | None = None
    video_id: str | None = None


class GetVideoToolsCall(BaseModel):
    """`get_video_tools` 工具的调用载荷：取视频工作区工具栏的完整状态。"""

    tool_name: Literal[ToolName.GET_VIDEO_TOOLS] = ToolName.GET_VIDEO_TOOLS
    series_id: str | None = None
    video_id: str | None = None


class GetVideoTranscriptCall(BaseModel):
    """`get_video_transcript` 工具的调用载荷：取视频的转写文本。"""

    tool_name: Literal[ToolName.GET_VIDEO_TRANSCRIPT] = ToolName.GET_VIDEO_TRANSCRIPT
    series_id: str | None = None
    video_id: str | None = None


class OpenSeriesHomeCall(BaseModel):
    """`open_series_home` 工具的调用载荷：通知前端跳转到系列首页。"""

    tool_name: Literal[ToolName.OPEN_SERIES_HOME] = ToolName.OPEN_SERIES_HOME


class OpenSeriesOverviewCall(BaseModel):
    """`open_series_overview` 工具的调用载荷：通知前端打开系列概览视图。"""

    tool_name: Literal[ToolName.OPEN_SERIES_OVERVIEW] = ToolName.OPEN_SERIES_OVERVIEW


class OpenOverviewCall(BaseModel):
    """`open_overview` 工具的调用载荷：通知前端打开当前视频概览。"""

    tool_name: Literal[ToolName.OPEN_OVERVIEW] = ToolName.OPEN_OVERVIEW


class OpenMindmapCall(BaseModel):
    """`open_mindmap` 工具的调用载荷：通知前端打开思维导图。"""

    tool_name: Literal[ToolName.OPEN_MINDMAP] = ToolName.OPEN_MINDMAP


class OpenKnowledgeCardsCall(BaseModel):
    """`open_knowledge_cards` 工具的调用载荷：通知前端打开知识卡视图。"""

    tool_name: Literal[ToolName.OPEN_KNOWLEDGE_CARDS] = ToolName.OPEN_KNOWLEDGE_CARDS


class OpenVideoCall(BaseModel):
    """`open_video` 工具的调用载荷：通知前端打开指定视频。"""

    tool_name: Literal[ToolName.OPEN_VIDEO] = ToolName.OPEN_VIDEO


class OpenNotesCall(BaseModel):
    """`open_notes` 工具的调用载荷：通知前端打开笔记视图。"""

    tool_name: Literal[ToolName.OPEN_NOTES] = ToolName.OPEN_NOTES


class VideoSeekCall(BaseModel):
    """`video_seek` 工具的调用载荷：让前端把视频跳转到指定时间点。

    Attributes:
        seek_seconds: 跳转到视频内的目标时间（秒）。
        match_end_seconds: 若引用来自一段匹配文本，标记该段的结束时间。
        matched_text: 命中的转写文本（用于前端在播放时高亮）。
        chapter_title: 该跳转所属的章节标题，便于前端展示。
        query: 触发跳转的原始查询词，便于回放/调试。
    """

    tool_name: Literal[ToolName.VIDEO_SEEK] = ToolName.VIDEO_SEEK
    seek_seconds: float
    match_end_seconds: float | None = None
    matched_text: str = ""
    chapter_title: str = ""
    query: str = ""


class GenerateOverviewCall(BaseModel):
    """`generate_overview` 工具的调用载荷：触发视频概览/总结的异步生成。"""

    tool_name: Literal[ToolName.GENERATE_OVERVIEW] = ToolName.GENERATE_OVERVIEW


class GenerateMindmapCall(BaseModel):
    """`generate_mindmap` 工具的调用载荷：触发视频思维导图的异步生成。"""

    tool_name: Literal[ToolName.GENERATE_MINDMAP] = ToolName.GENERATE_MINDMAP


class SaveNoteCall(BaseModel):
    """`save_note` 工具的调用载荷：把一段笔记持久化到当前视频。

    Attributes:
        note_title: 笔记标题。
        note_content: 笔记正文（Markdown）。
    """

    tool_name: Literal[ToolName.SAVE_NOTE] = ToolName.SAVE_NOTE
    note_title: str
    note_content: str


ToolCall = Annotated[
    ListSeriesVideosCall
    | GetVideoSummaryCall
    | GetVideoToolsCall
    | GetVideoTranscriptCall
    | OpenSeriesHomeCall
    | OpenSeriesOverviewCall
    | OpenOverviewCall
    | OpenMindmapCall
    | OpenKnowledgeCardsCall
    | OpenNotesCall
    | OpenVideoCall
    | VideoSeekCall
    | GenerateOverviewCall
    | GenerateMindmapCall
    | SaveNoteCall,
    Field(discriminator="tool_name"),
]


class ToolExecutionResult(BaseModel):
    """工具执行后的统一结果包装，供执行器返回给 Agent 节点。

    Attributes:
        tool_name: 实际执行的工具枚举名。
        status: 执行状态字符串（如 `ok` / `error` / `not_found`），由执行器自定义。
        payload: 与工具相关的负载字典；具体键值由各工具自行约定。
    """

    tool_name: ToolName
    status: str
    payload: dict[str, object] = Field(default_factory=dict)
