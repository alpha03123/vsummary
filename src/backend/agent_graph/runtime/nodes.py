"""LangGraph 图节点集合 + 共用辅助工具。

本模块包含：
- 图节点工厂：`build_video_context_node` / `build_plan_and_execute_video_actions_node`
  / `build_route_scope_node` / `build_understand_query_node` /
  `build_retrieve_evidence_node` / `build_optional_web_search_node` /
  `build_evidence_items_node` / `build_synthesize_answer_node` /
  `build_answer_node`，以及终结点 `finalize_state`；
- 文本回答相关工具：`synthesize_answer_text` / `build_answer_text_messages` /
  `append_answer_to_state`；
- 私有辅助：检索 hits 去重与多视频多样化、上下文预算估算、联网决策、
  本地/联网证据归一化、视频总结/转写上下文条目构造、秒数格式化等。
"""

from __future__ import annotations

from collections.abc import Callable
from math import ceil
from time import monotonic

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.runtime.state import AgentGraphState
from backend.video_summary.library.usecases.series_synopsis_generation import build_series_catalog_payload


def build_video_context_node(
    *,
    workspace,
    retrieval_service,
    context_window_tokens: int,
    reserved_output_tokens: int,
) -> Callable[[AgentGraphState], AgentGraphState]:
    """构造 `build_video_context` 节点函数：构造 video scope 的检索结果。

    业务目的：在 video 链路里，跳过 series 风格的 query understanding，
    直接把"视频总结 + 完整转写"或"总结 + 转写 RAG"打包为 `retrieval_results`，
    供后续节点直接消费。

    Args:
        workspace: 视频工作区只读端口（必须非 `None`）。
        retrieval_service: 转写 RAG 检索服务（仅在完整转写塞不下时使用）。
        context_window_tokens: video scope 上下文窗口 token 上限。
        reserved_output_tokens: 预留输出 token。

    Returns:
        一个接受 `AgentGraphState` 并返回新 state 的 LangGraph 节点函数。

    Raises:
        RuntimeError: `workspace` 未注入。
        ValueError: state 缺少 `series_id` 或 `video_id`。
    """
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
    """构造 `plan_and_execute_video_actions` 节点：LLM 规划 + 工具执行。

    业务目的：在 video scope 证据整理之后，让 LLM 基于证据 + 记忆决定
    要打开/记录/跳转哪些工具，并由 executor 立即执行；结果（tool_calls /
    tool_results / action_summary）写入 state。

    Args:
        video_action_planner: 实现 `VideoActionPlanner.run` 接口的规划器；
            为 `None` 时节点直接透传 state（不规划也不执行）。
        tool_executor: 工具执行器端口；为 `None` 时同上。

    Returns:
        LangGraph 节点函数；处理后返回新的 state。
    """
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
    """构造 `route_scope` 节点：当前为 identity 透传，仅承担条件边的起点。

    返回的节点函数直接返回 `dict(state)`，真正按 `scope_type` 路由由
    `graph.add_conditional_edges` + `_route_after_scope` 完成。
    """
    def route_scope(state: AgentGraphState) -> AgentGraphState:
        return dict(state)

    return route_scope


def build_understand_query_node(*, series_query_processor, workspace=None) -> Callable[[AgentGraphState], AgentGraphState]:
    """构造 `understand_query` 节点：调用 LLM 解析用户问题。

    业务目的：在 series 链路里，先让 LLM 把用户问题改写为 `normalized_query`
    + 子问题 + filters，并初始化下游节点的 state 字段（检索 / 联网 /
    证据 / 回答占位）。

    Args:
        series_query_processor: 实现 `SeriesQueryProcessor.run` 的处理器；
            为 `None` 时节点会抛 `RuntimeError`。
        workspace: 可选的工作区只读端口，用于加载 series catalog 与标题。

    Returns:
        LangGraph 节点函数。

    Raises:
        RuntimeError: `series_query_processor` 未注入。
    """
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
    """构造 `retrieve_evidence` 节点：基于 `query_understanding` 做系列级 RAG 检索。

    流程：拿 `normalized_query` + 子问题拼检索 query 列表 → 调 `retrieval_service`
    → 对结果做去重 + 多视频多样化 → 写入 `retrieval_results` 与 `retrieval_request`。

    Args:
        retrieval_service: 系列级 RAG 检索服务（`SeriesRetrievalService` 或兼容实现）。

    Returns:
        LangGraph 节点函数。
    """
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
    """构造 `optional_web_search` 节点：按启发式决定是否触发联网搜索。

    触发条件：网关/配置齐全且 `enabled=True`、本地证据不足或用户消息中
    包含联网意图关键词。命中后调 `web_search_gateway.search` 并把结果
    归一化写入 `web_search_results`（附 `duration_ms`）。

    Args:
        web_search_gateway: 实现 `search(user_message, max_results, timeout_seconds)`
            的联网网关；为 `None` 时节点透传 state。
        web_search_settings: 联网配置（启用开关、最大结果数、超时秒数）；
            为 `None` 或 `enabled=False` 时节点透传 state。

    Returns:
        LangGraph 节点函数。

    Raises:
        RuntimeError: 网关调用失败时被包装后抛出。
    """
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
    """构造 `build_evidence_items` 节点：合并本地证据与联网证据并归一化。

    流程：把 `retrieval_results` 投影成本地证据（带 `evidence_id`），再把
    `web_search_results` 投影成联网证据；二者拼接写入 `evidence_items`，
    供下游回答合成与 video 节点统一消费。
    """
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
    """构造 `synthesize_answer` 节点：调用 series 回答合成器生成最终回答。

    支持两种模式：
        - 普通模式：直接调 `series_answer_synthesizer.run`，把 `payload` 与
          `answer` 写入 state；
        - 流式延后模式（`defer_answer_stream=True`）：仅构造 `stream_answer_messages`
          留给 `AgentGraphStreamOrchestrator` 真正发起流式生成。

    Args:
        series_answer_synthesizer: 实现 `run` / `build_text_messages` 的回答合成器；
            为 `None` 时节点抛 `RuntimeError`。

    Returns:
        LangGraph 节点函数。

    Raises:
        RuntimeError: `series_answer_synthesizer` 未注入。
    """
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
    """构造 `answer` 节点：合成 video scope 的最终回答。

    同样支持延后流式：若 `defer_answer_stream=True` 则只构造
    `stream_answer_messages`；否则直接调 `synthesize_answer_text` 拿文本
    并通过 `append_answer_to_state` 写入。

    Args:
        answer_program: 实现 `run` / `build_text_messages` 的 video scope 回答程序。
    """
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
    """调用 `answer_program.run` 同步合成最终回答文本。

    投影参数：user_message、记忆消息、证据列表（两次：retrieval_results
    与 evidence_items 都用同一份）、以及 meta_state（工具结果 + action
    摘要 + 是否使用联网）。

    Args:
        state: 当前 `AgentGraphState`。
        answer_program: video scope 回答程序。
        debug_trace: 当前未使用，预留扩展。

    Returns:
        LLM 合成的回答文本字符串。
    """
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
    """构造 video scope 延后流式回答所需的 `AgentChatMessage` 列表。

    Args:
        state: 当前 `AgentGraphState`。
        answer_program: 实现 `build_text_messages` 的 video 回答程序。

    Returns:
        准备送往 LLM 流的 `AgentChatMessage` 列表。
    """
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
    """把回答文本写入 state 的 `answer` 字段并追加到 `task_outputs`。

    Args:
        state: 当前 state。
        answer_text: 已生成的回答文本（可能为空）。

    Returns:
        新的 state（`dict(state)` 拷贝）。
    """
    next_state = dict(state)
    next_state["answer"] = answer_text
    next_state["task_outputs"] = list(state.get("task_outputs", [])) + [
        {"kind": "answer", "value": answer_text}
    ]
    return next_state


def finalize_state(state: AgentGraphState) -> AgentGraphState:
    """图终节点：把所有 `task_outputs` 拼成 `assistant_message`，必要时回填 `answer`。

    行为：
        - 把 `task_outputs` 中 `kind=answer` 等有效文本用换行拼接为
          `assistant_message`；
        - 若 `answer` 为空则用 `assistant_message` 回填，保证最终用户消息与
          回答字段都非空。
    """
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
    """加载系列目录：优先读 `workspace.get_series_catalog`，缺失时回退到构造器。

    Args:
        workspace: 工作区只读端口。
        series_id: 目标系列 ID。

    Returns:
        系列目录字典；`workspace` 为 `None` 或 `series_id` 为空时返回只含
        `{series_id, videos: []}` 的占位字典。
    """
    if workspace is None or not series_id:
        return {"series_id": series_id, "videos": []}
    existing = workspace.get_series_catalog(series_id)
    if isinstance(existing, dict):
        return existing
    return build_series_catalog_payload(workspace, series_id)


def _resolve_retrieval_max_hits(retrieval_service) -> int:
    """读取检索服务的 `default_max_hits` 配置；不可用时回退到 5。"""
    default_max_hits = getattr(retrieval_service, "default_max_hits", None)
    if callable(default_max_hits):
        return int(default_max_hits())
    return 5


def _resolve_series_title(*, workspace, series_id: str) -> str:
    """查询系列的标题字符串；找不到时返回空串。"""
    if workspace is None or not series_id:
        return ""
    series = next((item for item in workspace.list_series() if item.id == series_id), None)
    if series is None:
        return ""
    return series.title


def _build_retrieval_queries(normalized_query: str, subqueries: list[str], *, max_queries: int = 5) -> list[str]:
    """把归一化查询与子问题拼成有序去重的检索 query 列表（最多 `max_queries` 条）。"""
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
    """对每个 query 调检索服务、合并 hits 并做去重 + 多视频多样化。"""
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
    """按 `doc_id` 去重；缺 `doc_id` 时回退到 `video_id|source_type|start|text` 复合键。"""
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
    """先按"每视频至多一条"选择，未满 `max_hits` 时再按原顺序补齐。"""
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
    """把 dict 形式的 query understanding 校验为 `SeriesQueryUnderstanding`。"""
    from backend.agent_graph.query.models import SeriesQueryUnderstanding

    return SeriesQueryUnderstanding.model_validate(value)


def _coerce_retrieval_hits(items: list[dict[str, object]]):
    """把 dict 检索 hits 列表校验为 `RetrievalHit` 列表，缺失字段补默认值。"""
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
    """启发式判断是否触发联网搜索：本地证据为空或用户消息含联网意图关键词。

    关键词包含中英文：联网 / 上网 / 搜索 / 查一下 / 查下 / 查找 / 外部资料 /
    官网 / 最新 / 今天 / 现在 / 核验 / 验证 / web / internet / search / latest。
    """
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
    """为本地证据补齐 `evidence_id` / `source_family` / `source_type` / `text` / `snippet`。

    `index` 用作兜底 `evidence_id`（如 `local-{index}`）。
    """
    payload = dict(item)
    payload["evidence_id"] = str(payload.get("evidence_id", f"local-{index}")).strip() or f"local-{index}"
    payload["source_family"] = str(payload.get("source_family", "local")).strip() or "local"
    payload["source_type"] = str(payload.get("source_type", "local")).strip() or "local"
    payload["text"] = str(payload.get("text", payload.get("snippet", ""))).strip()
    payload["snippet"] = str(payload.get("snippet", payload.get("text", ""))).strip()
    return payload


def _normalize_web_search_result(item: dict[str, object], *, index: int) -> dict[str, object]:
    """把联网搜索结果归一化为统一证据字典；`url` 或 `text/snippet` 缺失时抛错。

    关键约定：强制 `source_family="web"`、`source_type="web_search"`；缺失
    标题时回退到 URL；`text` 与 `snippet` 至少要有一个非空。
    """
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
    """把视频总结 DTO 投影为本地上下文条目（含一句话/核心问题/要点）。

    Args:
        state: 当前 graph state，用于回填 series_id / video_id。
        summary: 视频总结 DTO（可为 `None`）。

    Returns:
        含 `source_type=summary_global` 的本地证据字典；`summary` 为 `None`
        或其 `summary` 字段不是 dict 或渲染后无文本时返回 `None`。
    """
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
    """把完整转写 DTO 投影为本地上下文条目（每行带 `[mm:ss]` 时间戳）。"""
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
    """在 video scope 内对转写类来源做 RAG 检索（窗口扩展 120 秒）。"""
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
    """判断 user_message + memory + items 是否能塞进上下文窗口（粗略 token 估算）。"""
    available = max(0, int(context_window_tokens) - int(reserved_output_tokens))
    payload = {
        "user_message": state.get("user_message", ""),
        "memory_messages": state.get("memory_messages", []),
        "retrieval_results": items,
    }
    return _estimate_tokens(payload) <= available


def _render_video_summary_text(summary: dict[str, object]) -> str:
    """把视频总结 dict 渲染为可索引的纯文本（一句+核心问题+要点+章节）。"""
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
    """粗略估算 token 数：按 UTF-8 字节数 / 3 计算；空字符串返回 0，最少 1。"""
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
    """把秒数格式化为 `mm:ss` 字符串（负数按 0 处理）。"""
    seconds = max(0, int(float(value or 0)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _project_answer_evidence(results: list[dict[str, object]]) -> list[dict[str, object]]:
    """过滤非字典元素，返回原样的证据列表（供 `answer_program` 消费）。"""
    return [item for item in results if isinstance(item, dict)]
