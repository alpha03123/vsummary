"""Agent 流式输出到前端的统一事件包装。

业务意图：前端通过 SSE 订阅 Agent 一次回合的增量事件（文本分片、工具调用、
引用、状态等）；为了让一条事件既能携带类型又能携带任意负载，本模块把
事件定义为「`type` + `payload`」的最小公约数结构。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentStreamEvent(BaseModel):
    """一条 Agent 视角的流式事件。

    Attributes:
        type: 事件类型（具体取值由各 LangGraph 节点定义，例如
            `text_delta` / `tool_call` / `citation` / `done`）。
        payload: 与 `type` 对应的负载字典；具体键值约定由事件类型决定，
            本模型不做约束，以最大化兼容不同节点的扩展需求。
    """

    type: str
    payload: dict[str, object] = Field(default_factory=dict)
