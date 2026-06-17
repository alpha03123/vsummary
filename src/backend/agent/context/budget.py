"""Agent 上下文预算的"观测 + 阈值判定"服务。

业务意图：在 LangGraph 节点执行 LLM 调用之前，先用 `AgentContextBudgetService`
估算"系统指令 + 对话记忆 + 工作区上下文 + 工具结果"四类 token 的总量，
并对照窗口大小给出"normal / warning / compact / blocking"四个使用等级，
供上层决定是否触发压缩、是否阻断本轮请求。

token 估算采用"UTF-8 字节数 / 3"的近似；这是一种"宁可高估也不漏算"的
过近似策略，避免真实 tokenizer 算下来才超窗口。
"""

from __future__ import annotations

from math import ceil

from pydantic import BaseModel, Field

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentContextLoader, AgentSessionStore

# 估算"系统指令（LangGraph 节点名 + 程序名）"token 时使用的一份固定字典。
#
# 用静态结构而非真实配置的理由：LangGraph 图结构相对稳定，作为"系统指令"
# 的代表样本足以给出数量级正确的估算；任何实际提示词都不应比这更长。
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

# 默认的模型上下文窗口大小（token）。
DEFAULT_CONTEXT_WINDOW_TOKENS = 1_000_000
# 默认需要为模型输出预留的 token 数。
DEFAULT_RESERVED_OUTPUT_TOKENS = 20_000
# 进入"提醒"等级的阈值（占窗口大小的比例）。
DEFAULT_WARNING_THRESHOLD_RATIO = 0.60
# 进入"应当压缩"等级的阈值（占窗口大小的比例）。
DEFAULT_COMPACT_THRESHOLD_RATIO = 0.80
# 进入"阻断本轮"等级的阈值（占窗口大小的比例）。
DEFAULT_BLOCKING_THRESHOLD_RATIO = 0.92


class AgentContextUsageSource(BaseModel):
    """单个 token 来源在预算快照中的明细。"""

    id: str
    label: str
    estimated_tokens: int


class AgentContextUsage(BaseModel):
    """一次"预算观测"的完整快照，供前端或调用方做决策与展示。"""

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
    """按"系统指令 + 对话记忆 + 工作区上下文 + 工具结果"四类估算 token 总量。

    业务场景：在每轮 Agent 执行 LLM 调用前，先用 `inspect` 算一次预算，给出
    `AgentContextUsage` 快照；上层依据 `level` 决定是否需要触发压缩、
    是否需要阻断本轮请求。

    算法：
    1. 用 `AgentContextLoader` 拉取基础 `AgentContext`；如有 `AgentSessionStore`
       则合并会话内的 `context` 字段与会话消息。
    2. 用调用方传入的 `context_override` 覆盖（仅覆盖显式设置的字段）。
    3. 分别估算四类来源的 token：`GRAPH_RUNTIME_BASELINE`（系统指令）、
       会话消息（对话记忆）、`context.model_dump(mode="json")`（工作区上下文）、
       工具结果（当前固定为 0，留待后续节点统计）。
    4. 把总量与窗口大小比对，套入四个等级：`normal < warning < compact < blocking`。
    """

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
        """注入上下文加载器、会话存储（可选）以及窗口/阈值参数。

        Args:
            context_loader: 拉取基础 `AgentContext` 的 Port 实现。
            session_store: 可选的会话存储；提供后会用其 `get_snapshot` 把
                会话级上下文与会话消息合并进预算估算。
            window_tokens: 模型上下文窗口大小（token）。
            reserved_output_tokens: 为模型输出预留的 token 数。
            warning_threshold_ratio: "提醒"等级阈值占窗口的比例。
            compact_threshold_ratio: "压缩"等级阈值占窗口的比例。
            blocking_threshold_ratio: "阻断"等级阈值占窗口的比例。
        """
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
        """对指定会话做一次上下文预算观测。

        Args:
            session_id: 目标会话 ID。
            context_override: 调用方提供的覆盖上下文；若为 `None` 则只使用
                从 Loader/Store 拉取到的内容；若提供，仅覆盖显式设置的字段。

        Returns:
            包含总量、剩余、阈值、使用等级与四类来源明细的 `AgentContextUsage`。
        """
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
    """把工作区上下文序列化为 JSON 后估算 token 数。

    Args:
        context: 待估算的 `AgentContext`。

    Returns:
        估算的 token 数（采用字节/3 过近似）。
    """
    payload = context.model_dump(mode="json")
    return _estimate_tokens(payload)


def _merge_context(base_context: AgentContext, context_override: AgentContext | None) -> AgentContext:
    """把 `context_override` 中显式设置的字段合并进 `base_context`。

    Args:
        base_context: 基础上下文（来自 Loader/Store）。
        context_override: 覆盖上下文；若为 `None` 则原样返回 `base_context`。

    Returns:
        合并后的新 `AgentContext`；`session_id` 不参与合并（按 `session_id`
        找的上下文不应当被覆盖）。
    """
    if context_override is None:
        return base_context

    override_payload = context_override.model_dump(exclude_unset=True)
    override_payload.pop("session_id", None)
    merged_payload = base_context.model_dump(mode="python")
    merged_payload.update(override_payload)
    return AgentContext.model_validate(merged_payload)


def _estimate_tokens(value: object) -> int:
    """粗略估算一段字符串或可序列化对象的 token 数。

    算法：先序列化为紧凑字符串（`ensure_ascii=False`），再按"UTF-8 字节数 / 3"
    过近似；空内容返回 0，非空至少返回 1。不替代真实 tokenizer 计数。

    Args:
        value: 待估算的值；字符串原样使用，其他类型会被 JSON 序列化。

    Returns:
        估算的 token 数。
    """
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
    """把"已用 token 数"映射到"normal / warning / compact / blocking"四个等级。

    Args:
        estimated_total_tokens: 已用 token 估算值。
        warning_threshold_tokens: "提醒"阈值。
        compact_threshold_tokens: "压缩"阈值。
        blocking_threshold_tokens: "阻断"阈值。

    Returns:
        四个字符串之一，按从高到低命中：`blocking` > `compact` > `warning` > `normal`。
    """
    if estimated_total_tokens >= blocking_threshold_tokens:
        return "blocking"
    if estimated_total_tokens >= compact_threshold_tokens:
        return "compact"
    if estimated_total_tokens >= warning_threshold_tokens:
        return "warning"
    return "normal"
