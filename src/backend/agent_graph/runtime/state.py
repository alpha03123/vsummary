from __future__ import annotations

from typing import NotRequired, TypedDict


class AgentGraphState(TypedDict):
    session_id: str
    scope_type: str
    series_id: str
    video_id: NotRequired[str]
    user_message: str
    dialog_history: NotRequired[str]
    evidence_history: NotRequired[dict[str, object]]
    history_messages: NotRequired[list[dict[str, object]]]
    history_summary: NotRequired[str]
    task_outputs: NotRequired[list[dict[str, object]]]
    query_understanding: NotRequired[dict[str, object]]
    series_catalog: NotRequired[dict[str, object]]
    retrieval_request: NotRequired[dict[str, object]]
    retrieval_results: NotRequired[list[dict[str, object]]]
    answer_payload: NotRequired[dict[str, object]]
    tool_calls: NotRequired[list[dict[str, object]]]
    tool_results: NotRequired[list[dict[str, object]]]
    action_summary: NotRequired[str]
    video_context_mode: NotRequired[str]
    video_summary_included: NotRequired[bool]
    assistant_message: NotRequired[str]
    history_summary_update: NotRequired[str]
    answer: NotRequired[str]
    error: NotRequired[str]
