from __future__ import annotations

from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


def extract_assistant_message(result: dict[str, object]) -> str:
    return str(
        result.get("assistant_message")
        or result.get("answer", "")
    ).strip()


def extract_reason(result: dict[str, object]) -> str:
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
def merge_evidence_history(*, current: dict[str, object], result: dict[str, object]) -> dict[str, object]:
    merged = dict(current)
    evidence_history = result.get("evidence_history", {})
    if isinstance(evidence_history, dict):
        merged.update(evidence_history)
    return merged


def extract_history_summary_update(
    result: dict[str, object],
    *,
    fallback: str,
) -> str:
    return str(result.get("history_summary_update") or fallback or "")
