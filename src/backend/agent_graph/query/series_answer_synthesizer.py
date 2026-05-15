from __future__ import annotations

import json

from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.prompts import SERIES_ANSWER_SYNTHESIZER_SYSTEM_PROMPT, build_answer_detail_level_prompt
from backend.agent_graph.query.models import RetrievalHit, SeriesAnswerPayload, SeriesQueryUnderstanding


class SeriesAnswerSynthesizer:
    def __init__(self, *, gateway, answer_detail_level: str = "medium") -> None:
        self._gateway = gateway
        self._answer_detail_level = answer_detail_level

    def run(
        self,
        *,
        user_message: str,
        query_understanding: SeriesQueryUnderstanding,
        retrieval_hits: list[RetrievalHit] | None = None,
        evidence_items: list[dict[str, object]] | None = None,
        series_catalog: dict[str, object] | None = None,
        memory_messages: list[dict[str, object]] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> SeriesAnswerPayload:
        normalized_evidence_items = _normalize_evidence_items(
            evidence_items=evidence_items,
            retrieval_hits=retrieval_hits or [],
        )
        messages = self._build_messages(
            user_message=user_message,
            query_understanding=query_understanding,
            evidence_items=normalized_evidence_items,
            series_catalog=series_catalog or {},
            memory_messages=memory_messages or [],
        )
        payload = self._gateway.create_structured_completion(
            messages,
            response_model=SeriesAnswerPayload,
        )
        if debug_trace is not None:
            debug_trace["answer_synthesis"] = {
                "input": {
                    "user_message": user_message,
                    "answer_detail_level": self._answer_detail_level,
                    "query_understanding": query_understanding.model_dump(mode="json"),
                    "memory_messages": memory_messages or [],
                    "series_catalog": series_catalog or {},
                    "evidence_items": normalized_evidence_items,
                    "messages": [item.model_dump(mode="json") for item in messages],
                },
                "output": payload.model_dump(mode="json"),
            }
        return payload

    def build_text_messages(
        self,
        *,
        user_message: str,
        query_understanding: SeriesQueryUnderstanding,
        retrieval_hits: list[RetrievalHit] | None = None,
        evidence_items: list[dict[str, object]] | None = None,
        series_catalog: dict[str, object] | None = None,
        memory_messages: list[dict[str, object]] | None = None,
    ) -> list[AgentChatMessage]:
        normalized_evidence_items = _normalize_evidence_items(
            evidence_items=evidence_items,
            retrieval_hits=retrieval_hits or [],
        )
        return self._build_messages(
            user_message=user_message,
            query_understanding=query_understanding,
            evidence_items=_number_evidence_items(normalized_evidence_items),
            series_catalog=series_catalog or {},
            memory_messages=memory_messages or [],
            text_only=True,
        )

    def _build_messages(
        self,
        *,
        user_message: str,
        query_understanding: SeriesQueryUnderstanding,
        evidence_items: list[dict[str, object]],
        series_catalog: dict[str, object],
        memory_messages: list[dict[str, object]],
        text_only: bool = False,
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
                content=(
                    SERIES_ANSWER_SYNTHESIZER_SYSTEM_PROMPT
                    + "\n"
                    + build_answer_detail_level_prompt(self._answer_detail_level)
                    + (_STREAMING_CITED_ANSWER_PROMPT if text_only else "")
                ),
            ),
            AgentChatMessage(
                role="user",
                content=(
                    f"user_message:\n{user_message}\n\n"
                    f"answer_detail_level:\n{self._answer_detail_level}\n\n"
                    f"query_understanding:\n{json.dumps(query_understanding.model_dump(mode='json'), ensure_ascii=False, indent=2)}\n\n"
                    f"memory_messages:\n{json.dumps(memory_messages, ensure_ascii=False, indent=2)}\n\n"
                    f"series_catalog:\n{json.dumps(prompt_catalog, ensure_ascii=False, indent=2)}\n\n"
                    f"evidence_items:\n{json.dumps(evidence_items, ensure_ascii=False, indent=2)}"
                ),
            ),
        ]


def _normalize_evidence_items(
    *,
    evidence_items: list[dict[str, object]] | None,
    retrieval_hits: list[RetrievalHit],
) -> list[dict[str, object]]:
    if evidence_items is not None:
        return [dict(item) for item in evidence_items]
    return [item.model_dump(mode="json") for item in retrieval_hits]


_STREAMING_CITED_ANSWER_PROMPT = (
    "\n流式引用输出要求：\n"
    "- 只输出 answer 字段对应的 Markdown 回答正文。\n"
    "- evidence_items 已按 Source 1、Source 2 等数字编号。\n"
    "- 使用某条 Source 支持句子或段落时，在该句或段落末尾插入对应的数字引用，例如 [1] 或 [2]。\n"
    "- 只能使用真实存在的 Source 编号，不要输出 evidence_id、local-*、web-* 或 e* 这类内部 ID，不要编造引用编号。\n"
    "- 不要输出 JSON，不要输出 citations 或 used_source_types 字段。\n"
)


def _number_evidence_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            **item,
            "source_number": index,
            "source_label": f"Source {index}",
        }
        for index, item in enumerate(items, start=1)
    ]
