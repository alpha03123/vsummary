from __future__ import annotations

import json

from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.query.models import SeriesQueryUnderstanding


class SeriesQueryProcessor:
    def __init__(self, *, gateway) -> None:
        self._gateway = gateway

    def run(
        self,
        *,
        user_message: str,
        series_id: str,
        series_title: str,
        series_catalog: dict[str, object],
        dialog_history: str = "",
        history_messages: list[dict[str, object]] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> SeriesQueryUnderstanding:
        messages = self._build_messages(
            user_message=user_message,
            series_id=series_id,
            series_title=series_title,
            series_catalog=series_catalog,
            dialog_history=dialog_history,
            history_messages=history_messages or [],
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
        dialog_history: str,
        history_messages: list[dict[str, object]],
    ) -> list[AgentChatMessage]:
        if dialog_history.strip():
            history_block = dialog_history.strip()
        else:
            history_block = "\n".join(
                f"{str(item.get('role', '')).strip()}: {str(item.get('content', '')).strip()}"
                for item in history_messages
                if isinstance(item, dict) and str(item.get("content", "")).strip()
            ).strip() or "(none)"
        return [
            AgentChatMessage(
                role="system",
                content=(
                    "你是 series 查询理解器。"
                    "你只负责把用户问题改写成更适合统一检索的查询合同。"
                    "不要输出 selected_videos、subplans、target_video_ids、task_type、retrieval_hints。"
                    "只输出 normalized_query、subqueries、filters。"
                    "filters 中必须保留 series_id。"
                ),
            ),
            AgentChatMessage(
                role="user",
                content=(
                    f"series_id: {series_id}\n"
                    f"series_title: {series_title}\n\n"
                    f"dialog_history:\n{history_block}\n\n"
                    f"series_catalog:\n{json.dumps(series_catalog, ensure_ascii=False, indent=2)}\n\n"
                    f"user_message:\n{user_message}"
                ),
            ),
        ]
