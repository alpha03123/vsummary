"""Agent 一次回合的"动作规划 / 引用 / 结果"相关 Pydantic 模型。

本模块只描述"规划与产出"的形状，不规定如何生成：上游 `SeriesQueryProcessor`、
`VideoActionPlanner` 各自负责把 LLM 输出解析为这些结构，下游节点再依次执行。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult
from backend.core.citations import CitationReference, CitationSlot, CitationSlotCandidate


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
