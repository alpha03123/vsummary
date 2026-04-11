from __future__ import annotations

from typing import NotRequired, TypedDict


class AgentGraphState(TypedDict):
    session_id: str
    scope_type: str
    series_id: str
    video_id: NotRequired[str]
    user_message: str
    history_messages: NotRequired[list[dict[str, object]]]
    history_summary: NotRequired[str]
    tasks: NotRequired[list[dict[str, object]]]
    current_task_index: NotRequired[int]
    current_task: NotRequired[dict[str, object]]
    current_task_context: NotRequired[dict[str, object]]
    task_outputs: NotRequired[list[dict[str, object]]]
    query_plan: NotRequired[dict[str, object]]
    retrieval_queries: NotRequired[list[str]]
    retrieval_results: NotRequired[list[dict[str, object]]]
    meta_state: NotRequired[dict[str, object]]
    tool_results: NotRequired[list[dict[str, object]]]
    direct_response: NotRequired[str]
    assistant_message: NotRequired[str]
    history_summary_update: NotRequired[str]
    answer: NotRequired[str]
    error: NotRequired[str]
