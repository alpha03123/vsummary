from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult, ToolName
from backend.agent.session.models import AgentSessionEvidenceEntry


CACHEABLE_TOOL_NAMES: set[ToolName] = {
    ToolName.LIST_SERIES_VIDEOS,
    ToolName.GET_VIDEO_SUMMARY,
    ToolName.GET_VIDEO_TRANSCRIPT,
}


def build_cache_entries(
    existing_entries: list[AgentSessionEvidenceEntry],
    tool_results: list[ToolExecutionResult],
    *,
    updated_at: str,
) -> list[AgentSessionEvidenceEntry]:
    merged: dict[str, AgentSessionEvidenceEntry] = {
        entry.cache_key: entry
        for entry in existing_entries
    }
    for result in tool_results:
        if result.status != "ok":
            continue
        cache_key = build_result_cache_key(result)
        if cache_key is None:
            continue
        merged[cache_key] = AgentSessionEvidenceEntry(
            cache_key=cache_key,
            tool_result=result,
            updated_at=updated_at,
        )
    return list(merged.values())


def restore_cached_tool_results(entries: list[AgentSessionEvidenceEntry]) -> list[ToolExecutionResult]:
    return [entry.tool_result for entry in entries]


def build_cached_result_index(tool_results: list[ToolExecutionResult]) -> dict[str, ToolExecutionResult]:
    index: dict[str, ToolExecutionResult] = {}
    for result in tool_results:
        cache_key = build_result_cache_key(result)
        if cache_key is None:
            continue
        index[cache_key] = result
    return index


def build_result_cache_key(result: ToolExecutionResult) -> str | None:
    if result.tool_name not in CACHEABLE_TOOL_NAMES:
        return None
    payload = result.payload
    if result.tool_name == ToolName.LIST_SERIES_VIDEOS:
        series_id = str(payload.get("series_id", "")).strip()
        if not series_id:
            return None
        return f"{result.tool_name.value}:{series_id}"
    series_id = str(payload.get("series_id", "")).strip()
    video_id = str(payload.get("video_id", "")).strip()
    if not series_id or not video_id:
        return None
    return f"{result.tool_name.value}:{series_id}:{video_id}"


def build_call_cache_key(call: ToolCall, context: AgentContext) -> str | None:
    if call.tool_name not in CACHEABLE_TOOL_NAMES:
        return None
    if call.tool_name == ToolName.LIST_SERIES_VIDEOS:
        series_id = str(getattr(call, "series_id", None) or context.series_id or "").strip()
        if not series_id:
            return None
        return f"{call.tool_name.value}:{series_id}"
    series_id = str(getattr(call, "series_id", None) or context.series_id or "").strip()
    video_id = str(getattr(call, "video_id", None) or context.video_id or "").strip()
    if not series_id or not video_id:
        return None
    return f"{call.tool_name.value}:{series_id}:{video_id}"


def filter_cached_tool_calls(
    calls: list[ToolCall],
    *,
    context: AgentContext,
    cached_index: dict[str, ToolExecutionResult],
) -> list[ToolCall]:
    executable_calls: list[ToolCall] = []
    for call in calls:
        cache_key = build_call_cache_key(call, context)
        if cache_key is not None and cache_key in cached_index:
            continue
        executable_calls.append(call)
    return executable_calls
