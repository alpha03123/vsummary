from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.ports import ChatGateway
from backend.agent.runtime.lanes.command_lane import build_generation_plan, build_open_tool_plan, build_save_note_plan
from backend.agent.runtime.request_router import RouteKind, classify_initial_route
from backend.agent.runtime.series_evidence_selector import SeriesEvidenceMode, classify_series_evidence_need
from backend.agent.runtime.series_locator import select_series_locate_candidates
from backend.agent.runtime.tool_loop import (
    extract_latest_listed_video_ids,
    extract_latest_transcript_result,
    extract_series_summary_results,
    extract_series_transcript_results,
)
from backend.agent.runtime.video_evidence_selector import VideoEvidenceMode, classify_video_evidence_need
from backend.agent.runtime.video_seek_locator import locate_video_seek
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import (
    GetVideoSummaryCall,
    GetVideoTranscriptCall,
    ListSeriesVideosCall,
    ToolExecutionResult,
    ToolName,
    VideoSeekCall,
)


def build_initial_route_plan(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
    last_tool_plan: AgentActionPlan | None,
) -> AgentActionPlan:
    if observed_tool_results or last_tool_plan is not None:
        raise RuntimeError("initial route 只允许在首轮构建。")
    route = classify_initial_route(
        gateway=gateway,
        context=context,
        user_message=user_message,
    )
    if route.kind == RouteKind.SERIES_LOCATE:
        plan = _build_series_locate_plan(context, route.reason)
        if plan is not None:
            return plan
    if route.kind == RouteKind.SAVE_NOTE:
        plan = build_save_note_plan(context, route.reason)
        if plan is not None:
            return plan
    if route.kind == RouteKind.VIDEO_SUMMARY:
        plan = _build_video_summary_plan(context)
        if plan is not None:
            return plan
    if route.kind == RouteKind.VIDEO_TRANSCRIPT:
        plan = _build_video_transcript_plan(context)
        if plan is not None:
            return plan
    if route.kind == RouteKind.VIDEO_SEEK:
        plan = _build_video_seek_plan(context)
        if plan is not None:
            return plan
    if route.kind == RouteKind.SERIES_SUMMARY:
        plan = _build_series_summary_plan(context, route.reason)
        if plan is not None:
            return plan
    if route.kind == RouteKind.OPEN_TOOL:
        plan = build_open_tool_plan(context, route.tool_name, route.reason)
        if plan is not None:
            return plan
    generation_plan = build_generation_plan(route.kind, context.scope_type, route.reason)
    if generation_plan is not None:
        return generation_plan
    if route.kind == RouteKind.OUT_OF_SCOPE:
        return AgentActionPlan(
            intent_type="out_of_scope",
            scope_type=context.scope_type,
            tool_calls=[],
            reason=route.reason or "这个请求超出了当前视频知识工作台的支持范围。",
            out_of_scope_reason=route.reason or "当前请求超出支持范围。",
        )
    return build_fallback_route_plan(
        gateway=gateway,
        context=context,
        user_message=user_message,
        reason=route.reason,
    )


def build_fallback_route_plan(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    reason: str,
) -> AgentActionPlan:
    if context.scope_type == "series":
        decision = classify_series_evidence_need(
            gateway=gateway,
            context=context,
            user_message=user_message,
        )
        if decision.mode == SeriesEvidenceMode.SUMMARY:
            plan = _build_series_summary_plan(context, decision.reason or reason)
            if plan is not None:
                return plan
        return AgentActionPlan(
            intent_type="out_of_scope",
            scope_type=context.scope_type,
            tool_calls=[],
            reason=decision.reason or reason or "当前请求超出了视频知识工作台的支持范围。",
            out_of_scope_reason=decision.reason or reason or "当前请求超出支持范围。",
        )

    decision = classify_video_evidence_need(
        gateway=gateway,
        context=context,
        user_message=user_message,
    )
    if decision.mode == VideoEvidenceMode.TRANSCRIPT:
        plan = _build_video_transcript_plan(context)
        if plan is not None:
            return plan
    plan = _build_video_summary_plan(context)
    if plan is not None:
        if reason.strip():
            return plan.model_copy(update={"reason": reason})
        return plan
    return AgentActionPlan(
        intent_type="out_of_scope",
        scope_type=context.scope_type,
        tool_calls=[],
        reason=reason or "当前请求超出了视频知识工作台的支持范围。",
        out_of_scope_reason=reason or "当前请求超出支持范围。",
    )


def build_seek_followup_plan(
    *,
    gateway: ChatGateway,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
    last_tool_plan: AgentActionPlan | None,
) -> AgentActionPlan | None:
    if last_tool_plan is None or last_tool_plan.intent_type.value != "seek_video":
        return None
    if any(result.tool_name == ToolName.VIDEO_SEEK for result in observed_tool_results):
        return None

    transcript_result = extract_latest_transcript_result(observed_tool_results)
    if transcript_result is None:
        return None

    decision = locate_video_seek(
        gateway=gateway,
        user_message=user_message,
        transcript_result=transcript_result,
    )
    return AgentActionPlan(
        intent_type="seek_video",
        scope_type="video",
        tool_calls=[
            VideoSeekCall(
                tool_name=ToolName.VIDEO_SEEK,
                seek_seconds=decision.seek_seconds,
                match_end_seconds=decision.match_end_seconds,
                matched_text=decision.matched_text,
                chapter_title=decision.chapter_title,
                query=user_message,
            )
        ],
        reason=decision.reason or "已经根据 transcript 定位到最相关的视频时间点。",
    )


def build_series_locate_followup_plan(
    *,
    gateway: ChatGateway,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
    last_tool_plan: AgentActionPlan | None,
) -> AgentActionPlan | None:
    if last_tool_plan is None or last_tool_plan.intent_type.value != "series_locate":
        return None

    summary_results = extract_series_summary_results(observed_tool_results)
    if not summary_results:
        listed_video_ids = extract_latest_listed_video_ids(observed_tool_results)
        if not listed_video_ids:
            return None
        return AgentActionPlan(
            intent_type="series_locate",
            scope_type="series",
            tool_calls=[
                GetVideoSummaryCall(
                    tool_name=ToolName.GET_VIDEO_SUMMARY,
                    video_id=video_id,
                )
                for video_id in listed_video_ids
            ],
            reason="先批量读取整个系列的 summary，再筛选最相关的视频。",
        )

    transcript_results = extract_series_transcript_results(observed_tool_results)
    if transcript_results:
        return None

    decision = select_series_locate_candidates(
        gateway=gateway,
        user_message=user_message,
        summary_results=summary_results,
    )
    resolved_video_ids = [
        video_id.strip()
        for video_id in decision.video_ids
        if isinstance(video_id, str) and video_id.strip()
    ]
    if not resolved_video_ids:
        return None

    return AgentActionPlan(
        intent_type="series_locate",
        scope_type="series",
        tool_calls=[
            GetVideoTranscriptCall(
                tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                video_id=video_id,
            )
            for video_id in resolved_video_ids
        ],
        reason=decision.reason or "已经选出最可能相关的视频，继续读取 transcript 做定位。",
    )


def _build_video_summary_plan(context: AgentContext) -> AgentActionPlan | None:
    if context.scope_type != "video":
        return None
    if not context.series_id or not context.video_id:
        return None
    return AgentActionPlan(
        intent_type="answer_question",
        scope_type="video",
        tool_calls=[
            GetVideoSummaryCall(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                series_id=context.series_id,
                video_id=context.video_id,
            )
        ],
        reason="当前视频问答先读取 summary，再基于证据回答。",
    )


def _build_video_transcript_plan(context: AgentContext) -> AgentActionPlan | None:
    if context.scope_type != "video":
        return None
    if not context.series_id or not context.video_id:
        return None
    return AgentActionPlan(
        intent_type="answer_question",
        scope_type="video",
        tool_calls=[
            GetVideoTranscriptCall(
                tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                series_id=context.series_id,
                video_id=context.video_id,
            )
        ],
        reason="当前视频问答先读取 transcript，再基于证据回答。",
    )


def _build_video_seek_plan(context: AgentContext) -> AgentActionPlan | None:
    if context.scope_type != "video":
        return None
    if not context.series_id or not context.video_id:
        return None
    return AgentActionPlan(
        intent_type="seek_video",
        scope_type="video",
        tool_calls=[
            GetVideoTranscriptCall(
                tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                series_id=context.series_id,
                video_id=context.video_id,
            )
        ],
        reason="当前请求需要先读取 transcript，再定位视频时间点。",
    )


def _build_series_summary_plan(context: AgentContext, reason: str) -> AgentActionPlan | None:
    if context.scope_type != "series":
        return None
    if not context.series_id:
        return None
    return AgentActionPlan(
        intent_type="series_answer",
        scope_type="series",
        tool_calls=[
            ListSeriesVideosCall(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                series_id=context.series_id,
            )
        ],
        reason=reason or "这是系列概括型问题，先读取系列视频列表再展开证据链。",
    )


def _build_series_locate_plan(context: AgentContext, reason: str) -> AgentActionPlan | None:
    if context.scope_type != "series":
        return None
    if not context.series_id:
        return None
    return AgentActionPlan(
        intent_type="series_locate",
        scope_type="series",
        tool_calls=[
            ListSeriesVideosCall(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                series_id=context.series_id,
            )
        ],
        reason=reason or "先列出系列视频，再筛出最值得继续定位的候选视频。",
    )
