from __future__ import annotations

from collections.abc import Callable

from backend.agent_graph.state import AgentGraphState


def build_decompose_node(*, decomposer_program) -> Callable[[AgentGraphState], AgentGraphState]:
    def decompose(state: AgentGraphState) -> AgentGraphState:
        decision = decomposer_program.run(
            user_message=state["user_message"],
            scope_type=state["scope_type"],
            series_id=state["series_id"],
            video_id=state.get("video_id", ""),
        )
        next_state = dict(state)
        task_payloads = [task.model_dump(mode="json") for task in decision.tasks]
        if not task_payloads:
            task_payloads = [
                {
                    "task_id": "task-1",
                    "instruction": state["user_message"],
                    "depends_on": [],
                    "kind_hint": "",
                }
            ]
        next_state["tasks"] = task_payloads
        next_state["current_task_index"] = 0
        next_state["current_task"] = _select_next_ready_task(task_payloads, [])
        next_state["current_task_context"] = _build_task_context(next_state["current_task"], [])
        next_state["task_outputs"] = []
        return next_state

    return decompose


def build_advance_task_node() -> Callable[[AgentGraphState], AgentGraphState]:
    def advance_task(state: AgentGraphState) -> AgentGraphState:
        tasks = list(state.get("tasks", []))
        outputs = list(state.get("task_outputs", []))
        completed_ids = [
            str(item.get("task_id", "")).strip()
            for item in outputs
            if isinstance(item, dict) and str(item.get("task_id", "")).strip()
        ]
        next_task = _select_next_ready_task(tasks, completed_ids)
        next_state = dict(state)
        if next_task:
            next_state["current_task"] = next_task
            next_state["current_task_index"] = _task_index(tasks, next_task)
            next_state["current_task_context"] = _build_task_context(next_task, outputs)
            next_state["query_plan"] = {}
            next_state["retrieval_queries"] = []
            next_state["retrieval_results"] = []
            next_state["meta_state"] = {}
            next_state["direct_response"] = ""
        else:
            next_state["current_task"] = {}
        return next_state

    return advance_task


def build_classify_node(*, classifier_program) -> Callable[[AgentGraphState], AgentGraphState]:
    def classify(state: AgentGraphState) -> AgentGraphState:
        current_task = dict(state.get("current_task", {}))
        current_instruction = str(current_task.get("instruction", state["user_message"]))
        decision = classifier_program.run(
            user_message=current_instruction,
            scope_type=state["scope_type"],
            series_id=state["series_id"],
            video_id=state.get("video_id", ""),
        )
        next_state = dict(state)
        next_state["query_plan"] = decision.model_dump(mode="json")
        return next_state

    return classify


def build_split_compare_node(*, compare_split_program) -> Callable[[AgentGraphState], AgentGraphState]:
    def split_compare(state: AgentGraphState) -> AgentGraphState:
        plan = dict(state.get("query_plan", {}))
        if plan.get("goal") != "compare":
            next_state = dict(state)
            next_state["retrieval_queries"] = [state["user_message"]]
            return next_state
        split = compare_split_program.run(user_message=state["user_message"])
        next_state = dict(state)
        next_state["retrieval_queries"] = list(split.queries)
        return next_state

    return split_compare


def build_retrieve_node(*, retrieval_service) -> Callable[[AgentGraphState], AgentGraphState]:
    def retrieve(state: AgentGraphState) -> AgentGraphState:
        plan = dict(state.get("query_plan", {}))
        queries = list(state.get("retrieval_queries", [])) or [state["user_message"]]
        responses = [
            retrieval_service.search(
                scope_type=state["scope_type"],
                series_id=state["series_id"],
                video_id=state.get("video_id", ""),
                query=query,
                target_source=str(plan.get("target_source", "all")),
                expand_context=str(plan.get("context_need", "chunk")) != "continuous",
                context_window_seconds=120,
                max_hits=5,
            )
            for query in queries
        ]
        results: list[dict[str, object]] = []
        for response in responses:
            hits = response.get("hits", [])
            if not isinstance(hits, list):
                continue
            for hit in hits:
                if isinstance(hit, dict):
                    results.append(dict(hit))
        next_state = dict(state)
        next_state["retrieval_results"] = results
        return next_state

    return retrieve


def build_read_meta_state_node(*, meta_state_reader) -> Callable[[AgentGraphState], AgentGraphState]:
    def read_meta_state(state: AgentGraphState) -> AgentGraphState:
        meta_state = meta_state_reader.read(
            scope_type=state["scope_type"],
            series_id=state["series_id"],
            video_id=state.get("video_id", ""),
        )
        next_state = dict(state)
        next_state["meta_state"] = meta_state
        next_state["retrieval_results"] = [meta_state]
        next_state["task_outputs"] = list(state.get("task_outputs", [])) + [
            {"task_id": dict(state.get("current_task", {})).get("task_id", ""), "kind": "meta_state", "value": meta_state}
        ]
        return next_state

    return read_meta_state


def build_dispatch_action_node(*, action_dispatcher) -> Callable[[AgentGraphState], AgentGraphState]:
    def dispatch_action(state: AgentGraphState) -> AgentGraphState:
        plan = dict(state.get("query_plan", {}))
        task_context = dict(state.get("current_task_context", {}))
        action_args = dict(plan.get("action_args", {})) if isinstance(plan.get("action_args", {}), dict) else {}
        if str(plan.get("action_name", "")) == "save_note" and task_context.get("latest_answer"):
            action_args = {
                "note_title": action_args.get("note_title", "总结"),
                "note_content": action_args.get("note_content", task_context["latest_answer"]),
            }
        result = action_dispatcher.dispatch(
            scope_type=state["scope_type"],
            series_id=state["series_id"],
            video_id=state.get("video_id", ""),
            action_name=str(plan.get("action_name", "")),
            action_args=action_args,
        )
        next_state = dict(state)
        next_state["direct_response"] = str(result.get("direct_response", "")).strip()
        tool_results = result.get("tool_results", [])
        next_state["tool_results"] = list(tool_results) if isinstance(tool_results, list) else []
        next_state["task_outputs"] = list(state.get("task_outputs", [])) + [
            {
                "task_id": dict(state.get("current_task", {})).get("task_id", ""),
                "kind": "action",
                "value": next_state["direct_response"],
            }
        ]
        return next_state

    return dispatch_action


def build_answer_node(*, answer_program) -> Callable[[AgentGraphState], AgentGraphState]:
    def answer(state: AgentGraphState) -> AgentGraphState:
        current_task = dict(state.get("current_task", {}))
        current_instruction = str(current_task.get("instruction", state["user_message"]))
        answer_text = answer_program.run(
            user_message=current_instruction,
            retrieval_results=list(state.get("retrieval_results", [])),
            meta_state=state.get("meta_state"),
        )
        next_state = dict(state)
        next_state["answer"] = answer_text
        next_state["task_outputs"] = list(state.get("task_outputs", [])) + [
            {"task_id": current_task.get("task_id", ""), "kind": "answer", "value": answer_text}
        ]
        return next_state

    return answer


def build_finalize_node() -> Callable[[AgentGraphState], AgentGraphState]:
    def finalize(state: AgentGraphState) -> AgentGraphState:
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
        if not next_state.get("answer"):
            next_state["answer"] = next_state["assistant_message"]
        return next_state

    return finalize


def build_update_memory_node(*, memory_update_program) -> Callable[[AgentGraphState], AgentGraphState]:
    def update_memory(state: AgentGraphState) -> AgentGraphState:
        next_state = dict(state)
        next_state["history_summary_update"] = memory_update_program.run(
            history_summary=str(state.get("history_summary", "")),
            user_message=state["user_message"],
            assistant_message=str(state.get("assistant_message", state.get("answer", ""))),
            task_outputs=list(state.get("task_outputs", [])),
        )
        return next_state

    return update_memory


def _build_task_context(task: dict[str, object], task_outputs: list[dict[str, object]]) -> dict[str, object]:
    depends_on = task.get("depends_on", [])
    if not isinstance(depends_on, list):
        return {}
    related = [item for item in task_outputs if isinstance(item, dict) and item.get("task_id") in depends_on]
    latest_answer = ""
    if related:
        for item in reversed(related):
            if str(item.get("kind", "")) == "answer":
                latest_answer = str(item.get("value", "")).strip()
                if latest_answer:
                    break
    return {
        "dependencies": related,
        "latest_answer": latest_answer,
    }


def _select_next_ready_task(tasks: list[dict[str, object]], completed_ids: list[str]) -> dict[str, object]:
    completed = set(completed_ids)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id", "")).strip()
        if not task_id or task_id in completed:
            continue
        depends_on = task.get("depends_on", [])
        if not isinstance(depends_on, list):
            depends_on = []
        if all(str(dep).strip() in completed for dep in depends_on):
            return task
    return {}


def _task_index(tasks: list[dict[str, object]], target: dict[str, object]) -> int:
    target_id = str(target.get("task_id", "")).strip()
    for index, task in enumerate(tasks):
        if str(task.get("task_id", "")).strip() == target_id:
            return index
    return 0
