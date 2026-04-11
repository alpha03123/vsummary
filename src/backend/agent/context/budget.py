from __future__ import annotations

from math import ceil

from pydantic import BaseModel, Field

from backend.agent.memory.context import AgentContext
from backend.agent.memory.runtime import load_runtime_context
from backend.agent.memory.store import AgentMemoryStore
from backend.agent.ports import AgentContextLoader

GRAPH_RUNTIME_BASELINE = {
    "graph": "agent_graph",
    "nodes": ["classify", "split_compare", "retrieve", "read_meta_state", "dispatch_action", "answer"],
    "programs": ["dspy_classify", "dspy_split_compare", "dspy_answer"],
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
        memory_store: AgentMemoryStore,
        window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
        reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS,
        warning_threshold_ratio: float = DEFAULT_WARNING_THRESHOLD_RATIO,
        compact_threshold_ratio: float = DEFAULT_COMPACT_THRESHOLD_RATIO,
        blocking_threshold_ratio: float = DEFAULT_BLOCKING_THRESHOLD_RATIO,
    ) -> None:
        self._context_loader = context_loader
        self._memory_store = memory_store
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
        context, memory_key, _history = load_runtime_context(
            context_loader=self._context_loader,
            memory_store=self._memory_store,
            session_id=session_id,
            context_override=context_override,
        )
        system_prompt_tokens = _estimate_tokens(GRAPH_RUNTIME_BASELINE)
        recent_messages_tokens = _estimate_recent_messages_tokens(context.recent_messages)
        workspace_context_tokens = _estimate_workspace_context_tokens(context)
        tool_results_tokens = 0
        estimated_total_tokens = (
            system_prompt_tokens
            + recent_messages_tokens
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
                    id="recent_messages",
                    label="最近消息",
                    estimated_tokens=recent_messages_tokens,
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
    payload["recent_messages"] = []
    return _estimate_tokens(payload)


def _estimate_recent_messages_tokens(recent_messages: list[str]) -> int:
    if not recent_messages:
        return 0
    return _estimate_tokens("\n".join(recent_messages))


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
