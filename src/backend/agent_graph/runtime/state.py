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
    history_selected_videos: NotRequired[list[dict[str, object]]]
    current_subplan_index: NotRequired[int]
    current_subplan: NotRequired[dict[str, object]]
    task_outputs: NotRequired[list[dict[str, object]]]
    query_plan: NotRequired[dict[str, object]]
    retrieval_results: NotRequired[list[dict[str, object]]]
    meta_state: NotRequired[dict[str, object]]
    tool_results: NotRequired[list[dict[str, object]]]
    assistant_message: NotRequired[str]
    history_summary_update: NotRequired[str]
    answer: NotRequired[str]
    generated_content: NotRequired[str]
    error: NotRequired[str]
