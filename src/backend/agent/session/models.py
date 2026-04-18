from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import ToolExecutionResult


class AgentSessionMessageEntry(BaseModel):
    role: str
    content: str
    created_at: str


class AgentSessionEvidenceEntry(BaseModel):
    cache_key: str
    tool_result: ToolExecutionResult
    updated_at: str


class AgentSessionSelectedVideoEntry(BaseModel):
    video_id: str
    reason_for_selection: str = ""


class AgentSessionSnapshot(BaseModel):
    session_id: str
    memory_key: str
    context: AgentContext
    messages: list[AgentSessionMessageEntry] = Field(default_factory=list)
    evidence_entries: list[AgentSessionEvidenceEntry] = Field(default_factory=list)
    selected_videos: list[AgentSessionSelectedVideoEntry] = Field(default_factory=list)
    updated_at: str

    @property
    def message_count(self) -> int:
        return len(self.messages)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
