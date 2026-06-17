"""LangGraph 图结果字段提取工具。

本模块集中提供从图执行结果中抽取"助手消息 / 理由 / 工具结果"的辅助函数，
被 `AgentGraphTurnBuilder`、`AgentGraphStreamOrchestrator` 等消费。
"""

from __future__ import annotations

from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


def extract_assistant_message(result: dict[str, object]) -> str:
    """从图结果中提取最终给用户的助手消息文本。

    优先读取 `assistant_message`；为空时回退到 `answer`；两者均不存在
    或类型不为字符串时返回空串（结果会再 `strip`）。

    Args:
        result: LangGraph `invoke` / `stream` 返回的状态字典。

    Returns:
        `strip` 后的助手消息字符串；可能为空字符串。
    """
    return str(
        result.get("assistant_message")
        or result.get("answer", "")
    ).strip()


def extract_reason(result: dict[str, object]) -> str:
    """从图结果中提取本次回合的"理由"或"归一化问题"。

    优先级：`query_understanding.normalized_query` → `reason` → 空串。
    用于在 `AgentTurnResult.plan.reason` 中给前端展示。

    Args:
        result: LangGraph 返回的状态字典。

    Returns:
        `strip` 后的理由字符串；可能为空字符串。
    """
    query_understanding = result.get("query_understanding", {})
    if isinstance(query_understanding, dict):
        normalized_query = str(query_understanding.get("normalized_query", "")).strip()
        if normalized_query:
            return normalized_query
    reason = result.get("reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    return ""


def extract_tool_results(result: dict[str, object]) -> list[ToolExecutionResult]:
    """把 `tool_results` 字段归一化为 `ToolExecutionResult` 列表。

    非列表 / 空列表 / 非字典元素会被静默跳过；`payload` 必须为字典，
    否则回退为空字典。

    Args:
        result: LangGraph 返回的状态字典。

    Returns:
        校验后的 `ToolExecutionResult` 列表。
    """
    explicit_tool_results = result.get("tool_results")
    if not isinstance(explicit_tool_results, list) or not explicit_tool_results:
        return []

    normalized: list[ToolExecutionResult] = []
    for item in explicit_tool_results:
        if not isinstance(item, dict):
            continue
        normalized.append(
            ToolExecutionResult(
                tool_name=ToolName(str(item.get("tool_name"))),
                status=str(item.get("status", "ok")),
                payload=dict(item.get("payload", {})) if isinstance(item.get("payload", {}), dict) else {},
            )
        )
    return normalized
