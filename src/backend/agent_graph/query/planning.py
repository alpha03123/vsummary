from __future__ import annotations

from backend.agent_graph.query.models import ExecutionDepth, SelectionMode, StructuredQueryPlan
from backend.agent_graph.runtime.state import AgentGraphState

CONTENT_DEPENDENT_ACTIONS = {"save_note"}


def build_structured_query_plan(
    *,
    state: AgentGraphState,
    current_instruction: str,
    decision_payload: dict[str, object],
) -> dict[str, object]:
    goal = str(decision_payload.get("goal", "")).strip()
    target_source = str(decision_payload.get("target_source", "")).strip()
    context_need = str(decision_payload.get("context_need", "")).strip()
    action_name = str(decision_payload.get("action_name", "")).strip()
    action_args = decision_payload.get("action_args", {})
    if not isinstance(action_args, dict):
        action_args = {}
    if action_name in CONTENT_DEPENDENT_ACTIONS and not str(action_args.get("note_content", "")).strip():
        goal = "action_after_content"

    candidate_video_ids = _normalize_video_ids(decision_payload.get("candidate_video_ids"))
    selected_videos = _normalize_selected_videos(decision_payload.get("selected_videos"))
    selection_mode = _normalize_selection_mode(decision_payload.get("selection_mode"))
    subplans = _normalize_subplans(decision_payload.get("subplans"))
    retrieval_tags = _normalize_retrieval_tags(decision_payload.get("retrieval_tags"), target_source=target_source)
    history_selected_videos = _normalize_selected_videos(state.get("history_selected_videos"))

    if state.get("scope_type") == "video":
        video_id = str(state.get("video_id", "")).strip()
        if video_id:
            if not candidate_video_ids:
                candidate_video_ids = [video_id]
            if not selected_videos:
                selected_videos = [
                    {
                        "video_id": video_id,
                        "reason_for_selection": "当前 video scope",
                    }
                ]
        if goal not in {"action", "meta_state"}:
            summary_subplan = {
                "target_video_ids": [video_id] if video_id else [],
                "depth": ExecutionDepth.SUMMARY.value,
                "query": current_instruction,
                "retrieval_tags": ["summary"],
            }
            if target_source == "summary":
                subplans = [summary_subplan]
            elif target_source == "transcript":
                subplans = [
                    {
                        "target_video_ids": [video_id] if video_id else [],
                        "depth": ExecutionDepth.VIDEO_RAG.value,
                        "query": current_instruction,
                        "retrieval_tags": _normalize_retrieval_tags(None, target_source=target_source),
                    }
                ]
            else:
                rag_tags = retrieval_tags or _normalize_retrieval_tags(None, target_source=target_source)
                subplans = [
                    summary_subplan,
                    {
                        "target_video_ids": [video_id] if video_id else [],
                        "depth": ExecutionDepth.VIDEO_RAG.value,
                        "query": current_instruction,
                        "retrieval_tags": rag_tags,
                    },
                ]

    if (
        state.get("scope_type") == "series"
        and selection_mode == SelectionMode.CARRY_FORWARD.value
        and history_selected_videos
    ):
        if not selected_videos:
            selected_videos = history_selected_videos
        if not candidate_video_ids:
            candidate_video_ids = [item["video_id"] for item in selected_videos]
        if not subplans and goal not in {"action", "meta_state"}:
            if target_source == "transcript":
                depth = ExecutionDepth.VIDEO_GRAPH.value
            else:
                depth = ExecutionDepth.SUMMARY.value
            subplans = [
                {
                    "target_video_ids": list(candidate_video_ids),
                    "depth": depth,
                    "query": current_instruction,
                    "retrieval_tags": retrieval_tags,
                }
            ]

    if goal not in {"action", "action_after_content", "meta_state"} and not subplans:
        if target_source == "transcript":
            depth = ExecutionDepth.VIDEO_GRAPH.value
        else:
            depth = ExecutionDepth.SUMMARY.value
        subplans = [
                {
                    "target_video_ids": list(candidate_video_ids),
                    "depth": depth,
                    "query": current_instruction,
                    "retrieval_tags": retrieval_tags,
                }
            ]

    return StructuredQueryPlan.model_validate(
        {
            "goal": goal,
            "target_source": target_source,
            "context_need": context_need,
            "reason": str(decision_payload.get("reason", "")).strip(),
            "action_name": action_name,
            "action_args": action_args,
            "candidate_video_ids": candidate_video_ids,
            "selected_videos": selected_videos,
            "selection_mode": selection_mode,
            "retrieval_tags": retrieval_tags,
            "subplans": subplans,
        }
    ).model_dump(mode="json")


def backfill_query_plan_targets(state: AgentGraphState, results: list[dict[str, object]]) -> None:
    query_plan = dict(state.get("query_plan", {}))
    if not query_plan:
        return
    video_ids: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        video_id = str(item.get("video_id", "")).strip()
        if video_id and video_id not in video_ids:
            video_ids.append(video_id)
    if not video_ids:
        return

    candidate_video_ids = list(query_plan.get("candidate_video_ids", []))
    if not candidate_video_ids:
        query_plan["candidate_video_ids"] = video_ids

    selected_videos = list(query_plan.get("selected_videos", []))
    if not selected_videos:
        query_plan["selected_videos"] = [
            {
                "video_id": video_id,
                "reason_for_selection": "retrieval 命中",
            }
            for video_id in video_ids
        ]

    subplans = query_plan.get("subplans", [])
    if isinstance(subplans, list) and subplans:
        first_subplan = subplans[0]
        if isinstance(first_subplan, dict) and not first_subplan.get("target_video_ids"):
            first_subplan["target_video_ids"] = video_ids

    state["query_plan"] = query_plan


def _normalize_video_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        video_id = item.strip()
        if video_id and video_id not in result:
            result.append(video_id)
    return result


def _normalize_selected_videos(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        video_id = str(item.get("video_id", "")).strip()
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        normalized.append(
            {
                "video_id": video_id,
                "reason_for_selection": str(item.get("reason_for_selection", "")).strip(),
            }
        )
    return normalized


def _normalize_selection_mode(value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in {SelectionMode.FRESH.value, SelectionMode.CARRY_FORWARD.value}:
            return normalized
    return SelectionMode.FRESH.value


def _normalize_subplans(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        target_video_ids = _normalize_video_ids(item.get("target_video_ids"))
        depth = str(item.get("depth", "")).strip()
        if depth not in {
            ExecutionDepth.SERIES_META.value,
            ExecutionDepth.SUMMARY.value,
            ExecutionDepth.VIDEO_GRAPH.value,
            ExecutionDepth.VIDEO_WORKFLOW.value,
            ExecutionDepth.VIDEO_RAG.value,
        }:
            continue
        query = str(item.get("query", "")).strip()
        if depth != ExecutionDepth.SERIES_META.value and not query:
            continue
        normalized.append(
            {
                "target_video_ids": target_video_ids,
                "depth": depth,
                "query": query,
                "retrieval_tags": _normalize_retrieval_tags(item.get("retrieval_tags"), target_source="all"),
            }
        )
    return normalized


def _normalize_retrieval_tags(value: object, *, target_source: str) -> list[str]:
    if isinstance(value, list):
        normalized = [
            str(item).strip()
            for item in value
            if isinstance(item, str) and str(item).strip()
        ]
        if normalized:
            return list(dict.fromkeys(normalized))
    if target_source == "summary":
        return ["summary"]
    if target_source == "transcript":
        return ["transcript"]
    return ["summary", "transcript", "notes", "cards"]
