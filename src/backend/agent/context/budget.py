from __future__ import annotations

from math import ceil

from pydantic import BaseModel, Field

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentContextLoader, AgentSessionStore

GRAPH_RUNTIME_BASELINE = {
    "graph": "agent_graph",
    "nodes": [
        "route_scope",
        "build_video_context",
        "understand_query",
        "retrieve_evidence",
        "synthesize_answer",
        "answer",
        "finalize",
    ],
    "programs": [
        "video_answer",
    ],
}

DEFAULT_CONTEXT_WINDOW_TOKENS = 1_000_000
DEFAULT_RESERVED_OUTPUT_TOKENS = 20_000
DEFAULT_WARNING_THRESHOLD_RATIO = 0.60
DEFAULT_COMPACT_THRESHOLD_RATIO = 0.80
DEFAULT_BLOCKING_THRESHOLD_RATIO = 0.92


class AgentContextUsageSource(BaseModel):
    id: str
    label: str
    estimated_tokens: int


class AgentContextUsage(BaseModel):
    session_id: str
    scope_type: str
    memory_key: str
    estimated_total_tokens: int
    window_tokens: int
    reserved_output_tokens: int
    warning_threshold_tokens: int
    compact_threshold_tokens: int
    blocking_threshold_tokens: int
    remaining_tokens: int
    usage_percent: float
    level: str
    sources: list[AgentContextUsageSource] = Field(default_factory=list)


class AgentContextBudgetService:
    def __init__(
        self,
        *,
        context_loader: AgentContextLoader,
        session_store: AgentSessionStore | None = None,
        window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
        reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS,
        warning_threshold_ratio: float = DEFAULT_WARNING_THRESHOLD_RATIO,
        compact_threshold_ratio: float = DEFAULT_COMPACT_THRESHOLD_RATIO,
        blocking_threshold_ratio: float = DEFAULT_BLOCKING_THRESHOLD_RATIO,
    ) -> None:
        self._context_loader = context_loader
        self._session_store = session_store
        self._window_tokens = window_tokens
        self._reserved_output_tokens = reserved_output_tokens
        self._warning_threshold_tokens = int(window_tokens * warning_threshold_ratio)
        self._compact_threshold_tokens = int(window_tokens * compact_threshold_ratio)
        self._blocking_threshold_tokens = int(window_tokens * blocking_threshold_ratio)

    def inspect(
        self,
        *,
        session_id: str,
        context_override: AgentContext | None,
    ) -> AgentContextUsage:
        context = self._context_loader.load(session_id)
        memory_messages: list[dict[str, object]] = []
        if self._session_store is not None:
            snapshot = self._session_store.get_snapshot(session_id)
            if snapshot is not None:
                context = _merge_context(context, snapshot.context)
                memory_messages = [
                    {"role": message.role, "content": message.content}
                    for message in snapshot.messages
                ]
        context = _merge_context(context, context_override)
        memory_key = session_id
        system_prompt_tokens = _estimate_tokens(GRAPH_RUNTIME_BASELINE)
        memory_tokens = _estimate_tokens(memory_messages)
        workspace_context_tokens = _estimate_workspace_context_tokens(context)
        tool_results_tokens = 0
        estimated_total_tokens = (
            system_prompt_tokens
            + memory_tokens
            + workspace_context_tokens
            + tool_results_tokens
        )
        remaining_tokens = max(0, self._window_tokens - estimated_total_tokens)

        return AgentContextUsage(
            session_id=context.session_id,
            scope_type=context.scope_type,
            memory_key=memory_key,
            estimated_total_tokens=estimated_total_tokens,
            window_tokens=self._window_tokens,
            reserved_output_tokens=self._reserved_output_tokens,
            warning_threshold_tokens=self._warning_threshold_tokens,
            compact_threshold_tokens=self._compact_threshold_tokens,
            blocking_threshold_tokens=self._blocking_threshold_tokens,
            remaining_tokens=remaining_tokens,
            usage_percent=round((estimated_total_tokens / self._window_tokens) * 100, 2),
            level=_resolve_usage_level(
                estimated_total_tokens,
                warning_threshold_tokens=self._warning_threshold_tokens,
                compact_threshold_tokens=self._compact_threshold_tokens,
                blocking_threshold_tokens=self._blocking_threshold_tokens,
            ),
            sources=[
                AgentContextUsageSource(
                    id="system_prompt",
                    label="系统指令",
                    estimated_tokens=system_prompt_tokens,
                ),
                AgentContextUsageSource(
                    id="memory_messages",
                    label="对话记忆",
                    estimated_tokens=memory_tokens,
                ),
                AgentContextUsageSource(
                    id="tool_results",
                    label="工具结果",
                    estimated_tokens=tool_results_tokens,
                ),
                AgentContextUsageSource(
                    id="workspace_context",
                    label="工作区上下文",
                    estimated_tokens=workspace_context_tokens,
                ),
            ],
        )


def _estimate_workspace_context_tokens(context: AgentContext) -> int:
    payload = context.model_dump(mode="json")
    return _estimate_tokens(payload)


def _merge_context(base_context: AgentContext, context_override: AgentContext | None) -> AgentContext:
    if context_override is None:
        return base_context

    override_payload = context_override.model_dump(exclude_unset=True)
    override_payload.pop("session_id", None)
    merged_payload = base_context.model_dump(mode="python")
    merged_payload.update(override_payload)
    return AgentContext.model_validate(merged_payload)


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


def _resolve_usage_level(
    estimated_total_tokens: int,
    *,
    warning_threshold_tokens: int,
    compact_threshold_tokens: int,
    blocking_threshold_tokens: int,
) -> str:
    if estimated_total_tokens >= blocking_threshold_tokens:
        return "blocking"
    if estimated_total_tokens >= compact_threshold_tokens:
        return "compact"
    if estimated_total_tokens >= warning_threshold_tokens:
        return "warning"
    return "normal"
