"""系列级 query 理解阶段：把用户问题改写为统一检索合同。

`SeriesQueryProcessor` 是 series scope 的第一个 LangGraph 节点
`understand_query` 的实现：基于用户原始消息、系列目录与 Session memory，
让 LLM 输出 `SeriesQueryUnderstanding`（normalized_query / subqueries /
filters），供下游 `retrieve_evidence` 节点复用。本模块不直接执行检索。
"""

from __future__ import annotations

import json

from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.prompts import SERIES_QUERY_PROCESSOR_SYSTEM_PROMPT
from backend.agent_graph.query.models import SeriesQueryUnderstanding


class SeriesQueryProcessor:
    """series scope 的 query 理解器，封装"用户问题 → 检索合同"的 LLM 调用。

    业务定位：作为 series talk 流程的"前置语义层"，负责把口语化的用户
    问题改写为更适合 RAG 检索的形态（拆子问题、提取过滤条件），但本身
    不接触向量库；实际检索交给 `SeriesRetrievalService`。
    """

    def __init__(self, *, gateway) -> None:
        """注入 LLM 结构化补全网关。

        Args:
            gateway: 提供 `create_structured_completion` 的 LLM 入口。
        """
        self._gateway = gateway

    def run(
        self,
        *,
        user_message: str,
        series_id: str,
        series_title: str,
        series_catalog: dict[str, object],
        memory_messages: list[dict[str, object]] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> SeriesQueryUnderstanding:
        """执行一次结构化补全，得到改写后的 `SeriesQueryUnderstanding`。

        实现要点：
        - 在 LLM 输出后强制把 `series_id` 写入 `filters`，确保下游检索
          不会跨系列泄漏；
        - 若传入 `debug_trace`，会在其上写入 `series_query_processor.input`
          与 `series_query_processor.output` 两段，便于排查。

        Args:
            user_message: 用户原始问题。
            series_id: 当前系列 ID，会被强制写入 `filters["series_id"]`。
            series_title: 当前系列标题，注入 user 消息便于 LLM 解析指代。
            series_catalog: 系列目录信息（视频列表等）。
            memory_messages: Session memory 中的历史消息。
            debug_trace: 可选的调试 trace 容器。

        Returns:
            含 `normalized_query` / `subqueries` / `filters` 的查询合同；
            其中 `filters` 至少包含 `series_id`。
        """
        messages = self._build_messages(
            user_message=user_message,
            series_id=series_id,
            series_title=series_title,
            series_catalog=series_catalog,
            memory_messages=memory_messages or [],
        )
        result = self._gateway.create_structured_completion(
            messages,
            response_model=SeriesQueryUnderstanding,
        )
        result.filters["series_id"] = series_id
        if debug_trace is not None:
            debug_trace["series_query_processor"] = {
                "input": {
                    "user_message": user_message,
                    "series_id": series_id,
                    "series_title": series_title,
                },
                "output": result.model_dump(mode="json"),
            }
        return result

    def _build_messages(
        self,
        *,
        user_message: str,
        series_id: str,
        series_title: str,
        series_catalog: dict[str, object],
        memory_messages: list[dict[str, object]],
    ) -> list[AgentChatMessage]:
        """构造 query 理解阶段的两段式 LLM 消息（system + user）。

        Args:
            user_message: 用户原始问题。
            series_id: 当前系列 ID。
            series_title: 当前系列标题。
            series_catalog: 系列目录信息。
            memory_messages: Session memory 历史消息；会被格式化为
                `role: content` 的行集合。

        Returns:
            `[system_message, user_message]` 形式的 LLM 消息列表。
        """
        memory_block = "\n".join(
            f"{str(item.get('role', '')).strip()}: {str(item.get('content', '')).strip()}"
            for item in memory_messages
            if isinstance(item, dict) and str(item.get("content", "")).strip()
        ).strip() or "(none)"
        return [
            AgentChatMessage(
                role="system",
                content=SERIES_QUERY_PROCESSOR_SYSTEM_PROMPT,
            ),
            AgentChatMessage(
                role="user",
                content=(
                    f"series_id: {series_id}\n"
                    f"series_title: {series_title}\n\n"
                    f"memory_messages:\n{memory_block}\n\n"
                    f"series_catalog:\n{json.dumps(series_catalog, ensure_ascii=False, indent=2)}\n\n"
                    f"user_message:\n{user_message}"
                ),
            ),
        ]
