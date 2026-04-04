from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel
from backend.agent.memory.context import AgentContext
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult

StructuredResponseT = TypeVar("StructuredResponseT", bound=BaseModel)


class ChatGateway(Protocol):
    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
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


@dataclass(frozen=True)
class TranscriptLookupMatch:
    source: str
    text: str
    start_seconds: float
    end_seconds: float
    chapter_title: str | None = None
    score: float = 0.0


@dataclass(frozen=True)
class TranscriptLookupResult:
    query: str
    matches: list[TranscriptLookupMatch]

    @property
    def seek_seconds(self) -> float | None:
        if not self.matches:
            return None
        return self.matches[0].start_seconds


class AgentTranscriptLookup(Protocol):
    def lookup(self, context: AgentContext, query: str) -> TranscriptLookupResult:
        ...


class AgentToolExecutor(Protocol):
    def execute(self, plan: AgentActionPlan, context: AgentContext) -> list[ToolExecutionResult]:
        ...
