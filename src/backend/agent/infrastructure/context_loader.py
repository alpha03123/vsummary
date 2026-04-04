from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentContextLoader


class StaticAgentContextLoader:
    def __init__(self, context: AgentContext) -> None:
        self._context = context

    def load(self, session_id: str) -> AgentContext:
        if self._context.session_id == session_id:
            return self._context
        return self._context.model_copy(update={"session_id": session_id})
