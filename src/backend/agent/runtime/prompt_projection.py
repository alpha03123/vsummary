from __future__ import annotations

import json
import re

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


DEFAULT_MAX_SUMMARY_TAKEAWAYS = 5
DEFAULT_MAX_SUMMARY_CHAPTERS = 4
DEFAULT_MAX_TRANSCRIPT_SEGMENTS = 8
DEFAULT_MAX_SEGMENT_TEXT_CHARS = 180


def build_prompt_projection(
    *,
    context: AgentContext,
    user_message: str,
    tool_results: list[ToolExecutionResult],
    max_tokens: int | None = None,
) -> dict[str, object]:
    projection = {
        "scope_type": context.scope_type,
        "series_id": context.series_id,
        "video_id": context.video_id,
        "user_message": user_message,
        "evidence": [
            _project_tool_result(user_message=user_message, result=result)
            for result in tool_results
        ],
    }
    if max_tokens is None:
        return projection
    return _shrink_projection_to_budget(projection, max_tokens=max_tokens)


def estimate_prompt_projection_tokens(
    *,
    context: AgentContext,
    user_message: str,
    tool_results: list[ToolExecutionResult],
    max_tokens: int | None = None,
) -> int:
    payload = build_prompt_projection(
        context=context,
        user_message=user_message,
        tool_results=tool_results,
        max_tokens=max_tokens,
    )
    return _estimate_tokens(payload)


def _project_tool_result(*, user_message: str, result: ToolExecutionResult) -> dict[str, object]:
    if result.tool_name == ToolName.LIST_SERIES_VIDEOS:
        return _project_series_list(result)
    if result.tool_name == ToolName.GET_VIDEO_SUMMARY:
        return _project_video_summary(result)
    if result.tool_name == ToolName.GET_VIDEO_TOOLS:
        return _project_video_tools(result)
    if result.tool_name == ToolName.GET_VIDEO_TRANSCRIPT:
        return _project_video_transcript(user_message=user_message, result=result)
    return {
        "tool_name": result.tool_name.value,
        "status": result.status,
        "payload": result.payload,
    }


def _project_series_list(result: ToolExecutionResult) -> dict[str, object]:
    videos = result.payload.get("videos", [])
    projected_videos = []
    if isinstance(videos, list):
        for item in videos:
            if not isinstance(item, dict):
                continue
            projected_videos.append(
                {
                    "video_id": item.get("video_id"),
                    "title": item.get("title"),
                    "processed": item.get("processed"),
                    "status": item.get("status"),
                }
            )
    return {
        "tool_name": result.tool_name.value,
        "status": result.status,
        "payload": {
            "series_id": result.payload.get("series_id"),
            "series_title": result.payload.get("series_title"),
            "videos": projected_videos,
        },
    }


def _project_video_summary(result: ToolExecutionResult) -> dict[str, object]:
    payload = result.payload
    raw_takeaways = payload.get("key_takeaways", [])
    raw_chapters = payload.get("chapters", [])
    takeaways = raw_takeaways[:DEFAULT_MAX_SUMMARY_TAKEAWAYS] if isinstance(raw_takeaways, list) else []
    chapters = []
    if isinstance(raw_chapters, list):
        for item in raw_chapters[:DEFAULT_MAX_SUMMARY_CHAPTERS]:
            if not isinstance(item, dict):
                continue
            chapters.append(
                {
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "start_seconds": item.get("start_seconds"),
                    "end_seconds": item.get("end_seconds"),
                }
            )
    return {
        "tool_name": result.tool_name.value,
        "status": result.status,
        "payload": {
            "series_id": payload.get("series_id"),
            "video_id": payload.get("video_id"),
            "title": payload.get("title"),
            "generated": payload.get("generated"),
            "one_sentence_summary": payload.get("one_sentence_summary"),
            "core_problem": payload.get("core_problem"),
            "key_takeaways": takeaways,
            "chapters": chapters,
        },
    }


def _project_video_tools(result: ToolExecutionResult) -> dict[str, object]:
    payload = result.payload
    projected_payload = {
        "series_id": payload.get("series_id"),
        "video_id": payload.get("video_id"),
    }
    for field in ("overview", "knowledge_cards", "mindmap", "notes", "preview"):
        item = payload.get(field)
        if isinstance(item, dict):
            projected_payload[field] = {
                "available": item.get("available"),
                "generated": item.get("generated"),
                "status": item.get("status"),
            }
    return {
        "tool_name": result.tool_name.value,
        "status": result.status,
        "payload": projected_payload,
    }


def _project_video_transcript(*, user_message: str, result: ToolExecutionResult) -> dict[str, object]:
    payload = result.payload
    segments = payload.get("segments", [])
    selected_segments = _select_relevant_segments(user_message, segments)
    return {
        "tool_name": result.tool_name.value,
        "status": result.status,
        "payload": {
            "series_id": payload.get("series_id"),
            "video_id": payload.get("video_id"),
            "title": payload.get("title"),
            "duration_seconds": payload.get("duration_seconds"),
            "segments": selected_segments,
        },
    }


def _select_relevant_segments(user_message: str, raw_segments: object) -> list[dict[str, object]]:
    if not isinstance(raw_segments, list):
        return []
    normalized_segments = [
        item
        for item in raw_segments
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ]
    if not normalized_segments:
        return []

    query_terms = _extract_query_terms(user_message)
    if not query_terms:
        return [_trim_segment(item) for item in normalized_segments[:DEFAULT_MAX_TRANSCRIPT_SEGMENTS]]

    scored_segments = [
        (_score_segment(str(item.get("text", "")), query_terms), index, item)
        for index, item in enumerate(normalized_segments)
    ]
    scored_segments.sort(key=lambda entry: (-entry[0], entry[1]))
    top_matches = [item for score, _index, item in scored_segments if score > 0][:DEFAULT_MAX_TRANSCRIPT_SEGMENTS]
    if not top_matches:
        top_matches = normalized_segments[:DEFAULT_MAX_TRANSCRIPT_SEGMENTS]
    return [_trim_segment(item) for item in top_matches]


def _trim_segment(segment: dict[str, object]) -> dict[str, object]:
    text = str(segment.get("text", "")).strip()
    if len(text) > DEFAULT_MAX_SEGMENT_TEXT_CHARS:
        text = f"{text[: DEFAULT_MAX_SEGMENT_TEXT_CHARS - 3]}..."
    return {
        "start_seconds": segment.get("start_seconds"),
        "end_seconds": segment.get("end_seconds"),
        "text": text,
    }


def _extract_query_terms(user_message: str) -> list[str]:
    english_terms = re.findall(r"[A-Za-z0-9_]+", user_message.lower())
    cjk_terms = re.findall(r"[\u4e00-\u9fff]{2,}", user_message)
    combined = [*english_terms, *cjk_terms]
    seen: set[str] = set()
    ordered: list[str] = []
    for term in combined:
        normalized = term.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _score_segment(text: str, query_terms: list[str]) -> int:
    lowered = text.lower()
    score = 0
    for term in query_terms:
        if term in lowered or term in text:
            score += max(1, len(term))
    return score
def _estimate_tokens(value: object) -> int:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")).strip()
    if not text:
        return 0
    return max(1, len(text.encode("utf-8")) // 3)


def _shrink_projection_to_budget(projection: dict[str, object], *, max_tokens: int) -> dict[str, object]:
    if _estimate_tokens(projection) <= max_tokens:
        return projection

    shrunk = json.loads(json.dumps(projection, ensure_ascii=False))
    evidence = shrunk.get("evidence", [])
    if not isinstance(evidence, list):
        return projection

    for item in evidence:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        if "chapters" in payload:
            payload["chapters"] = []
        if isinstance(payload.get("key_takeaways"), list):
            payload["key_takeaways"] = payload["key_takeaways"][:3]
    if _estimate_tokens(shrunk) <= max_tokens:
        return shrunk

    for item in evidence:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        if isinstance(payload.get("segments"), list):
            payload["segments"] = payload["segments"][:4]
            for segment in payload["segments"]:
                if not isinstance(segment, dict):
                    continue
                text = str(segment.get("text", "")).strip()
                if len(text) > 100:
                    segment["text"] = f"{text[:97]}..."
    if _estimate_tokens(shrunk) <= max_tokens:
        return shrunk

    for item in evidence:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        if isinstance(payload.get("segments"), list):
            payload["segments"] = payload["segments"][:2]
        if isinstance(payload.get("videos"), list):
            payload["videos"] = payload["videos"][:10]
    return shrunk
