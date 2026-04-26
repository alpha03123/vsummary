from __future__ import annotations

import json
from collections.abc import Iterator

from backend.agent.ports import ChatGateway
from backend.agent.schemas.chat_stream import ChatCompletionStreamChunk
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.evidence.citations import build_citations_from_graph_result


class SeriesAggregator:
    def __init__(self, *, gateway: ChatGateway) -> None:
        self._gateway = gateway

    def run(
        self,
        *,
        user_message: str,
        query_plan: dict[str, object],
        execution_results: list[dict[str, object]],
        tool_results: list[dict[str, object]],
        dialog_history: str = "",
        history_messages: list[dict[str, object]] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> str:
        messages = self.build_messages(
            user_message=user_message,
            query_plan=query_plan,
            execution_results=execution_results,
            tool_results=tool_results,
            dialog_history=dialog_history,
            history_messages=history_messages,
            debug_trace=debug_trace,
        )
        return self._gateway.create_text_completion(messages).strip()

    def stream(
        self,
        *,
        user_message: str,
        query_plan: dict[str, object],
        execution_results: list[dict[str, object]],
        tool_results: list[dict[str, object]],
        dialog_history: str = "",
        history_messages: list[dict[str, object]] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> Iterator[ChatCompletionStreamChunk]:
        messages = self.build_messages(
            user_message=user_message,
            query_plan=query_plan,
            execution_results=execution_results,
            tool_results=tool_results,
            dialog_history=dialog_history,
            history_messages=history_messages,
            debug_trace=debug_trace,
        )
        return self._gateway.create_text_completion_stream_with_metadata(messages)

    def build_messages(
        self,
        *,
        user_message: str,
        query_plan: dict[str, object],
        execution_results: list[dict[str, object]],
        tool_results: list[dict[str, object]],
        dialog_history: str = "",
        history_messages: list[dict[str, object]] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> list[AgentChatMessage]:
        if not execution_results:
            raise RuntimeError("series query returned no evidence")
        curated_execution_results = _curate_execution_results(
            query_plan=query_plan,
            execution_results=execution_results,
        )
        citations = build_citations_from_graph_result({"retrieval_results": curated_execution_results})
        citation_block = _render_citation_briefs(citations)
        execution_block = _render_execution_results(curated_execution_results)
        history_block = dialog_history.strip()
        if not history_block and history_messages:
            history_block = "\n".join(
                f"{str(item.get('role', '')).strip()}: {str(item.get('content', '')).strip()}"
                for item in history_messages
                if isinstance(item, dict) and str(item.get("content", "")).strip()
            ).strip()
        messages = [
            AgentChatMessage(
                role="system",
                content=(
                    "你是学习助手。请严格基于执行结果和计划里的 selected_videos 回答。"
                    "不要编造不存在的视频、时间点或课程内容。"
                    "如果证据不足，要明确说明不足。"
                    "优先直接回答用户问题，语气自然，不要写成检索器回执。"
                    "如果提供了 citations，请在需要引用证据的句子后用 [1]、[2] 这种递增编号标注。"
                    "不要在正文直接输出 video_id、start_seconds、end_seconds、matched_text 这类内部字段。"
                    "只有在用户明确追问边界时，才解释哪些内容被排除以及原因。"
                    "可以引用 citation 对应的证据，但把具体跳转细节留给 citations 元数据，不要写进正文。"
                ),
            ),
            AgentChatMessage(
                role="user",
                content=(
                    f"对话记忆:\n{history_block or '(none)'}\n\n"
                    f"计划:\n{json.dumps(query_plan, ensure_ascii=False, indent=2)}\n\n"
                    f"执行结果:\n{execution_block}\n\n"
                    f"可用引用:\n{citation_block}\n\n"
                    f"用户问题:\n{user_message}"
                ),
            ),
        ]
        if debug_trace is not None:
            debug_trace["series_aggregator"] = {
                "messages": [message.model_dump(mode="json") for message in messages],
                "curated_execution_results": curated_execution_results,
                "citations": [item.model_dump(mode="json") for item in citations],
                "tool_results": tool_results,
            }
        return messages


def _curate_execution_results(
    *,
    query_plan: dict[str, object],
    execution_results: list[dict[str, object]],
) -> list[dict[str, object]]:
    depths = {
        str(item.get("depth", "")).strip()
        for item in execution_results
        if isinstance(item, dict)
    }
    if not depths or "video_graph" in depths:
        return execution_results
    curated_results: list[dict[str, object]] = []
    summary_items: list[dict[str, object]] = []
    for item in execution_results:
        if not isinstance(item, dict):
            continue
        if str(item.get("depth", "")).strip() == "summary":
            for summary_item in item.get("items", []):
                if isinstance(summary_item, dict):
                    summary_items.append(summary_item)
            continue
        curated_results.append(item)
    selected_summary_items = _select_summary_items(
        candidate_video_ids=query_plan.get("candidate_video_ids", []),
        summary_items=summary_items,
    )
    if selected_summary_items:
        curated_results.append(
            {
                "depth": "summary",
                "query": _first_summary_query(execution_results),
                "items": selected_summary_items,
            }
        )
    return curated_results


def _select_summary_items(*, candidate_video_ids: object, summary_items: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped_by_video_id: dict[str, dict[str, object]] = {}
    for item in summary_items:
        video_id = str(item.get("video_id", "")).strip()
        if not video_id or video_id in deduped_by_video_id:
            continue
        deduped_by_video_id[video_id] = item
    if not deduped_by_video_id:
        return []
    if isinstance(candidate_video_ids, list) and candidate_video_ids:
        selected = [
            deduped_by_video_id[video_id]
            for video_id in candidate_video_ids
            if isinstance(video_id, str) and video_id in deduped_by_video_id
        ]
        if selected:
            return selected
    return list(deduped_by_video_id.values())


def _first_summary_query(execution_results: list[dict[str, object]]) -> str:
    for item in execution_results:
        if isinstance(item, dict) and str(item.get("depth", "")).strip() == "summary":
            return str(item.get("query", "")).strip()
    return ""


def _render_execution_results(execution_results: list[dict[str, object]]) -> str:
    if not execution_results:
        return "(none)"
    blocks: list[str] = []
    for index, item in enumerate(execution_results, start=1):
        if not isinstance(item, dict):
            continue
        depth = str(item.get("depth", "")).strip()
        query = str(item.get("query", "")).strip()
        if depth == "summary":
            lines = [f"[{index}] depth=summary", f"query={query}"]
            for summary_index, summary_item in enumerate(item.get("items", []), start=1):
                if not isinstance(summary_item, dict):
                    continue
                lines.extend(
                    [
                        f"  - item[{summary_index}] video_id={summary_item.get('video_id', '')}; title={summary_item.get('title', '')}",
                        f"    one_sentence_summary={summary_item.get('one_sentence_summary', '')}",
                        f"    core_problem={summary_item.get('core_problem', '')}",
                        f"    snippet={summary_item.get('snippet', '')}",
                    ]
                )
            blocks.append("\n".join(lines))
            continue
        if depth == "video_graph":
            lines = [f"[{index}] depth=video_graph", f"query={query}"]
            for item_index, graph_item in enumerate(item.get("items", []), start=1):
                if not isinstance(graph_item, dict):
                    continue
                lines.append(
                    f"  - item[{item_index}] video_id={graph_item.get('video_id', '')}; title={graph_item.get('title', '')}; transcript_missing={graph_item.get('transcript_missing', False)}"
                )
                slots = graph_item.get("slots", [])
                if isinstance(slots, list):
                    for slot_index, slot in enumerate(slots, start=1):
                        if not isinstance(slot, dict):
                            continue
                        lines.append(f"    slot[{slot_index}].label={slot.get('label', '')}")
                        lines.append(f"    slot[{slot_index}].query={slot.get('query', '')}")
                        best_match = slot.get("best_match")
                        if isinstance(best_match, dict):
                            lines.extend(
                                [
                                    f"    slot[{slot_index}].best_match.start_seconds={best_match.get('start_seconds', '')}",
                                    f"    slot[{slot_index}].best_match.end_seconds={best_match.get('end_seconds', '')}",
                                    f"    slot[{slot_index}].best_match.text={best_match.get('text', '')}",
                                ]
                            )
                continue_best = graph_item.get("best_match")
                if isinstance(continue_best, dict):
                    lines.extend(
                        [
                            f"    best_match.start_seconds={continue_best.get('start_seconds', '')}",
                            f"    best_match.end_seconds={continue_best.get('end_seconds', '')}",
                            f"    best_match.text={continue_best.get('text', '')}",
                        ]
                    )
            blocks.append("\n".join(lines))
            continue
        if depth == "video_workflow":
            lines = [f"[{index}] depth=video_workflow", f"query={query}"]
            for item_index, workflow_item in enumerate(item.get("items", []), start=1):
                if not isinstance(workflow_item, dict):
                    continue
                lines.append(
                    f"  - item[{item_index}] video_id={workflow_item.get('video_id', '')}; title={workflow_item.get('title', '')}; transcript_missing={workflow_item.get('transcript_missing', False)}"
                )
                best_window = workflow_item.get("best_window")
                if isinstance(best_window, dict):
                    lines.extend(
                        [
                            f"    best_window.start_seconds={best_window.get('start_seconds', '')}",
                            f"    best_window.end_seconds={best_window.get('end_seconds', '')}",
                            f"    best_window.text={best_window.get('text', '')}",
                        ]
                    )
                windows = workflow_item.get("windows", [])
                if isinstance(windows, list):
                    for window_index, window in enumerate(windows, start=1):
                        if not isinstance(window, dict):
                            continue
                        lines.extend(
                            [
                                f"    window[{window_index}].start_seconds={window.get('start_seconds', '')}",
                                f"    window[{window_index}].end_seconds={window.get('end_seconds', '')}",
                                f"    window[{window_index}].text={window.get('text', '')}",
                            ]
                        )
            blocks.append("\n".join(lines))
            continue
        blocks.append(json.dumps(item, ensure_ascii=False, indent=2))
    return "\n\n".join(blocks) if blocks else "(none)"


def _render_citation_briefs(citations: list[object]) -> str:
    if not citations:
        return "(none)"
    lines: list[str] = []
    for citation in citations:
        if not hasattr(citation, "slots"):
            continue
        slots = list(getattr(citation, "slots", []))
        if not slots:
            continue
        slot_one = next((slot for slot in slots if getattr(slot, "slot", 0) == 1), slots[0])
        target_type = getattr(slot_one, "target_type", "")
        if target_type == "video":
            lines.append(
                f"[{getattr(citation, 'id', '')}] transcript | label={getattr(citation, 'label', '')} | "
                f"time={getattr(slot_one, 'start_seconds', None)}-{getattr(slot_one, 'end_seconds', None)} | "
                f"text={_first_slot_text(slots)}"
            )
            continue
        lines.append(
            f"[{getattr(citation, 'id', '')}] {getattr(citation, 'source_type', '')} | "
            f"label={getattr(citation, 'label', '')} | text={getattr(slot_one, 'text', '') or ''}"
        )
    return "\n".join(lines) if lines else "(none)"


def _first_slot_text(slots: list[object]) -> str:
    for slot in slots:
        text = getattr(slot, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""
