from __future__ import annotations

from collections.abc import Callable

from backend.agent.schemas.action_plan import AgentActionPlan, IntentType
from backend.agent.schemas.tool_calls import GetVideoSummaryCall, GetVideoToolsCall, ToolExecutionResult, ToolName
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
from backend.agent.validation.seek_video import validate_seek_video_plan


PlanValidator = Callable[[AgentActionPlan], AgentActionPlan]


PLAN_VALIDATORS: dict[IntentType, PlanValidator] = {
    IntentType.ANSWER_QUESTION: validate_answer_question_plan,
    IntentType.OPEN_TOOL: validate_open_tool_plan,
    IntentType.SEEK_VIDEO: validate_seek_video_plan,
    IntentType.GENERATE_OVERVIEW: validate_generate_overview_plan,
    IntentType.GENERATE_MINDMAP: validate_generate_mindmap_plan,
    IntentType.SERIES_ANSWER: validate_series_answer_plan,
    IntentType.OUT_OF_SCOPE: validate_out_of_scope_plan,
}


def validate_action_plan(
    plan: AgentActionPlan,
    observed_tool_results: list[ToolExecutionResult] | None = None,
) -> AgentActionPlan:
    validator = PLAN_VALIDATORS.get(plan.intent_type)
    if validator is None:
        raise AgentPlanError(f"Unsupported intent_type: {plan.intent_type.value}")
    validated_plan = validator(plan)
    _validate_plan_against_observations(validated_plan, observed_tool_results or [])
    return validated_plan


def _validate_plan_against_observations(
    plan: AgentActionPlan,
    observed_tool_results: list[ToolExecutionResult],
) -> None:
    valid_video_ids = _extract_listed_video_ids(observed_tool_results)
    if not valid_video_ids:
        return

    for call in plan.tool_calls:
        if not isinstance(call, GetVideoSummaryCall | GetVideoToolsCall):
            continue
        if call.video_id is None:
            continue
        if call.video_id not in valid_video_ids:
            raise AgentPlanError(
                "get_video_summary / get_video_tools 的 video_id 必须直接使用上一轮 list_series_videos 返回的真实 video_id。"
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
