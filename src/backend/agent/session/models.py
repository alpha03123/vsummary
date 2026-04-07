from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from backend.agent.memory.context import AgentContext


class AgentSessionMessageEntry(BaseModel):
    role: str
    content: str
    created_at: str


class AgentSessionSnapshot(BaseModel):
    session_id: str
    memory_key: str
    context: AgentContext
    messages: list[AgentSessionMessageEntry] = Field(default_factory=list)
    updated_at: str

    @property
    def message_count(self) -> int:
        return len(self.messages)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
