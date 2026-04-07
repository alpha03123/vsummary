from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import (
    AddSeriesCandidatesCall,
    ClearSeriesCandidatesCall,
    RemoveSeriesCandidatesCall,
    ReplaceSeriesCandidatesCall,
    ToolDefinition,
    ToolContextTag,
    ToolEffectTag,
    ToolExecutionResult,
    ToolIntentTag,
    ToolName,
    ViewSeriesCandidatesCall,
)
from backend.video_summary.library.ports import VideoWorkspace

VIEW_SERIES_CANDIDATES_TOOL = ToolDefinition(
    name=ToolName.VIEW_SERIES_CANDIDATES,
    title="查看候选缓冲区",
    description="查看当前系列缓冲区中的候选视频、已检查视频和已淘汰视频。",
    contexts=(ToolContextTag.SERIES_DISCOVERY, ToolContextTag.SERIES_INSPECTION),
    intents=(ToolIntentTag.SERIES_ANSWER,),
)

ADD_SERIES_CANDIDATES_TOOL = ToolDefinition(
    name=ToolName.ADD_SERIES_CANDIDATES,
    title="加入候选视频",
    description="把一个或多个视频加入当前系列的候选缓冲区，供下一阶段深度检查。",
    arguments={
        "video_ids": "要加入缓冲区的 video_id 列表",
        "reason": "可选，为什么把这些视频加入缓冲区",
    },
    contexts=(ToolContextTag.SERIES_DISCOVERY, ToolContextTag.SERIES_INSPECTION),
    intents=(ToolIntentTag.SERIES_ANSWER,),
    effects=(ToolEffectTag.APPLY_CANDIDATE_BUFFER_PAYLOAD,),
)

REMOVE_SERIES_CANDIDATES_TOOL = ToolDefinition(
    name=ToolName.REMOVE_SERIES_CANDIDATES,
    title="移出候选视频",
    description="把一个或多个视频从当前系列的候选缓冲区中移出。",
    arguments={
        "video_ids": "要移出的 video_id 列表",
        "reason": "可选，为什么把这些视频移出缓冲区",
    },
    contexts=(ToolContextTag.SERIES_DISCOVERY, ToolContextTag.SERIES_INSPECTION),
    intents=(ToolIntentTag.SERIES_ANSWER,),
    effects=(ToolEffectTag.APPLY_CANDIDATE_BUFFER_PAYLOAD,),
)

REPLACE_SERIES_CANDIDATES_TOOL = ToolDefinition(
    name=ToolName.REPLACE_SERIES_CANDIDATES,
    title="替换候选缓冲区",
    description="用一组新视频直接替换当前候选缓冲区。",
    arguments={
        "video_ids": "新的候选 video_id 列表",
        "reason": "可选，为什么重建这组候选",
    },
    contexts=(ToolContextTag.SERIES_DISCOVERY, ToolContextTag.SERIES_INSPECTION),
    intents=(ToolIntentTag.SERIES_ANSWER,),
    effects=(ToolEffectTag.APPLY_CANDIDATE_BUFFER_PAYLOAD,),
)

CLEAR_SERIES_CANDIDATES_TOOL = ToolDefinition(
    name=ToolName.CLEAR_SERIES_CANDIDATES,
    title="清空候选缓冲区",
    description="清空当前系列的候选缓冲区、已检查列表和已淘汰列表。",
    contexts=(ToolContextTag.SERIES_DISCOVERY, ToolContextTag.SERIES_INSPECTION),
    intents=(ToolIntentTag.SERIES_ANSWER,),
    effects=(ToolEffectTag.APPLY_CANDIDATE_BUFFER_PAYLOAD,),
)


def create_view_series_candidates_handler(workspace: VideoWorkspace):
    def execute_view_series_candidates(call: ViewSeriesCandidatesCall, context: AgentContext) -> ToolExecutionResult:
        del call
        return ToolExecutionResult(
            tool_name=ToolName.VIEW_SERIES_CANDIDATES,
            status="ok",
            payload=_serialize_buffer_payload(context),
        )

    return execute_view_series_candidates


def create_add_series_candidates_handler(workspace: VideoWorkspace):
    def execute_add_series_candidates(call: AddSeriesCandidatesCall, context: AgentContext) -> ToolExecutionResult:
        resolved_videos = _resolve_series_videos(workspace, context, call.video_ids)
        current_ids = {item.video_id for item in context.candidate_buffer}
        next_buffer = [item.model_dump(mode="json") for item in context.candidate_buffer]
        for video in resolved_videos:
            if video["video_id"] in current_ids:
                continue
            next_buffer.append({**video, "reason": call.reason.strip()})
        return ToolExecutionResult(
            tool_name=ToolName.ADD_SERIES_CANDIDATES,
            status="ok",
            payload={
                "reason": call.reason.strip(),
                "added_videos": [{**video, "reason": call.reason.strip()} for video in resolved_videos if video["video_id"] not in current_ids],
                "candidate_buffer": next_buffer,
            },
        )

    return execute_add_series_candidates


def create_remove_series_candidates_handler(workspace: VideoWorkspace):
    def execute_remove_series_candidates(call: RemoveSeriesCandidatesCall, context: AgentContext) -> ToolExecutionResult:
        del workspace
        remove_ids = {video_id.strip() for video_id in call.video_ids if video_id.strip()}
        removed = [item.model_dump(mode="json") for item in context.candidate_buffer if item.video_id in remove_ids]
        next_buffer = [item.model_dump(mode="json") for item in context.candidate_buffer if item.video_id not in remove_ids]
        return ToolExecutionResult(
            tool_name=ToolName.REMOVE_SERIES_CANDIDATES,
            status="ok",
            payload={
                "reason": call.reason.strip(),
                "removed_videos": removed,
                "candidate_buffer": next_buffer,
            },
        )

    return execute_remove_series_candidates


def create_replace_series_candidates_handler(workspace: VideoWorkspace):
    def execute_replace_series_candidates(call: ReplaceSeriesCandidatesCall, context: AgentContext) -> ToolExecutionResult:
        resolved_videos = _resolve_series_videos(workspace, context, call.video_ids)
        next_buffer = [{**video, "reason": call.reason.strip()} for video in resolved_videos]
        return ToolExecutionResult(
            tool_name=ToolName.REPLACE_SERIES_CANDIDATES,
            status="ok",
            payload={
                "reason": call.reason.strip(),
                "candidate_buffer": next_buffer,
            },
        )

    return execute_replace_series_candidates


def create_clear_series_candidates_handler(workspace: VideoWorkspace):
    def execute_clear_series_candidates(call: ClearSeriesCandidatesCall, context: AgentContext) -> ToolExecutionResult:
        del workspace, call, context
        return ToolExecutionResult(
            tool_name=ToolName.CLEAR_SERIES_CANDIDATES,
            status="ok",
            payload={
                "candidate_buffer": [],
                "inspected_video_ids": [],
                "rejected_video_ids": [],
            },
        )

    return execute_clear_series_candidates


def _resolve_series_videos(workspace: VideoWorkspace, context: AgentContext, video_ids: list[str]) -> list[dict[str, object]]:
    series = next((item for item in workspace.list_series() if item.id == context.series_id), None)
    if series is None:
        raise RuntimeError("当前缺少有效的 series 上下文，无法维护候选缓冲区。")
    requested_ids = [video_id.strip() for video_id in video_ids if isinstance(video_id, str) and video_id.strip()]
    if not requested_ids:
        raise RuntimeError("候选缓冲区操作必须提供至少一个有效的 video_id。")
    series_videos = {video.id: video for video in series.videos}
    resolved_videos: list[dict[str, object]] = []
    missing_ids: list[str] = []
    for video_id in requested_ids:
        video = series_videos.get(video_id)
        if video is None:
            missing_ids.append(video_id)
            continue
        resolved_videos.append(
            {
                "video_id": video.id,
                "title": video.title,
                "processed": video.processed,
                "status": video.status,
            }
        )
    if missing_ids:
        raise RuntimeError(f"候选缓冲区中存在无效 video_id: {', '.join(missing_ids)}")
    return resolved_videos


def _serialize_buffer_payload(context: AgentContext) -> dict[str, object]:
    return {
        "candidate_buffer": [item.model_dump(mode="json") for item in context.candidate_buffer],
        "inspected_video_ids": list(context.inspected_video_ids),
        "rejected_video_ids": list(context.rejected_video_ids),
    }
