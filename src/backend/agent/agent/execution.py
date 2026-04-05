from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentToolExecutor
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult, ToolName
from backend.agent.validation.errors import AgentPlanError


ToolHandler = Callable[[ToolCall, AgentContext], ToolExecutionResult]


@dataclass(frozen=True)
class RegistryAgentToolExecutor(AgentToolExecutor):
    registry: dict[ToolName, ToolHandler]

    def execute(self, plan: AgentActionPlan, context: AgentContext) -> list[ToolExecutionResult]:
        return [self.execute_call(call, context) for call in plan.tool_calls]

    def execute_call(self, call: ToolCall, context: AgentContext) -> ToolExecutionResult:
        handler = self.registry.get(call.tool_name)
        if handler is None:
            raise AgentPlanError(f"Unsupported tool_name: {call.tool_name.value}")
        return handler(call, context)
