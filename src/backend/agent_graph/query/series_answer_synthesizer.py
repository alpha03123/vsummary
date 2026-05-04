from __future__ import annotations

import json

from backend.agent.schemas.messages import AgentChatMessage
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
        debug_trace: dict[str, object] | None = None,
    ) -> SeriesAnswerPayload:
        messages = self._build_messages(
            user_message=user_message,
            query_understanding=query_understanding,
            retrieval_hits=retrieval_hits,
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
                    "retrieval_hits": [item.model_dump(mode="json") for item in retrieval_hits],
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
    ) -> list[AgentChatMessage]:
        return [
            AgentChatMessage(
                role="system",
                content=(
                    "你是 series 回答合成器。"
                    "你只能基于给定 evidence 回答。"
                    "输出 answer、citations、used_source_types。"
                    "不要输出 doc_id、score 等内部字段。"
                ),
            ),
            AgentChatMessage(
                role="user",
                content=(
                    f"user_message:\n{user_message}\n\n"
                    f"query_understanding:\n{json.dumps(query_understanding.model_dump(mode='json'), ensure_ascii=False, indent=2)}\n\n"
                    f"retrieval_hits:\n{json.dumps([item.model_dump(mode='json') for item in retrieval_hits], ensure_ascii=False, indent=2)}"
                ),
            ),
        ]
