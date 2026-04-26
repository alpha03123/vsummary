from __future__ import annotations

from collections.abc import Callable

from backend.agent_graph.query.models import ExecutionDepth
from backend.agent_graph.query.planning import backfill_query_plan_targets, build_structured_query_plan
from backend.agent_graph.runtime.state import AgentGraphState


def build_plan_node(*, classifier_program, compare_split_program, series_planner=None) -> Callable[[AgentGraphState], AgentGraphState]:
    def build_plan(state: AgentGraphState) -> AgentGraphState:
        current_instruction = str(state["user_message"])
        decision = classifier_program.run(
            user_message=current_instruction,
            scope_type=state["scope_type"],
            series_id=state["series_id"],
            video_id=state.get("video_id", ""),
            history_summary=str(state.get("dialog_history", state.get("history_summary", ""))),
            history_selected_videos=list(state.get("history_selected_videos", [])),
        )
        if (
            state.get("scope_type") == "series"
            and series_planner is not None
            and str(getattr(decision, "goal", "")).strip() not in {"action", "meta_state"}
        ):
            query_plan = series_planner.create_plan(
                user_message=current_instruction,
                series_id=state["series_id"],
                dialog_history=str(state.get("dialog_history", "")),
                history_messages=list(state.get("history_messages", [])),
                previous_selected_videos=list(state.get("history_selected_videos", [])),
            )
            next_state = dict(state)
            next_state["query_plan"] = query_plan
            next_state["current_subplan_index"] = -1
            next_state["current_subplan"] = {}
            next_state["retrieval_results"] = []
            next_state["meta_state"] = {}
            next_state["tool_results"] = []
            next_state["generated_content"] = ""
            return next_state
        query_plan = build_structured_query_plan(
            state=state,
            current_instruction=current_instruction,
            decision_payload=decision.model_dump(mode="json"),
        )
        if query_plan.get("goal") == "compare" and not query_plan.get("subplans"):
            split = compare_split_program.run(user_message=current_instruction)
            queries = list(split.queries)
            depth = ExecutionDepth.VIDEO_GRAPH.value if query_plan.get("target_source") == "transcript" else ExecutionDepth.SUMMARY.value
            query_plan["subplans"] = [
                {
                    "target_video_ids": list(query_plan.get("candidate_video_ids", [])),
                    "depth": depth,
                    "query": query,
                }
                for query in queries
            ]
        next_state = dict(state)
        next_state["query_plan"] = query_plan
        next_state["current_subplan_index"] = -1
        next_state["current_subplan"] = {}
        next_state["retrieval_results"] = []
        next_state["meta_state"] = {}
        next_state["tool_results"] = []
        next_state["generated_content"] = ""
        return next_state

    return build_plan


def build_advance_subplan_node() -> Callable[[AgentGraphState], AgentGraphState]:
    def advance_subplan(state: AgentGraphState) -> AgentGraphState:
        query_plan = dict(state.get("query_plan", {}))
        subplans = list(query_plan.get("subplans", []))
        next_index = int(state.get("current_subplan_index", -1)) + 1
        next_state = dict(state)
        if 0 <= next_index < len(subplans):
            next_state["current_subplan_index"] = next_index
            next_state["current_subplan"] = subplans[next_index]
        else:
            next_state["current_subplan"] = {}
        return next_state

    return advance_subplan



def build_execute_summary_node(*, retrieval_service) -> Callable[[AgentGraphState], AgentGraphState]:
    def execute_summary(state: AgentGraphState) -> AgentGraphState:
        current_subplan = dict(state.get("current_subplan", {}))
        query = str(current_subplan.get("query", state["user_message"])).strip() or state["user_message"]
        target_ids = [
            str(video_id).strip()
            for video_id in current_subplan.get("target_video_ids", [])
            if isinstance(video_id, str) and str(video_id).strip()
        ]
        if not target_ids:
            target_ids = [
                str(video_id).strip()
                for video_id in state.get("query_plan", {}).get("candidate_video_ids", [])
                if isinstance(video_id, str) and str(video_id).strip()
            ]

        items = _load_summary_items_from_state(state)
        if not items:
            responses: list[dict[str, object]] = []
            if target_ids:
                for video_id in target_ids:
                    responses.append(
                        retrieval_service.search(
                            scope_type="video",
                            series_id=state["series_id"],
                            video_id=video_id,
                            query=query,
                            target_source="summary",
                            source_tags=["summary"],
                            expand_context=False,
                            context_window_seconds=120,
                            max_hits=5,
                        )
                    )
            else:
                responses.append(
                    retrieval_service.search(
                        scope_type=state["scope_type"],
                        series_id=state["series_id"],
                        video_id=state.get("video_id", ""),
                        query=query,
                        target_source="summary",
                        source_tags=["summary"],
                        expand_context=False,
                        context_window_seconds=120,
                        max_hits=5,
                    )
                )

            items = []
            for response in responses:
                hits = response.get("hits", [])
                if not isinstance(hits, list):
                    continue
                items.extend(hit for hit in hits if isinstance(hit, dict))

        next_state = dict(state)
        next_state["retrieval_results"] = list(state.get("retrieval_results", [])) + [
            {
                "depth": ExecutionDepth.SUMMARY.value,
                "query": query,
                "items": items,
            }
        ]
        next_state["tool_results"] = _merge_tool_results(
            state,
            _build_summary_tool_results(state["series_id"], items),
        )
        backfill_query_plan_targets(next_state, items)
        return next_state

    return execute_summary


def build_execute_video_rag_node(*, retrieval_service) -> Callable[[AgentGraphState], AgentGraphState]:
    def execute_video_rag(state: AgentGraphState) -> AgentGraphState:
        current_subplan = dict(state.get("current_subplan", {}))
        query = str(current_subplan.get("query", state["user_message"])).strip() or state["user_message"]
        retrieval_tags = [
            str(tag).strip()
            for tag in current_subplan.get("retrieval_tags", [])
            if isinstance(tag, str) and str(tag).strip()
        ]
        target_ids = [
            str(video_id).strip()
            for video_id in current_subplan.get("target_video_ids", [])
            if isinstance(video_id, str) and str(video_id).strip()
        ] or [str(state.get("video_id", "")).strip()]

        responses: list[dict[str, object]] = []
        for video_id in target_ids:
            if not video_id:
                continue
            responses.append(
                retrieval_service.search(
                    scope_type="video",
                    series_id=state["series_id"],
                    video_id=video_id,
                    query=query,
                    target_source="all",
                    source_tags=retrieval_tags,
                    expand_context=True,
                    context_window_seconds=120,
                    max_hits=5,
                )
            )

        items: list[dict[str, object]] = []
        for response in responses:
            hits = response.get("hits", [])
            if not isinstance(hits, list):
                continue
            items.extend(hit for hit in hits if isinstance(hit, dict))

        next_state = dict(state)
        next_state["retrieval_results"] = list(state.get("retrieval_results", [])) + [
            {
                "depth": ExecutionDepth.VIDEO_RAG.value,
                "query": query,
                "retrieval_tags": retrieval_tags,
                "items": items,
            }
        ]
        next_state["tool_results"] = _merge_tool_results(
            state,
            _build_video_rag_tool_results(
                series_id=state["series_id"],
                retrieval_tags=retrieval_tags,
                items=items,
            ),
        )
        backfill_query_plan_targets(next_state, items)
        return next_state

    return execute_video_rag



def build_execute_video_graph_node(*, retrieval_service, pinpoint_service) -> Callable[[AgentGraphState], AgentGraphState]:
    def execute_video_graph(state: AgentGraphState) -> AgentGraphState:
        current_subplan = dict(state.get("current_subplan", {}))
        query = str(current_subplan.get("query", state["user_message"])).strip() or state["user_message"]
        target_ids = [
            str(video_id).strip()
            for video_id in current_subplan.get("target_video_ids", [])
            if isinstance(video_id, str) and str(video_id).strip()
        ]
        if not target_ids:
            discovery = retrieval_service.search(
                scope_type=state["scope_type"],
                series_id=state["series_id"],
                video_id=state.get("video_id", ""),
                query=query,
                target_source="transcript",
                expand_context=False,
                context_window_seconds=120,
                max_hits=5,
            )
            hits = discovery.get("hits", [])
            target_ids = []
            if isinstance(hits, list):
                for hit in hits:
                    if not isinstance(hit, dict):
                        continue
                    video_id = str(hit.get("video_id", "")).strip()
                    if video_id and video_id not in target_ids:
                        target_ids.append(video_id)

        items: list[dict[str, object]] = []
        tool_results: list[dict[str, object]] = []
        for video_id in target_ids[:3]:
            item, item_tool_results = pinpoint_service.locate(
                series_id=state["series_id"],
                video_id=video_id,
                query=query,
            )
            if isinstance(item, dict):
                if "source_type" not in item:
                    item = {**item, "source_type": "transcript_chunk"}
                items.append(item)
            if isinstance(item_tool_results, list):
                tool_results.extend(item_tool_results)

        next_state = dict(state)
        next_state["retrieval_results"] = list(state.get("retrieval_results", [])) + [
            {
                "depth": ExecutionDepth.VIDEO_GRAPH.value,
                "query": query,
                "items": items,
            }
        ]
        next_state["tool_results"] = _merge_tool_results(state, tool_results)
        backfill_query_plan_targets(next_state, items)
        return next_state

    return execute_video_graph


def build_execute_video_workflow_node(*, workflow_service) -> Callable[[AgentGraphState], AgentGraphState]:
    def execute_video_workflow(state: AgentGraphState) -> AgentGraphState:
        current_subplan = dict(state.get("current_subplan", {}))
        query = str(current_subplan.get("query", state["user_message"])).strip() or state["user_message"]
        target_ids = [
            str(video_id).strip()
            for video_id in current_subplan.get("target_video_ids", [])
            if isinstance(video_id, str) and str(video_id).strip()
        ]
        if not target_ids:
            target_ids = [
                str(video_id).strip()
                for video_id in state.get("query_plan", {}).get("candidate_video_ids", [])
                if isinstance(video_id, str) and str(video_id).strip()
            ]
        items: list[dict[str, object]] = []
        tool_results: list[dict[str, object]] = []
        for video_id in target_ids[:2]:
            item, item_tool_results = workflow_service.extract(
                series_id=state["series_id"],
                video_id=video_id,
                query=query,
            )
            if isinstance(item, dict):
                if "source_type" not in item:
                    item = {**item, "source_type": "workflow_window"}
                items.append(item)
            if isinstance(item_tool_results, list):
                tool_results.extend(item_tool_results)
        next_state = dict(state)
        next_state["retrieval_results"] = list(state.get("retrieval_results", [])) + [
            {
                "depth": ExecutionDepth.VIDEO_WORKFLOW.value,
                "query": query,
                "items": items,
            }
        ]
        next_state["tool_results"] = _merge_tool_results(state, tool_results)
        backfill_query_plan_targets(next_state, items)
        return next_state

    return execute_video_workflow


def build_execute_series_meta_node(*, meta_state_reader) -> Callable[[AgentGraphState], AgentGraphState]:
    def execute_series_meta(state: AgentGraphState) -> AgentGraphState:
        query = str(dict(state.get("current_subplan", {})).get("query", state["user_message"])).strip() or state["user_message"]
        meta = meta_state_reader.read(
            scope_type="series",
            series_id=state["series_id"],
            video_id="",
        )
        next_state = dict(state)
        next_state["retrieval_results"] = list(state.get("retrieval_results", [])) + [
            {
                "depth": ExecutionDepth.SERIES_META.value,
                "query": query,
                **meta,
            }
        ]
        return next_state

    return execute_series_meta


def build_read_meta_state_node(*, meta_state_reader) -> Callable[[AgentGraphState], AgentGraphState]:
    def read_meta_state(state: AgentGraphState) -> AgentGraphState:
        meta_state = meta_state_reader.read(
            scope_type=state["scope_type"],
            series_id=state["series_id"],
            video_id=state.get("video_id", ""),
        )
        next_state = dict(state)
        next_state["meta_state"] = meta_state
        next_state["retrieval_results"] = []
        return next_state

    return read_meta_state


def build_dispatch_action_node(*, action_dispatcher) -> Callable[[AgentGraphState], AgentGraphState]:
    def dispatch_action(state: AgentGraphState) -> AgentGraphState:
        plan = dict(state.get("query_plan", {}))
        action_args = dict(plan.get("action_args", {})) if isinstance(plan.get("action_args", {}), dict) else {}
        if str(plan.get("action_name", "")) == "save_note":
            action_args = _resolve_save_note_action_args(state=state, action_args=action_args)
        result = action_dispatcher.dispatch(
            scope_type=state["scope_type"],
            series_id=state["series_id"],
            video_id=state.get("video_id", ""),
            action_name=str(plan.get("action_name", "")),
            action_args=action_args,
        )
        next_state = dict(state)
        action_message = str(result.get("message", "")).strip()
        tool_results = result.get("tool_results", [])
        next_state["tool_results"] = _merge_tool_results(
            state,
            list(tool_results) if isinstance(tool_results, list) else [],
        )
        if str(plan.get("goal", "")).strip() != "action_after_content":
            next_state["task_outputs"] = list(state.get("task_outputs", [])) + [
                {
                    "kind": "action",
                    "value": action_message,
                }
            ]
        return next_state

    return dispatch_action


def build_answer_node(*, answer_program, note_program, action_reply_program, series_aggregator=None) -> Callable[[AgentGraphState], AgentGraphState]:
    def answer(state: AgentGraphState) -> AgentGraphState:
        goal = str(dict(state.get("query_plan", {})).get("goal", "")).strip()
        if goal == "action_after_content":
            generated_content = synthesize_note_content_text(
                state,
                note_program=note_program,
            )
            reply_text = synthesize_action_after_content_reply_text(
                state,
                generated_content=generated_content,
                action_reply_program=action_reply_program,
            )
            next_state = append_generated_content_to_state(state, generated_content)
            return append_answer_to_state(next_state, reply_text)
        answer_text = synthesize_answer_text(
            state,
            answer_program=answer_program,
            series_aggregator=series_aggregator,
        )
        return append_answer_to_state(state, answer_text)

    return answer

def synthesize_answer_text(
    state: AgentGraphState,
    *,
    answer_program,
    series_aggregator=None,
    debug_trace: dict[str, object] | None = None,
) -> str:
    if should_use_series_aggregator(state, series_aggregator):
        return series_aggregator.run(
            user_message=state["user_message"],
            query_plan=dict(state.get("query_plan", {})),
            execution_results=list(state.get("retrieval_results", [])),
            tool_results=list(state.get("tool_results", [])),
            dialog_history=str(state.get("dialog_history", "")),
            history_messages=list(state.get("history_messages", [])),
            debug_trace=debug_trace,
        )
    return answer_program.run(
        user_message=state["user_message"],
        retrieval_results=_project_answer_evidence(list(state.get("retrieval_results", []))),
        meta_state=state.get("meta_state"),
    )


def append_answer_to_state(state: AgentGraphState, answer_text: str) -> AgentGraphState:
    next_state = dict(state)
    next_state["answer"] = answer_text
    next_state["task_outputs"] = list(state.get("task_outputs", [])) + [
        {"kind": "answer", "value": answer_text}
    ]
    return next_state


def append_generated_content_to_state(state: AgentGraphState, generated_content: str) -> AgentGraphState:
    next_state = dict(state)
    next_state["generated_content"] = generated_content
    return next_state


def finalize_state(state: AgentGraphState) -> AgentGraphState:
    outputs = list(state.get("task_outputs", []))
    fragments: list[str] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value", "")).strip()
        if value:
            fragments.append(value)
    next_state = dict(state)
    next_state["assistant_message"] = "\n".join(fragments).strip()
    goal = str(dict(state.get("query_plan", {})).get("goal", "")).strip()
    if goal != "action_after_content" and not next_state.get("answer"):
        next_state["answer"] = next_state["assistant_message"]
    return next_state


def apply_memory_update(state: AgentGraphState, **_) -> AgentGraphState:
    user_message = str(state.get("user_message", "")).strip()
    assistant_message = str(state.get("assistant_message", state.get("answer", ""))).strip()
    prior = str(state.get("history_summary", "")).strip()
    turn = f"User: {user_message}\nAssistant: {assistant_message}".strip()
    updated = f"{prior}\n\n{turn}".strip() if prior else turn
    next_state = dict(state)
    next_state["history_summary_update"] = updated
    return next_state


def should_use_series_aggregator(state: AgentGraphState, series_aggregator) -> bool:
    if series_aggregator is None:
        return False
    if str(state.get("scope_type", "")).strip() != "series":
        return False
    goal = str(dict(state.get("query_plan", {})).get("goal", "")).strip()
    return goal not in {"action", "meta_state"}


def synthesize_note_content_text(
    state: AgentGraphState,
    *,
    note_program,
) -> str:
    return note_program.run(
        user_message=state["user_message"],
        retrieval_results=_project_answer_evidence(list(state.get("retrieval_results", []))),
        meta_state=state.get("meta_state"),
    )


def synthesize_action_after_content_reply_text(
    state: AgentGraphState,
    *,
    generated_content: str,
    action_reply_program,
) -> str:
    return action_reply_program.run(
        user_message=state["user_message"],
        action_name=str(dict(state.get("query_plan", {})).get("action_name", "")).strip(),
        generated_content=generated_content,
    )


def _build_summary_tool_results(series_id: str, items: list[dict[str, object]]) -> list[dict[str, object]]:
    tool_results: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in items:
        video_id = str(item.get("video_id", "")).strip()
        title = str(item.get("title", "")).strip()
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        tool_results.append(
            {
                "tool_name": "get_video_summary",
                "status": "ok",
                "payload": {
                    "series_id": series_id,
                    "video_id": video_id,
                    "title": title,
                    "generated": True,
                },
            }
        )
    return tool_results


def _build_video_rag_tool_results(
    *,
    series_id: str,
    retrieval_tags: list[str],
    items: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not items:
        return []

    transcript_hits = [
        item for item in items
        if item.get("source_family") == "transcript" or item.get("source_type") == "transcript_chunk"
    ]
    summary_hits = [
        item for item in items
        if item.get("source_family") == "summary" or item.get("source_type") == "summary"
    ]
    selected_hits = transcript_hits or summary_hits or items
    first = selected_hits[0]
    tool_name = "get_video_transcript" if transcript_hits else "get_video_summary"
    return [
        {
            "tool_name": tool_name,
            "status": "ok",
            "payload": {
                "series_id": series_id,
                "video_id": first.get("video_id", ""),
                "title": first.get("title", ""),
                "retrieval_tags": retrieval_tags,
                "result_count": len(selected_hits),
            },
        }
    ]


def _resolve_save_note_action_args(*, state: AgentGraphState, action_args: dict[str, object]) -> dict[str, object]:
    note_title = str(action_args.get("note_title", "")).strip()
    note_content = str(action_args.get("note_content", "")).strip()
    if note_title and note_content:
        return action_args
    generated_content = str(state.get("generated_content", "")).strip()
    if generated_content:
        return {
            "note_title": note_title or "总结",
            "note_content": note_content or generated_content,
        }
    raise ValueError("save_note 缺少 note_content，且当前状态中没有 generated_content。")


def _merge_tool_results(state: AgentGraphState, additional: list[dict[str, object]]) -> list[dict[str, object]]:
    merged = list(state.get("tool_results", [])) if isinstance(state.get("tool_results"), list) else []
    merged.extend(additional)
    return merged


def _project_answer_evidence(results: list[dict[str, object]]) -> list[dict[str, object]]:
    projected: list[dict[str, object]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        depth = str(item.get("depth", "")).strip()
        if depth == ExecutionDepth.SUMMARY.value:
            items = item.get("items", [])
            if isinstance(items, list):
                for summary_item in items:
                    if isinstance(summary_item, dict):
                        projected.append(summary_item)
            continue
        if depth == ExecutionDepth.VIDEO_GRAPH.value:
            items = item.get("items", [])
            if isinstance(items, list):
                for graph_item in items:
                    if not isinstance(graph_item, dict):
                        continue
                    slots = graph_item.get("slots", [])
                    if isinstance(slots, list) and slots:
                        for slot in slots:
                            if not isinstance(slot, dict):
                                continue
                            best_match = slot.get("best_match")
                            if not isinstance(best_match, dict):
                                continue
                            projected.append(
                                {
                                    "video_id": graph_item.get("video_id", ""),
                                    "title": graph_item.get("title", ""),
                                    "source_type": "transcript_chunk",
                                    "snippet": best_match.get("text", ""),
                                    "start_seconds": best_match.get("start_seconds"),
                                    "end_seconds": best_match.get("end_seconds"),
                                    "slot_label": slot.get("label", ""),
                                    "slot_query": slot.get("query", ""),
                                }
                            )
                        continue
                    best_match = graph_item.get("best_match")
                    if isinstance(best_match, dict):
                        projected.append(
                            {
                                "video_id": graph_item.get("video_id", ""),
                                "title": graph_item.get("title", ""),
                                "source_type": "transcript_chunk",
                                "snippet": best_match.get("text", ""),
                                "start_seconds": best_match.get("start_seconds"),
                                "end_seconds": best_match.get("end_seconds"),
                            }
                        )
            continue
        if depth == ExecutionDepth.VIDEO_RAG.value:
            items = item.get("items", [])
            if isinstance(items, list):
                for rag_item in items:
                    if isinstance(rag_item, dict):
                        projected.append(rag_item)
            continue
        projected.append(item)
    return projected


def _load_summary_items_from_state(state: AgentGraphState) -> list[dict[str, object]]:
    evidence_history = state.get("evidence_history", {})
    if not isinstance(evidence_history, dict):
        return []
    video_summary = evidence_history.get("video_summary", {})
    if not isinstance(video_summary, dict):
        return []
    summary_payload = video_summary.get("summary", {})
    if not isinstance(summary_payload, dict):
        return []
    video_id = str(video_summary.get("video_id", "")).strip() or str(state.get("video_id", "")).strip()
    title = str(video_summary.get("title", "")).strip()
    items: list[dict[str, object]] = []
    summary_text = "\n".join(
        part
        for part in [
            str(summary_payload.get("one_sentence_summary", "")).strip(),
            str(summary_payload.get("core_problem", "")).strip(),
            "\n".join(
                item.strip()
                for item in summary_payload.get("key_takeaways", [])
                if isinstance(item, str) and item.strip()
            ),
        ]
        if part
    ).strip()
    if summary_text:
        items.append(
            {
                "video_id": video_id,
                "title": title,
                "source_type": "summary",
                "source_family": "summary",
                "snippet": summary_text,
                "one_sentence_summary": str(summary_payload.get("one_sentence_summary", "")).strip(),
                "core_problem": str(summary_payload.get("core_problem", "")).strip(),
                "key_takeaways": list(summary_payload.get("key_takeaways", [])),
            }
        )
    return items
