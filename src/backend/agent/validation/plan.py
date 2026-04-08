from __future__ import annotations

from collections.abc import Callable

from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.schemas.action_plan import AgentActionPlan, IntentType
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName
from backend.agent.tools import tool_is_available_in_context, tool_requires_candidate_buffer, tool_requires_video_id
from backend.agent.validation.answer import (
    validate_answer_question_plan,
    validate_series_answer_plan,
)
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.generate import (
    validate_generate_mindmap_plan,
    validate_generate_overview_plan,
)
from backend.agent.validation.open_tool import validate_open_tool_plan
from backend.agent.validation.out_of_scope import validate_out_of_scope_plan
from backend.agent.validation.save_note import validate_save_note_plan
from backend.agent.validation.series_locate import validate_series_locate_plan
from backend.agent.validation.seek_video import validate_seek_video_plan
from backend.agent.validation.shared import validate_batch_tool_usage


PlanValidator = Callable[[AgentActionPlan], AgentActionPlan]


PLAN_VALIDATORS: dict[IntentType, PlanValidator] = {
    IntentType.ANSWER_QUESTION: validate_answer_question_plan,
    IntentType.SERIES_LOCATE: validate_series_locate_plan,
    IntentType.OPEN_TOOL: validate_open_tool_plan,
    IntentType.SEEK_VIDEO: validate_seek_video_plan,
    IntentType.SAVE_NOTE: validate_save_note_plan,
    IntentType.GENERATE_OVERVIEW: validate_generate_overview_plan,
    IntentType.GENERATE_MINDMAP: validate_generate_mindmap_plan,
    IntentType.SERIES_ANSWER: validate_series_answer_plan,
    IntentType.OUT_OF_SCOPE: validate_out_of_scope_plan,
}


def validate_action_plan(
    plan: AgentActionPlan,
    context: AgentContext,
    observed_tool_results: list[ToolExecutionResult] | None = None,
) -> AgentActionPlan:
    validator = PLAN_VALIDATORS.get(plan.intent_type)
    if validator is None:
        raise AgentPlanError(f"Unsupported intent_type: {plan.intent_type.value}")
    resolved_tool_results = observed_tool_results or []
    validated_plan = validator(plan)
    validate_batch_tool_usage(validated_plan)
    _validate_plan_against_context(validated_plan, context)
    _validate_plan_against_observations(validated_plan, context, resolved_tool_results)
    _validate_terminal_action_plan(validated_plan, resolved_tool_results)
    return validated_plan


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
                f"{call.tool_name.value} 的 video_id 必须直接使用上一轮 list_series_videos 返回的真实 video_id。"
            )


def _validate_plan_against_context(plan: AgentActionPlan, context: AgentContext) -> None:
    for call in plan.tool_calls:
        if not tool_is_available_in_context(call.tool_name, context):
            current_stage = context.scope_type if context.scope_type == "video" else context.inspection_stage.value
            raise AgentPlanError(
                f"{current_stage} 阶段不允许工具 {call.tool_name.value}。"
            )
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
                    f"{call.tool_name.value} 的 video_id 必须来自当前候选缓冲区。"
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


def _validate_terminal_action_plan(
    plan: AgentActionPlan,
    observed_tool_results: list[ToolExecutionResult],
) -> None:
    if plan.tool_calls:
        return
    if plan.intent_type not in {
        IntentType.OPEN_TOOL,
        IntentType.SEEK_VIDEO,
        IntentType.SAVE_NOTE,
        IntentType.GENERATE_OVERVIEW,
        IntentType.GENERATE_MINDMAP,
    }:
        return
    if observed_tool_results:
        return
    raise AgentPlanError(f"{plan.intent_type.value} 首轮至少需要一个工具调用。")
