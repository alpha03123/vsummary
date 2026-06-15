"""Agent 核心的 Protocol 端口集合。

把 Agent 与外部依赖之间的边界以 Protocol 类型声明：
- `ChatGateway`：与 LLM 交互的网关
- `AgentContextLoader`：按会话加载上下文
- `AgentToolExecutor`：执行 LLM 规划出的工具调用
- `AgentSessionStore`：会话历史的持久化与读取

具体实现位于 `backend.agent.infrastructure` 与
`backend.video_summary.infrastructure`，本模块不依赖任何具体实现，
便于在测试中替换。
"""

from __future__ import annotations

from typing import Iterator, Protocol, TypeVar

from pydantic import BaseModel
from backend.agent.memory.context import AgentContext
from backend.agent.schemas.chat_stream import ChatCompletionStreamChunk
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.session.models import AgentSessionSnapshot
from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult

StructuredResponseT = TypeVar("StructuredResponseT", bound=BaseModel)


class ChatGateway(Protocol):
    """与 LLM 交互的统一网关。

    把所有「调用 LLM」的动作收口到这一接口上，便于在 Agent 用例
    内注入不同实现（LiteLLM、mock、测试桩等），并集中处理流式
    输出与结构化输出协议协商。
    """

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        """同步发起一次文本补全，返回完整字符串。"""

    def create_text_completion_stream(self, messages: list[AgentChatMessage]) -> Iterator[str]:
        """以流式增量方式逐分片返回文本补全结果。"""

    def create_text_completion_stream_with_metadata(
        self,
        messages: list[AgentChatMessage],
    ) -> Iterator[ChatCompletionStreamChunk]:
        """以流式增量方式返回带元数据的文本分片（用于 SSE）。"""

    def create_structured_completion(
        self,
        messages: list[AgentChatMessage],
        response_model: type[StructuredResponseT],
    ) -> StructuredResponseT:
        """按 `response_model` 的 schema 发起结构化补全，返回校验后的实例。"""


class AgentContextLoader(Protocol):
    """按 `session_id` 加载 `AgentContext` 的端口。

    实现方负责从工作区状态（库、视频制品等）拼出一次 Agent 会话
    所需要的目标上下文；返回的 `AgentContext` 视为只读快照。
    """

    def load(self, session_id: str) -> AgentContext:
        """返回与 `session_id` 绑定的目标工作区上下文快照。"""


class AgentToolExecutor(Protocol):
    """执行 LLM 规划出的工具调用的端口。

    把 `AgentActionPlan`（多个 `ToolCall`）按业务规则真正落到具体
    的视频/库操作上，并把每个调用的结果汇总返回，供 LLM 在下一
    轮综合所有结果再合成答案。
    """

    def execute(self, plan: AgentActionPlan, context: AgentContext) -> list[ToolExecutionResult]:
        """按 `plan` 串行/并行执行所有工具调用，返回每个调用的结果列表。"""

    def execute_call(self, call: ToolCall, context: AgentContext) -> ToolExecutionResult:
        """执行单个工具调用；用于更细粒度的控制（如计划重试、错误隔离）。"""


class AgentSessionStore(Protocol):
    """Agent 会话历史的持久化端口。

    用例通过 `append_turn` 写入一整轮对话后的快照，通过
    `get_snapshot` 恢复历史；`clear_snapshot` 用于用户主动重置会话。
    实现可以是文件、Redis、SQL 等任意后端。
    """

    def get_snapshot(self, session_id: str) -> AgentSessionSnapshot | None:
        """取指定会话的完整快照；不存在时返回 `None`。"""

    def append_turn(
        self,
        *,
        session_id: str,
        memory_key: str,
        context: AgentContext,
        messages: list[AgentChatMessage],
    ) -> None:
        """把一轮对话（含本轮问答与最新上下文）整体写入会话快照。"""

    def clear_snapshot(self, session_id: str) -> None:
        """清空指定会话的快照。"""
