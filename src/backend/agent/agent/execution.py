from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.ports import AgentToolExecutor
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult, ToolName
from backend.agent.tools import tool_is_available_in_context, tool_requires_candidate_buffer
from backend.agent.validation.errors import AgentPlanError


ToolHandler = Callable[[ToolCall, AgentContext], ToolExecutionResult]


@dataclass(frozen=True)
class RegistryAgentToolExecutor(AgentToolExecutor):
    registry: dict[ToolName, ToolHandler]

    def execute(self, plan: AgentActionPlan, context: AgentContext) -> list[ToolExecutionResult]:
        return [self.execute_call(call, context) for call in plan.tool_calls]

    def execute_call(self, call: ToolCall, context: AgentContext) -> ToolExecutionResult:
        _guard_call_against_context(call, context)
        handler = self.registry.get(call.tool_name)
        if handler is None:
            raise AgentPlanError(f"Unsupported tool_name: {call.tool_name.value}")
        return handler(call, context)


def _guard_call_against_context(call: ToolCall, context: AgentContext) -> None:
    if not tool_is_available_in_context(call.tool_name, context):
        current_stage = context.scope_type if context.scope_type == "video" else context.inspection_stage.value
        raise AgentPlanError(f"{current_stage} 阶段不能直接执行 {call.tool_name.value}。")
    if context.scope_type == "video":
        return
    if context.inspection_stage == InspectionStage.SERIES_DISCOVERY:
        return
    if context.candidate_buffer and tool_requires_candidate_buffer(call.tool_name):
        candidate_ids = {item.video_id for item in context.candidate_buffer}
        video_id = getattr(call, "video_id", None)
        if video_id is None or video_id not in candidate_ids:
            raise AgentPlanError(f"{call.tool_name.value} 只能作用于当前候选缓冲区中的视频。")
