from __future__ import annotations

from collections.abc import Callable
from math import ceil
from time import monotonic

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.runtime.state import AgentGraphState
from backend.video_summary.workspace.usecases.series_synopsis_generation import build_series_catalog_payload


def build_video_context_node(
    *,
    workspace,
    retrieval_service,
    context_window_tokens: int,
    reserved_output_tokens: int,
) -> Callable[[AgentGraphState], AgentGraphState]:
    def build_video_context(state: AgentGraphState) -> AgentGraphState:
        if workspace is None:
            raise RuntimeError("Video workspace 尚未注入。")
        series_id = str(state["series_id"]).strip()
        video_id = str(state.get("video_id", "")).strip()
        if not series_id or not video_id:
            raise ValueError("video scope 缺少 series_id 或 video_id。")

        summary = workspace.get_video_summary(series_id, video_id)
        transcript = workspace.get_video_transcript(series_id, video_id)
        summary_item = _build_video_summary_context_item(state, summary)
        transcript_item = _build_full_transcript_context_item(transcript)

        retrieval_results: list[dict[str, object]] = []
        if summary_item:
            retrieval_results.append(summary_item)
        if transcript_item and _fits_context_budget(
            state=state,
            items=[item for item in [summary_item, transcript_item] if item],
            context_window_tokens=context_window_tokens,
            reserved_output_tokens=reserved_output_tokens,
        ):
            retrieval_results.append(transcript_item)
            mode = "full_transcript"
        else:
            retrieval_results.extend(_search_video_transcript(
                retrieval_service=retrieval_service,
                state=state,
                query=str(state["user_message"]),
            ))
            mode = "summary_plus_transcript_rag"

        next_state = dict(state)
        next_state["retrieval_results"] = retrieval_results
        next_state["video_context_mode"] = mode
        next_state["video_summary_included"] = summary_item is not None
        return next_state

    return build_video_context


def build_plan_and_execute_video_actions_node(
    *,
    video_action_planner=None,
    tool_executor=None,
) -> Callable[[AgentGraphState], AgentGraphState]:
    def plan_and_execute_video_actions(state: AgentGraphState) -> AgentGraphState:
        if video_action_planner is None or tool_executor is None:
            return dict(state)
        context = AgentContext(
            session_id=str(state["session_id"]),
            scope_type="video",
            series_id=str(state["series_id"]),
            video_id=str(state.get("video_id", "")),
        )
        plan = video_action_planner.run(
            user_message=str(state["user_message"]),
            retrieval_results=[
                item for item in state.get("evidence_items", state.get("retrieval_results", []))
                if isinstance(item, dict)
            ],
            memory_messages=[
                item for item in state.get("memory_messages", [])
                if isinstance(item, dict)
            ],
        )
        tool_results = [
            tool_executor.execute_call(call, context)
            for call in list(getattr(plan, "tool_calls", []))
        ]
        next_state = dict(state)
        next_state["tool_calls"] = [
            call.model_dump(mode="json")
            for call in list(getattr(plan, "tool_calls", []))
        ]
        next_state["tool_results"] = [
            result.model_dump(mode="json")
            for result in tool_results
        ]
        next_state["action_summary"] = str(getattr(plan, "action_summary", "")).strip()
        return next_state

    return plan_and_execute_video_actions


def build_route_scope_node() -> Callable[[AgentGraphState], AgentGraphState]:
    def route_scope(state: AgentGraphState) -> AgentGraphState:
        return dict(state)

    return route_scope


def build_understand_query_node(*, series_query_processor, workspace=None) -> Callable[[AgentGraphState], AgentGraphState]:
    def understand_query(state: AgentGraphState) -> AgentGraphState:
        if series_query_processor is None:
            raise RuntimeError("Series query processor 尚未注入。")
        series_id = str(state.get("series_id", "")).strip()
        catalog = _load_series_catalog(workspace=workspace, series_id=series_id)
        result = series_query_processor.run(
            user_message=state["user_message"],
            series_id=series_id,
            series_title=_resolve_series_title(workspace=workspace, series_id=series_id),
            series_catalog=catalog,
            memory_messages=list(state.get("memory_messages", [])),
            debug_trace=None,
        )
        next_state = dict(state)
        next_state["query_understanding"] = result.model_dump(mode="json")
        next_state["series_catalog"] = catalog
        next_state["retrieval_request"] = {}
        next_state["retrieval_results"] = []
        next_state["web_search_results"] = []
        next_state["web_search_used"] = False
        next_state["evidence_items"] = []
        next_state["answer_payload"] = {}
        next_state["tool_results"] = []
        return next_state

    return understand_query


def build_retrieve_evidence_node(*, retrieval_service) -> Callable[[AgentGraphState], AgentGraphState]:
    def retrieve_evidence(state: AgentGraphState) -> AgentGraphState:
        max_hits = _resolve_retrieval_max_hits(retrieval_service)
        query_understanding = dict(state.get("query_understanding", {}))
        normalized_query = str(query_understanding.get("normalized_query", "")).strip() or state["user_message"]
        subqueries = [
            str(item).strip()
            for item in query_understanding.get("subqueries", [])
            if isinstance(item, str) and str(item).strip()
        ]
        filters = dict(query_understanding.get("filters", {}))
        series_id = str(filters.get("series_id", state.get("series_id", ""))).strip()
        queries = _build_retrieval_queries(normalized_query, subqueries)
        retrieval_results = _search_series_queries(
            retrieval_service=retrieval_service,
            series_id=series_id,
            queries=queries,
            max_hits=max_hits,
        )
        next_state = dict(state)
        next_state["retrieval_request"] = {
            "query": normalized_query,
            "subqueries": subqueries,
            "filters": {"series_id": series_id},
            "executed_queries": queries,
        }
        next_state["retrieval_results"] = retrieval_results
        return next_state

    return retrieve_evidence


def build_optional_web_search_node(*, web_search_gateway=None, web_search_settings=None) -> Callable[[AgentGraphState], AgentGraphState]:
    def optional_web_search(state: AgentGraphState) -> AgentGraphState:
        if web_search_gateway is None or web_search_settings is None or not bool(getattr(web_search_settings, "enabled", False)):
            next_state = dict(state)
            next_state.setdefault("web_search_results", [])
            next_state.setdefault("web_search_used", False)
            return next_state

        local_items = [
            item for item in state.get("retrieval_results", [])
            if isinstance(item, dict)
        ]
        user_message = str(state.get("user_message", "")).strip()
        if not _should_use_web_search(user_message=user_message, local_items=local_items):
            next_state = dict(state)
            next_state.setdefault("web_search_results", [])
            next_state["web_search_used"] = False
            return next_state

        started_at = monotonic()
        try:
            results = web_search_gateway.search(
                user_message,
                max_results=int(getattr(web_search_settings, "max_results", 5)),
                timeout_seconds=int(getattr(web_search_settings, "timeout_seconds", 10)),
            )
        except Exception as error:
            raise RuntimeError(f"联网搜索失败：{error}") from error
        normalized_results = [
            _normalize_web_search_result(item, index=index)
            for index, item in enumerate(results, start=1)
            if isinstance(item, dict)
        ]
        duration_ms = int((monotonic() - started_at) * 1000)
        next_state = dict(state)
        next_state["web_search_results"] = [
            {**item, "duration_ms": duration_ms}
            for item in normalized_results
        ]
        next_state["web_search_used"] = bool(normalized_results)
        return next_state

    return optional_web_search


def build_evidence_items_node() -> Callable[[AgentGraphState], AgentGraphState]:
    def build_evidence_items(state: AgentGraphState) -> AgentGraphState:
        local_items = [
            _normalize_local_evidence_item(item, index=index)
            for index, item in enumerate(state.get("retrieval_results", []), start=1)
            if isinstance(item, dict)
        ]
        web_items = [
            _normalize_web_search_result(item, index=index)
            for index, item in enumerate(state.get("web_search_results", []), start=1)
            if isinstance(item, dict)
        ]
        next_state = dict(state)
        next_state["evidence_items"] = [*local_items, *web_items]
        return next_state

    return build_evidence_items


def build_synthesize_answer_node(*, series_answer_synthesizer) -> Callable[[AgentGraphState], AgentGraphState]:
    def synthesize_answer(state: AgentGraphState) -> AgentGraphState:
        if series_answer_synthesizer is None:
            raise RuntimeError("Series answer synthesizer 尚未注入。")
        query_understanding_payload = dict(state.get("query_understanding", {}))
        evidence_items = [
            item for item in state.get("evidence_items", state.get("retrieval_results", []))
            if isinstance(item, dict)
        ]
        if bool(state.get("defer_answer_stream", False)):
            next_state = dict(state)
            next_state["stream_answer_messages"] = [
                message.model_dump(mode="json")
                for message in series_answer_synthesizer.build_text_messages(
                    user_message=state["user_message"],
                    query_understanding=_coerce_query_understanding(query_understanding_payload),
                    evidence_items=evidence_items,
                    series_catalog=dict(state.get("series_catalog", {})),
                    memory_messages=[
                        item for item in state.get("memory_messages", [])
                        if isinstance(item, dict)
                    ],
                )
            ]
            next_state["answer_payload"] = {}
            return next_state
        payload = series_answer_synthesizer.run(
            user_message=state["user_message"],
            query_understanding=_coerce_query_understanding(query_understanding_payload),
            evidence_items=evidence_items,
            series_catalog=dict(state.get("series_catalog", {})),
            memory_messages=[
                item for item in state.get("memory_messages", [])
                if isinstance(item, dict)
            ],
            debug_trace=None,
        )
        next_state = dict(state)
        next_state["answer_payload"] = payload.model_dump(mode="json")
        return append_answer_to_state(next_state, payload.answer)

    return synthesize_answer


def build_answer_node(*, answer_program) -> Callable[[AgentGraphState], AgentGraphState]:
    def answer(state: AgentGraphState) -> AgentGraphState:
        if bool(state.get("defer_answer_stream", False)):
            next_state = dict(state)
            next_state["stream_answer_messages"] = [
                message.model_dump(mode="json")
                for message in build_answer_text_messages(
                    state,
                    answer_program=answer_program,
                )
            ]
            return next_state
        answer_text = synthesize_answer_text(
            state,
            answer_program=answer_program,
        )
        return append_answer_to_state(state, answer_text)

    return answer

def synthesize_answer_text(
    state: AgentGraphState,
    *,
    answer_program,
    debug_trace: dict[str, object] | None = None,
) -> str:
    return answer_program.run(
        user_message=state["user_message"],
        memory_messages=[
            item for item in state.get("memory_messages", [])
            if isinstance(item, dict)
        ],
        retrieval_results=_project_answer_evidence(list(state.get("evidence_items", state.get("retrieval_results", [])))),
        evidence_items=_project_answer_evidence(list(state.get("evidence_items", state.get("retrieval_results", [])))),
        meta_state={
            "tool_results": list(state.get("tool_results", [])),
            "action_summary": str(state.get("action_summary", "")).strip(),
            "web_search_used": bool(state.get("web_search_used", False)),
        },
    )


def build_answer_text_messages(
    state: AgentGraphState,
    *,
    answer_program,
) -> list[AgentChatMessage]:
    return answer_program.build_text_messages(
        user_message=state["user_message"],
        memory_messages=[
            item for item in state.get("memory_messages", [])
            if isinstance(item, dict)
        ],
        retrieval_results=_project_answer_evidence(list(state.get("evidence_items", state.get("retrieval_results", [])))),
        evidence_items=_project_answer_evidence(list(state.get("evidence_items", state.get("retrieval_results", [])))),
        meta_state={
            "tool_results": list(state.get("tool_results", [])),
            "action_summary": str(state.get("action_summary", "")).strip(),
            "web_search_used": bool(state.get("web_search_used", False)),
        },
    )


def append_answer_to_state(state: AgentGraphState, answer_text: str) -> AgentGraphState:
    next_state = dict(state)
    next_state["answer"] = answer_text
    next_state["task_outputs"] = list(state.get("task_outputs", [])) + [
        {"kind": "answer", "value": answer_text}
    ]
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
    if not next_state.get("answer"):
        next_state["answer"] = next_state["assistant_message"]
    return next_state


def _load_series_catalog(*, workspace, series_id: str) -> dict[str, object]:
    if workspace is None or not series_id:
        return {"series_id": series_id, "videos": []}
    existing = workspace.get_series_catalog(series_id)
    if isinstance(existing, dict):
        return existing
    return build_series_catalog_payload(workspace, series_id)


def _resolve_retrieval_max_hits(retrieval_service) -> int:
    default_max_hits = getattr(retrieval_service, "default_max_hits", None)
    if callable(default_max_hits):
        return int(default_max_hits())
    return 5


def _resolve_series_title(*, workspace, series_id: str) -> str:
    if workspace is None or not series_id:
        return ""
    series = next((item for item in workspace.list_series() if item.id == series_id), None)
    if series is None:
        return ""
    return series.title


def _build_retrieval_queries(normalized_query: str, subqueries: list[str], *, max_queries: int = 5) -> list[str]:
    queries: list[str] = []
    for query in [normalized_query, *subqueries]:
        normalized = str(query).strip()
        if normalized and normalized not in queries:
            queries.append(normalized)
        if len(queries) >= max_queries:
            break
    return queries


def _search_series_queries(
    *,
    retrieval_service,
    series_id: str,
    queries: list[str],
    max_hits: int,
) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for query in queries:
        response = retrieval_service.search(
            scope_type="series",
            series_id=series_id,
            video_id="",
            query=query,
            target_source="all",
            source_tags=[],
            expand_context=True,
            context_window_seconds=120,
            max_hits=max_hits,
        )
        hits.extend(item for item in response.get("hits", []) if isinstance(item, dict))
    return _diversify_series_hits(_deduplicate_hits(hits), max_hits=max_hits)


def _deduplicate_hits(hits: list[dict[str, object]]) -> list[dict[str, object]]:
    unique_hits: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for hit in hits:
        key = str(hit.get("doc_id", "")).strip()
        if not key:
            key = "|".join(
                [
                    str(hit.get("video_id", "")).strip(),
                    str(hit.get("source_type", "")).strip(),
                    str(hit.get("start_seconds", "")).strip(),
                    str(hit.get("text", hit.get("snippet", ""))).strip(),
                ]
            )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_hits.append(hit)
    return unique_hits


def _diversify_series_hits(hits: list[dict[str, object]], *, max_hits: int) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    selected_keys: set[int] = set()
    seen_videos: set[str] = set()

    for index, hit in enumerate(hits):
        video_id = str(hit.get("video_id", "")).strip()
        if video_id and video_id in seen_videos:
            continue
        selected.append(hit)
        selected_keys.add(index)
        if video_id:
            seen_videos.add(video_id)
        if len(selected) >= max_hits:
            return selected

    for index, hit in enumerate(hits):
        if index in selected_keys:
            continue
        selected.append(hit)
        if len(selected) >= max_hits:
            break
    return selected


def _coerce_query_understanding(value: dict[str, object]):
    from backend.agent_graph.query.models import SeriesQueryUnderstanding

    return SeriesQueryUnderstanding.model_validate(value)


def _coerce_retrieval_hits(items: list[dict[str, object]]):
    from backend.agent_graph.query.models import RetrievalHit

    hits: list[RetrievalHit] = []
    for index, item in enumerate(items, start=1):
        payload = dict(item)
        payload.setdefault("evidence_id", f"e{index}")
        payload.setdefault("doc_id", str(payload.get("doc_id", f"series:{payload.get('series_id', '')}:{index}")))
        payload.setdefault("series_id", str(payload.get("series_id", "")))
        payload.setdefault("source_family", str(payload.get("source_family", "")))
        payload.setdefault("title", str(payload.get("title", "")))
        payload.setdefault("text", str(payload.get("text", payload.get("snippet", ""))))
        hits.append(RetrievalHit.model_validate(payload))
    return hits


def _should_use_web_search(*, user_message: str, local_items: list[dict[str, object]]) -> bool:
    if not local_items:
        return True
    normalized = user_message.lower()
    explicit_markers = (
        "联网",
        "上网",
        "搜索",
        "查一下",
        "查下",
        "查找",
        "外部资料",
        "官网",
        "最新",
        "今天",
        "现在",
        "核验",
        "验证",
        "web",
        "internet",
        "search",
        "latest",
    )
    return any(marker in normalized for marker in explicit_markers)


def _normalize_local_evidence_item(item: dict[str, object], *, index: int) -> dict[str, object]:
    payload = dict(item)
    payload["evidence_id"] = str(payload.get("evidence_id", f"local-{index}")).strip() or f"local-{index}"
    payload["source_family"] = str(payload.get("source_family", "local")).strip() or "local"
    payload["source_type"] = str(payload.get("source_type", "local")).strip() or "local"
    payload["text"] = str(payload.get("text", payload.get("snippet", ""))).strip()
    payload["snippet"] = str(payload.get("snippet", payload.get("text", ""))).strip()
    return payload


def _normalize_web_search_result(item: dict[str, object], *, index: int) -> dict[str, object]:
    title = str(item.get("title", "")).strip()
    url = str(item.get("url", "")).strip()
    text = str(item.get("text", item.get("snippet", ""))).strip()
    snippet = str(item.get("snippet", text)).strip()
    if not url:
        raise ValueError("web_search result 缺少 url。")
    if not text and not snippet:
        raise ValueError("web_search result 缺少 text 或 snippet。")
    return {
        **dict(item),
        "evidence_id": str(item.get("evidence_id", f"web-{index}")).strip() or f"web-{index}",
        "doc_id": str(item.get("doc_id", f"web:{index}:{url}")).strip(),
        "series_id": str(item.get("series_id", "")).strip(),
        "video_id": str(item.get("video_id", "")).strip(),
        "source_family": "web",
        "source_type": "web_search",
        "title": title or url,
        "url": url,
        "text": text or snippet,
        "snippet": snippet or text,
        "published_at": str(item.get("published_at", "")).strip(),
    }


def _build_video_summary_context_item(state: AgentGraphState, summary) -> dict[str, object] | None:
    if summary is None:
        return None
    raw_summary = getattr(summary, "summary", {})
    if not isinstance(raw_summary, dict):
        return None
    text = _render_video_summary_text(raw_summary)
    if not text:
        return None
    video_id = str(getattr(summary, "video_id", "")).strip() or str(state.get("video_id", "")).strip()
    title = str(getattr(summary, "title", "")).strip()
    return {
        "series_id": str(getattr(summary, "series_id", state.get("series_id", ""))).strip(),
        "video_id": video_id,
        "title": title,
        "source_type": "summary_global",
        "source_family": "summary",
        "doc_id": f"series:{state.get('series_id', '')}:video:{video_id}:summary_global",
        "text": text,
        "snippet": text,
        "one_sentence_summary": str(raw_summary.get("one_sentence_summary", "")).strip(),
        "core_problem": str(raw_summary.get("core_problem", "")).strip(),
        "key_takeaways": list(raw_summary.get("key_takeaways", [])) if isinstance(raw_summary.get("key_takeaways", []), list) else [],
    }


def _build_full_transcript_context_item(transcript) -> dict[str, object] | None:
    if transcript is None:
        return None
    lines: list[str] = []
    for segment in getattr(transcript, "segments", []):
        text = str(getattr(segment, "text", "")).strip()
        if not text:
            continue
        lines.append(f"[{_format_seconds(getattr(segment, 'start_seconds', 0.0))}] {text}")
    text = "\n".join(lines).strip()
    if not text:
        return None
    return {
        "series_id": str(getattr(transcript, "series_id", "")).strip(),
        "video_id": str(getattr(transcript, "video_id", "")).strip(),
        "title": str(getattr(transcript, "title", "")).strip(),
        "source_type": "transcript_full",
        "source_family": "transcript",
        "doc_id": f"series:{getattr(transcript, 'series_id', '')}:video:{getattr(transcript, 'video_id', '')}:transcript_full",
        "start_seconds": getattr(transcript, "segments", [None])[0].start_seconds if getattr(transcript, "segments", []) else None,
        "end_seconds": getattr(transcript, "segments", [None])[-1].end_seconds if getattr(transcript, "segments", []) else None,
        "text": text,
        "snippet": text,
    }


def _search_video_transcript(*, retrieval_service, state: AgentGraphState, query: str) -> list[dict[str, object]]:
    response = retrieval_service.search(
        scope_type="video",
        series_id=state["series_id"],
        video_id=state.get("video_id", ""),
        query=query,
        target_source="transcript",
        source_tags=["transcript"],
        expand_context=True,
        context_window_seconds=120,
        max_hits=_resolve_retrieval_max_hits(retrieval_service),
    )
    hits = response.get("hits", [])
    if not isinstance(hits, list):
        return []
    return [hit for hit in hits if isinstance(hit, dict)]


def _fits_context_budget(
    *,
    state: AgentGraphState,
    items: list[dict[str, object]],
    context_window_tokens: int,
    reserved_output_tokens: int,
) -> bool:
    available = max(0, int(context_window_tokens) - int(reserved_output_tokens))
    payload = {
        "user_message": state.get("user_message", ""),
        "memory_messages": state.get("memory_messages", []),
        "retrieval_results": items,
    }
    return _estimate_tokens(payload) <= available


def _render_video_summary_text(summary: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("one_sentence_summary", "core_problem"):
        value = str(summary.get(key, "")).strip()
        if value:
            parts.append(value)
    takeaways = summary.get("key_takeaways", [])
    if isinstance(takeaways, list):
        parts.extend(str(item).strip() for item in takeaways if isinstance(item, str) and item.strip())
    chapters = summary.get("chapters", [])
    if isinstance(chapters, list):
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            title = str(chapter.get("title", "")).strip()
            chapter_summary = str(chapter.get("summary", "")).strip()
            if title or chapter_summary:
                parts.append("：".join(part for part in [title, chapter_summary] if part))
    return "\n".join(parts).strip()


def _estimate_tokens(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        text = value.strip()
    else:
        from json import dumps

        text = dumps(value, ensure_ascii=False, separators=(",", ":")).strip()
    if not text:
        return 0
    return max(1, ceil(len(text.encode("utf-8")) / 3))


def _format_seconds(value: object) -> str:
    seconds = max(0, int(float(value or 0)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _project_answer_evidence(results: list[dict[str, object]]) -> list[dict[str, object]]:
    return [item for item in results if isinstance(item, dict)]
