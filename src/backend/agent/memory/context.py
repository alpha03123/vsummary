"""Agent 单次会话的上下文快照。

`AgentContext` 是 Agent 在一次会话内使用的「目标工作区 + 工具可用性」
只读视图：由 `AgentContextLoader` 在每轮对话开始前构建，随消息历史
一起流入下游节点与用例，作为提示词渲染的输入之一。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolAvailability(BaseModel):
    """单条工作区工具制品的就绪状态。

    用于在提示词中告知 LLM「哪些制品可用 / 哪些尚未生成」，从而影响
    行动规划的决策（例如不可用时改用 RAG 兜底，而不是直接调用工具）。

    Attributes:
        available: 制品是否对用户可见（受界面开关、权限等控制）。
        generated: 制品是否已经成功生成并落盘。
        status: 工具当前生命周期状态（如 "idle" / "generating" /
            "error"），由实现方按需扩展。
    """

    available: bool = False
    generated: bool = False
    status: str = "idle"


class AgentContext(BaseModel):
    """一次 Agent 会话所绑定的目标工作区与工具状态快照。

    把「会话属于哪个 scope、关注哪个 series/video、用户当前选中了
    哪个工具」这类信息集中存放；`scope_type` 决定下游分支
    （`series` 走 RAG 检索，`video` 走工具调用）。

    该模型是 Pydantic BaseModel，构造后即可视为不可变的只读快照；
    实际更新由上层 `AgentSessionStore.append_turn` 在写入快照前
    重新拷贝。

    Attributes:
        session_id: 会话唯一 ID，与 `AgentSessionSnapshot.session_id`
            一致。
        workspace_title: 当前工作区的展示标题，供提示词渲染。
        scope_type: 会话作用域，取值 "series" 或 "video"；
            默认 "series" 是因为 series scope 是更轻的入口。
        series_id: series scope 下的目标系列 ID；非 series scope
            时若存在则为关联系列，否则为 `None`。
        series_title: 系列标题；`series_id` 为 `None` 时为 `None`。
        video_id: video scope 下的目标视频 ID；非 video scope
            时为 `None`。
        video_title: 视频标题；`video_id` 为 `None` 时为 `None`。
        selected_tool: 用户当前在工作区侧栏选中的工具名（用于
            在提示词中突出引导），未选中时为 `None`。
        overview: 系列概览制品的就绪状态。
        mindmap: 思维导图制品的就绪状态。
        knowledge_cards: 知识卡制品的就绪状态。
        notes: 笔记制品的就绪状态。
        preview: 视频预览制品的就绪状态。
        chapter_titles: 当前视频的章节标题列表；用于在提示词中
            提供轻量的目录索引。
    """

    session_id: str
    workspace_title: str = "Video Include"
    scope_type: str = "series"
    series_id: str | None = None
    series_title: str | None = None
    video_id: str | None = None
    video_title: str | None = None
    selected_tool: str | None = None
    overview: ToolAvailability = Field(default_factory=ToolAvailability)
    mindmap: ToolAvailability = Field(default_factory=ToolAvailability)
    knowledge_cards: ToolAvailability = Field(default_factory=ToolAvailability)
    notes: ToolAvailability = Field(default_factory=ToolAvailability)
    preview: ToolAvailability = Field(default_factory=ToolAvailability)
    chapter_titles: list[str] = Field(default_factory=list)
