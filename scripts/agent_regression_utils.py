from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.api.bootstrap import ApiContainer, build_api_container


@dataclass(frozen=True)
class AgentRunResult:
    session_id: str
    message: str
    thinking_summaries: list[str]
    tool_rows: list[str]
    final_answer: str
    raw_events: list[dict[str, object]]


def should_skip_manual_only_run(manual: bool, script_label: str) -> bool:
    if manual:
        return False
    print(f"[skip] {script_label} 属于低优先级的真实模型对话回归，默认不执行。")
    print("如需手动运行，请显式追加 --manual。")
    return True


def build_container() -> ApiContainer:
    return build_api_container(ROOT)


def run_agent_case(
    *,
    container: ApiContainer,
    session_id: str,
    message: str,
    clear_session: bool = True,
) -> AgentRunResult:
    service = container.get_agent_service()
    if clear_session:
        service.clear_session(session_id=session_id, context_override=None)

    thinking_summaries: list[str] = []
    tool_rows: list[str] = []
    final_answer = ""
    raw_events: list[dict[str, object]] = []

    for event in service.stream_with_context(
        session_id=session_id,
        user_message=message,
        context_override=None,
    ):
        raw_events.append({"type": event.type, "payload": event.payload})
        if event.type == "thinking_completed":
            summary = str(event.payload.get("summary", "")).strip()
            if summary:
                thinking_summaries.append(summary)
        elif event.type == "tool_completed":
            tool_rows.append(format_tool_row(event.payload))
        elif event.type == "answer_completed":
            final_answer = str(event.payload.get("message", "")).strip()

    return AgentRunResult(
        session_id=session_id,
        message=message,
        thinking_summaries=thinking_summaries,
        tool_rows=tool_rows,
        final_answer=final_answer,
        raw_events=raw_events,
    )


def format_tool_row(payload: dict[str, object]) -> str:
    tool_name = str(payload.get("tool_name", ""))
    status = str(payload.get("status", ""))
    detail = summarize_payload(tool_name, payload.get("payload"))
    return f"- {tool_name} [{status}] {detail}".rstrip()


def summarize_payload(tool_name: str, payload: object) -> str:
    if not isinstance(payload, dict):
        return ""

    if tool_name == "list_series_videos":
        videos = payload.get("videos")
        if isinstance(videos, list):
            titles = [
                str(item.get("title", "")).strip()
                for item in videos
                if isinstance(item, dict) and str(item.get("title", "")).strip()
            ]
            return f"视频数={len(titles)}; titles={titles}"
        return ""

    if tool_name in {"add_series_candidates", "replace_series_candidates", "view_series_candidates"}:
        buffer_items = payload.get("candidate_buffer")
        if isinstance(buffer_items, list):
            video_ids = extract_video_ids(buffer_items)
            return f"candidate_buffer={video_ids}"
        return ""

    if tool_name == "remove_series_candidates":
        buffer_items = payload.get("candidate_buffer")
        removed_items = payload.get("removed_videos")
        next_ids = extract_video_ids(buffer_items)
        removed_ids = extract_video_ids(removed_items)
        return f"removed={removed_ids}; candidate_buffer={next_ids}"

    if tool_name == "clear_series_candidates":
        return "candidate_buffer=[]"

    if tool_name == "get_video_summary":
        title = str(payload.get("title", "")).strip()
        chapters = payload.get("chapters")
        key_takeaways = payload.get("key_takeaways")
        chapter_count = len(chapters) if isinstance(chapters, list) else 0
        takeaway_count = len(key_takeaways) if isinstance(key_takeaways, list) else 0
        return f"title={title}; chapters={chapter_count}; key_takeaways={takeaway_count}"

    if tool_name == "get_video_tools":
        return f"video_id={payload.get('video_id', '')}"

    if tool_name == "get_video_transcript":
        segments = payload.get("segments")
        segment_count = len(segments) if isinstance(segments, list) else 0
        duration_seconds = payload.get("duration_seconds")
        return f"video_id={payload.get('video_id', '')}; segments={segment_count}; duration_seconds={duration_seconds}"

    if tool_name == "video_seek":
        return f"seek_seconds={payload.get('seek_seconds', '')}"

    return json.dumps(payload, ensure_ascii=False)


def extract_video_ids(raw_items: object) -> list[str]:
    if not isinstance(raw_items, list):
        return []
    return [
        str(item.get("video_id", "")).strip()
        for item in raw_items
        if isinstance(item, dict) and str(item.get("video_id", "")).strip()
    ]


def summarize_event_order(raw_events: list[dict[str, object]]) -> list[str]:
    order: list[str] = []
    for item in raw_events:
        event_type = str(item.get("type", "")).strip()
        if event_type in {"thinking_delta", "answer_delta"}:
            continue
        payload = item.get("payload")
        if event_type in {"tool_started", "tool_completed"} and isinstance(payload, dict):
            tool_name = str(payload.get("tool_name", "")).strip()
            order.append(f"{event_type}:{tool_name}")
            continue
        order.append(event_type)
    return order
