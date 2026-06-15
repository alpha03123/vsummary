"""Agent 一次回合的"动作规划 / 引用 / 结果"相关 Pydantic 模型。

本模块只描述"规划与产出"的形状，不规定如何生成：上游 `SeriesQueryProcessor`、
`VideoActionPlanner` 各自负责把 LLM 输出解析为这些结构，下游节点再依次执行。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult


class ScopeType(str, Enum):
    """Agent 当前回合所作用的目标范围。

    Attributes:
        SERIES: 系列级，回答会跨多视频检索。
        VIDEO: 单视频级，回答只针对当前打开的视频。
    """

    SERIES = "series"
    VIDEO = "video"


class AgentActionPlan(BaseModel):
    """一次 LLM 决策产出的"动作规划"。

    Attributes:
        scope_type: 本回合的目标范围（系列 / 单视频）。
        tool_calls: 在生成最终答案前需要先执行的工具调用列表。
        reason: 决策理由说明，供前端调试面板与日志回放使用。
        use_answerer: 是否直接走最终 answerer 节点；为 `True` 时跳过工具执行。
    """

    scope_type: ScopeType
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reason: str = ""
    use_answerer: bool = False


class CitationSlot(BaseModel):
    """一个引用位（出现在答案文本中时用 `[N]` 引用）。

    Attributes:
        slot: 引用编号（从 1 开始，与文本中的 `[slot]` 占位符一一对应）。
        target_type: 引用的目标类型（章节 / 笔记 / 知识卡等，由使用方自定义）。
        series_id: 所属系列 ID；非视频相关引用时可为 `None`。
        video_id: 所属视频 ID；非视频相关引用时可为 `None`。
        video_title: 视频标题，仅用于前端展示。
        chapter_id: 引用的章节 ID（若引用来自章节卡）。
        start_seconds / end_seconds: 引用片段在原视频中的时间区间。
        text: 引用的文本片段（用于在前端 tooltip 展示）。
        url: 引用对应的外链 URL（外部引用时使用）。
        candidates: 当引用来自检索召回时，可附带备选候选。
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
    candidates: list["CitationSlotCandidate"] = Field(default_factory=list)


class CitationSlotCandidate(BaseModel):
    """一个引用位的备选候选（供前端做"切换证据"交互）。"""

    start_seconds: float | None = None
    end_seconds: float | None = None
    text: str | None = None


class CitationReference(BaseModel):
    """一组按"来源"聚合的引用列表。

    Attributes:
        id: 来源唯一 ID（多用于前端 key）。
        label: 人类可读的来源标签（视频标题、章节标题等）。
        source_type: 来源类型（`video` / `chapter` / `note` / `external` 等）。
        search_scope: 该引用所属的检索范围（`series` / `video`）。
        slots: 属于该来源的所有引用位。
    """

    id: str
    label: str
    source_type: str
    search_scope: str
    slots: list[CitationSlot] = Field(default_factory=list)


class AgentTurnResult(BaseModel):
    """一轮 Agent 执行的最终结果（供前端消费）。

    Attributes:
        assistant_message: 最终要展示给用户的答案文本（已替换好 `[N]` 引用占位符）。
        plan: 本次回合的"动作规划"（`AgentActionPlan`）。
        tool_results: 本次回合执行过的工具调用结果，按执行顺序排列。
        citations: 本次回合使用的所有引用，按来源聚合。
    """

    assistant_message: str
    plan: AgentActionPlan
    tool_results: list[ToolExecutionResult] = Field(default_factory=list)
    citations: list[CitationReference] = Field(default_factory=list)
