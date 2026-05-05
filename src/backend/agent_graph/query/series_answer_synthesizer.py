from __future__ import annotations

import json

from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.prompts import SERIES_ANSWER_SYNTHESIZER_SYSTEM_PROMPT
from backend.agent_graph.query.models import RetrievalHit, SeriesAnswerPayload, SeriesQueryUnderstanding


class SeriesAnswerSynthesizer:
    def __init__(self, *, gateway) -> None:
        self._gateway = gateway

    def run(
        self,
        *,
        user_message: str,
        query_understanding: SeriesQueryUnderstanding,
        retrieval_hits: list[RetrievalHit],
        series_catalog: dict[str, object] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> SeriesAnswerPayload:
        messages = self._build_messages(
            user_message=user_message,
            query_understanding=query_understanding,
            retrieval_hits=retrieval_hits,
            series_catalog=series_catalog or {},
        )
        payload = self._gateway.create_structured_completion(
            messages,
            response_model=SeriesAnswerPayload,
        )
        if debug_trace is not None:
            debug_trace["answer_synthesis"] = {
                "input": {
                    "user_message": user_message,
                    "query_understanding": query_understanding.model_dump(mode="json"),
                    "series_catalog": series_catalog or {},
                    "retrieval_hits": [item.model_dump(mode="json") for item in retrieval_hits],
                    "messages": [item.model_dump(mode="json") for item in messages],
                },
                "output": payload.model_dump(mode="json"),
            }
        return payload

    def _build_messages(
        self,
        *,
        user_message: str,
        query_understanding: SeriesQueryUnderstanding,
        retrieval_hits: list[RetrievalHit],
        series_catalog: dict[str, object],
    ) -> list[AgentChatMessage]:
        catalog_videos = series_catalog.get("videos", [])
        if not isinstance(catalog_videos, list):
            raise ValueError("series_catalog.videos 必须是数组。")
        prompt_catalog = {
            **series_catalog,
            "video_count": len(catalog_videos),
        }
        return [
            AgentChatMessage(
                role="system",
                content=SERIES_ANSWER_SYNTHESIZER_SYSTEM_PROMPT,
            ),
            AgentChatMessage(
                role="user",
                content=(
                    f"user_message:\n{user_message}\n\n"
                    f"query_understanding:\n{json.dumps(query_understanding.model_dump(mode='json'), ensure_ascii=False, indent=2)}\n\n"
                    f"series_catalog:\n{json.dumps(prompt_catalog, ensure_ascii=False, indent=2)}\n\n"
                    f"retrieval_hits:\n{json.dumps([item.model_dump(mode='json') for item in retrieval_hits], ensure_ascii=False, indent=2)}"
                ),
            ),
        ]
