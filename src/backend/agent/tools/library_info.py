from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import (
    GetVideoSummaryCall,
    GetVideoTranscriptCall,
    GetVideoToolsCall,
    ListSeriesVideosCall,
    ToolDefinition,
    ToolContextTag,
    ToolExecutionResult,
    ToolIntentTag,
    ToolName,
    ToolPlane,
)
from backend.video_summary.library.ports import VideoWorkspace


LIST_SERIES_VIDEOS_TOOL = ToolDefinition(
    name=ToolName.LIST_SERIES_VIDEOS,
    title="读取系列视频列表",
    description="读取当前系列下的视频列表与处理状态，用于系列级总结和跨视频检索。",
    plane=ToolPlane.BUSINESS_READ,
    concurrency_safe=True,
    arguments={"series_id": "可选，目标系列 ID；不填则默认当前系列"},
    contexts=(ToolContextTag.SERIES_DISCOVERY, ToolContextTag.SERIES_INSPECTION),
    intents=(ToolIntentTag.SERIES_ANSWER, ToolIntentTag.SERIES_LOCATE),
)

GET_VIDEO_SUMMARY_TOOL = ToolDefinition(
    name=ToolName.GET_VIDEO_SUMMARY,
    title="读取视频概况",
    description="读取指定视频的概况内容，用于系列级聚合回答。",
    plane=ToolPlane.BUSINESS_READ,
    concurrency_safe=True,
    batch_tag="series_videos",
    arguments={
        "series_id": "可选，目标系列 ID；不填则默认当前系列",
        "video_id": "可选，目标视频 ID；不填则默认当前视频",
    },
    contexts=(ToolContextTag.SERIES_INSPECTION, ToolContextTag.VIDEO),
    intents=(ToolIntentTag.ANSWER_QUESTION, ToolIntentTag.SERIES_ANSWER, ToolIntentTag.SERIES_LOCATE, ToolIntentTag.SAVE_NOTE),
    requires_video_id=True,
)

GET_VIDEO_TOOLS_TOOL = ToolDefinition(
    name=ToolName.GET_VIDEO_TOOLS,
    title="读取视频工具状态",
    description="读取指定视频的概况、导图、知识卡片和笔记等工具状态。",
    plane=ToolPlane.BUSINESS_READ,
    concurrency_safe=True,
    batch_tag="series_videos",
    arguments={
        "series_id": "可选，目标系列 ID；不填则默认当前系列",
        "video_id": "可选，目标视频 ID；不填则默认当前视频",
    },
    contexts=(ToolContextTag.SERIES_INSPECTION, ToolContextTag.VIDEO),
    intents=(ToolIntentTag.ANSWER_QUESTION, ToolIntentTag.SERIES_ANSWER, ToolIntentTag.SERIES_LOCATE),
    requires_video_id=True,
)

GET_VIDEO_TRANSCRIPT_TOOL = ToolDefinition(
    name=ToolName.GET_VIDEO_TRANSCRIPT,
    title="读取视频转写全文",
    description="读取指定视频的完整转写分段，包含时间轴与原文。",
    plane=ToolPlane.BUSINESS_READ,
    concurrency_safe=True,
    batch_tag="series_videos",
    arguments={
        "series_id": "可选，目标系列 ID；不填则默认当前系列",
        "video_id": "可选，目标视频 ID；不填则默认当前视频",
    },
    contexts=(ToolContextTag.SERIES_INSPECTION, ToolContextTag.VIDEO),
    intents=(ToolIntentTag.ANSWER_QUESTION, ToolIntentTag.SERIES_ANSWER, ToolIntentTag.SERIES_LOCATE, ToolIntentTag.SEEK_VIDEO, ToolIntentTag.SAVE_NOTE),
    requires_video_id=True,
)


def list_library_info_tool_definitions() -> list[ToolDefinition]:
    return [
        LIST_SERIES_VIDEOS_TOOL,
        GET_VIDEO_SUMMARY_TOOL,
        GET_VIDEO_TOOLS_TOOL,
        GET_VIDEO_TRANSCRIPT_TOOL,
    ]


def create_list_series_videos_handler(workspace: VideoWorkspace):
    def execute_list_series_videos(call: ListSeriesVideosCall, context: AgentContext) -> ToolExecutionResult:
        resolved_series_id = _resolve_series_id(call.series_id, context)
        series = next((item for item in workspace.list_series() if item.id == resolved_series_id), None)
        if series is None:
            return ToolExecutionResult(
                tool_name=ToolName.LIST_SERIES_VIDEOS,
                status="not_found",
                payload={"series_id": resolved_series_id, "videos": []},
            )

        return ToolExecutionResult(
            tool_name=ToolName.LIST_SERIES_VIDEOS,
            status="ok",
            payload={
                "series_id": series.id,
                "series_title": series.title,
                "videos": [
                    {
                        "video_id": video.id,
                        "title": video.title,
                        "processed": video.processed,
                        "status": video.status,
                    }
                    for video in series.videos
                ],
            },
        )

    return execute_list_series_videos


def create_get_video_summary_handler(workspace: VideoWorkspace):
    def execute_get_video_summary(call: GetVideoSummaryCall, context: AgentContext) -> ToolExecutionResult:
        resolved_target = _resolve_video_target(call.series_id, call.video_id, context)
        if resolved_target is None:
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="invalid_input",
                payload={
                    "series_id": _resolve_series_id(call.series_id, context),
                    "generated": False,
                    "error": "缺少 video_id，无法读取视频概况。",
                },
            )
        resolved_series_id, resolved_video_id = resolved_target
        summary = workspace.get_video_summary(resolved_series_id, resolved_video_id)
        if summary is None:
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                status="not_found",
                payload={
                    "series_id": resolved_series_id,
                    "video_id": resolved_video_id,
                    "generated": False,
                },
            )

        raw_summary = summary.summary
        raw_chapters = raw_summary.get("chapters", []) if isinstance(raw_summary, dict) else []
        chapters = []
        if isinstance(raw_chapters, list):
            for item in raw_chapters:
                if not isinstance(item, dict):
                    continue
                chapters.append(
                    {
                        "chapter_id": item.get("id"),
                        "title": item.get("title"),
                        "summary": item.get("summary"),
                        "key_points": item.get("key_points", []),
                        "start_seconds": item.get("start_seconds"),
                        "end_seconds": item.get("end_seconds"),
                    }
                )

        return ToolExecutionResult(
            tool_name=ToolName.GET_VIDEO_SUMMARY,
            status="ok",
            payload={
                "series_id": summary.series_id,
                "video_id": summary.video_id,
                "title": summary.title,
                "generated": True,
                "one_sentence_summary": raw_summary.get("one_sentence_summary", "") if isinstance(raw_summary, dict) else "",
                "core_problem": raw_summary.get("core_problem", "") if isinstance(raw_summary, dict) else "",
                "key_takeaways": raw_summary.get("key_takeaways", []) if isinstance(raw_summary, dict) else [],
                "chapters": chapters,
            },
        )

    return execute_get_video_summary


def create_get_video_tools_handler(workspace: VideoWorkspace):
    def execute_get_video_tools(call: GetVideoToolsCall, context: AgentContext) -> ToolExecutionResult:
        resolved_target = _resolve_video_target(call.series_id, call.video_id, context)
        if resolved_target is None:
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_TOOLS,
                status="invalid_input",
                payload={
                    "series_id": _resolve_series_id(call.series_id, context),
                    "error": "缺少 video_id，无法读取视频工具状态。",
                },
            )
        resolved_series_id, resolved_video_id = resolved_target
        tools = workspace.get_video_workspace_tools(resolved_series_id, resolved_video_id)
        if tools is None:
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_TOOLS,
                status="not_found",
                payload={"series_id": resolved_series_id, "video_id": resolved_video_id},
            )

        return ToolExecutionResult(
            tool_name=ToolName.GET_VIDEO_TOOLS,
            status="ok",
            payload={
                "series_id": tools.series_id,
                "video_id": tools.video_id,
                "overview": _serialize_tool(tools.overview),
                "knowledge_cards": _serialize_tool(tools.knowledge_cards),
                "mindmap": _serialize_tool(tools.mindmap),
                "notes": _serialize_tool(tools.notes),
                "preview": _serialize_tool(tools.preview),
            },
        )

    return execute_get_video_tools


def create_get_video_transcript_handler(workspace: VideoWorkspace):
    def execute_get_video_transcript(call: GetVideoTranscriptCall, context: AgentContext) -> ToolExecutionResult:
        resolved_target = _resolve_video_target(call.series_id, call.video_id, context)
        if resolved_target is None:
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                status="invalid_input",
                payload={
                    "series_id": _resolve_series_id(call.series_id, context),
                    "generated": False,
                    "error": "缺少 video_id，无法读取视频转写。",
                },
            )
        resolved_series_id, resolved_video_id = resolved_target
        transcript = workspace.get_video_transcript(resolved_series_id, resolved_video_id)
        if transcript is None:
            return ToolExecutionResult(
                tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                status="not_found",
                payload={
                    "series_id": resolved_series_id,
                    "video_id": resolved_video_id,
                    "generated": False,
                },
            )

        return ToolExecutionResult(
            tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
            status="ok",
            payload={
                "series_id": transcript.series_id,
                "video_id": transcript.video_id,
                "title": transcript.title,
                "generated": True,
                "duration_seconds": transcript.duration_seconds,
                "segments": [
                    {
                        "start_seconds": item.start_seconds,
                        "end_seconds": item.end_seconds,
                        "text": item.text,
                    }
                    for item in transcript.segments
                ],
            },
        )

    return execute_get_video_transcript


def _resolve_series_id(series_id: str | None, context: AgentContext) -> str:
    resolved = (series_id or context.series_id or "").strip()
    if not resolved:
        raise RuntimeError("当前缺少 series 上下文，无法读取系列视频列表。")
    return resolved


def _resolve_video_target(
    series_id: str | None,
    video_id: str | None,
    context: AgentContext,
) -> tuple[str, str] | None:
    resolved_series_id = _resolve_series_id(series_id, context)
    resolved_video_id = (video_id or context.video_id or "").strip()
    if not resolved_video_id:
        return None
    return resolved_series_id, resolved_video_id


def _serialize_tool(tool) -> dict[str, object]:
    return {
        "id": tool.id,
        "title": tool.title,
        "available": tool.available,
        "generated": tool.generated,
        "status": tool.status,
        "preview_url": tool.preview_url,
    }
