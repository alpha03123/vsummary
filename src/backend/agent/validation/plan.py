from __future__ import annotations

from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName
from backend.agent.tools import (
    list_model_visible_tool_definitions_for_context,
    tool_is_available_in_context,
    tool_requires_candidate_buffer,
    tool_requires_video_id,
)
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.shared import validate_batch_tool_usage, validate_tool_call_arguments


def validate_action_plan(
    plan: AgentActionPlan,
    context: AgentContext,
    observed_tool_results: list[ToolExecutionResult] | None = None,
) -> AgentActionPlan:
    resolved_tool_results = observed_tool_results or []
    _validate_response_mode(plan)
    validate_batch_tool_usage(plan)
    validate_tool_call_arguments(plan)
    _validate_plan_against_context(plan, context)
    _validate_plan_against_observations(plan, context, resolved_tool_results)
    return plan


def _validate_response_mode(plan: AgentActionPlan) -> None:
    enabled_modes = sum(
        (
            1 if plan.tool_calls else 0,
            1 if plan.direct_response.strip() else 0,
            1 if plan.use_answerer else 0,
        )
    )
    if enabled_modes != 1:
        raise AgentPlanError("plan 必须且只能选择一种执行模式：tool_calls、direct_response、use_answerer。")


def _validate_plan_against_observations(
    plan: AgentActionPlan,
    context: AgentContext,
    observed_tool_results: list[ToolExecutionResult],
) -> None:
    valid_video_ids = _extract_listed_video_ids(observed_tool_results)
    if not valid_video_ids or context.candidate_buffer:
        return

    for call in plan.tool_calls:
        if not tool_requires_video_id(call.tool_name):
            continue
        video_id = getattr(call, "video_id", None)
        if video_id is None:
            continue
        if video_id not in valid_video_ids:
            raise AgentPlanError(
                (
                    f"{call.tool_name.value} 的 video_id 必须直接使用上一轮 list_series_videos 返回的真实 video_id。"
                    f" 当前可用 video_id: {sorted(valid_video_ids)}"
                )
            )


def _validate_plan_against_context(plan: AgentActionPlan, context: AgentContext) -> None:
    for call in plan.tool_calls:
        if not tool_is_available_in_context(call.tool_name, context):
            current_stage = context.scope_type if context.scope_type == "video" else context.inspection_stage.value
            allowed_tool_names = sorted(
                tool.name.value for tool in list_model_visible_tool_definitions_for_context(context)
            )
            raise AgentPlanError(
                f"{current_stage} 阶段不允许工具 {call.tool_name.value}。当前对模型可见的可用工具: {allowed_tool_names}"
            )
        if context.scope_type == "series" and tool_requires_video_id(call.tool_name):
            video_id = getattr(call, "video_id", None)
            if not isinstance(video_id, str) or not video_id.strip():
                raise AgentPlanError(f"{call.tool_name.value} 在 series 上下文中必须提供明确的 video_id。")
        if context.scope_type == "video":
            continue
        if (
            context.inspection_stage != InspectionStage.SERIES_DISCOVERY
            and context.candidate_buffer
            and tool_requires_candidate_buffer(call.tool_name)
        ):
            video_id = getattr(call, "video_id", None)
            candidate_video_ids = {item.video_id for item in context.candidate_buffer}
            if video_id is None or video_id not in candidate_video_ids:
                raise AgentPlanError(
                    f"{call.tool_name.value} 的 video_id 必须来自当前候选缓冲区。当前候选 video_id: {sorted(candidate_video_ids)}"
                )


def _extract_listed_video_ids(observed_tool_results: list[ToolExecutionResult]) -> set[str]:
    for result in reversed(observed_tool_results):
        if result.tool_name != ToolName.LIST_SERIES_VIDEOS or result.status != "ok":
            continue
        videos = result.payload.get("videos")
        if not isinstance(videos, list):
            return set()
        resolved_ids = {
            video.get("video_id")
            for video in videos
            if isinstance(video, dict) and isinstance(video.get("video_id"), str) and video.get("video_id").strip()
        }
        return {video_id.strip() for video_id in resolved_ids}
    return set()
