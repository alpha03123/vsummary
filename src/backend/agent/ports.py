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
    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        ...

    def create_text_completion_stream(self, messages: list[AgentChatMessage]) -> Iterator[str]:
        ...

    def create_text_completion_stream_with_metadata(
        self,
        messages: list[AgentChatMessage],
    ) -> Iterator[ChatCompletionStreamChunk]:
        ...

    def create_structured_completion(
        self,
        messages: list[AgentChatMessage],
        response_model: type[StructuredResponseT],
    ) -> StructuredResponseT:
        ...


class AgentContextLoader(Protocol):
    def load(self, session_id: str) -> AgentContext:
        ...

class AgentToolExecutor(Protocol):
    def execute(self, plan: AgentActionPlan, context: AgentContext) -> list[ToolExecutionResult]:
        ...

    def execute_call(self, call: ToolCall, context: AgentContext) -> ToolExecutionResult:
        ...


class AgentSessionStore(Protocol):
    def get_snapshot(self, session_id: str) -> AgentSessionSnapshot | None:
        ...

    def append_turn(
        self,
        *,
        session_id: str,
        memory_key: str,
        context: AgentContext,
        user_message: str,
        assistant_message: str,
        tool_results: list[ToolExecutionResult],
    ) -> None:
        ...

    def clear_snapshot(self, session_id: str) -> None:
        ...
