from __future__ import annotations

import json

from pydantic import BaseModel

from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.prompts import VIDEO_ANSWER_SYNTHESIZER_SYSTEM_PROMPT, build_answer_detail_level_prompt


class VideoAnswerPayload(BaseModel):
    answer: str


class AnswerSynthesisProgram:
    def __init__(self, *, gateway, answer_detail_level: str = "medium") -> None:
        self._gateway = gateway
        self._answer_detail_level = answer_detail_level

    def run(
        self,
        *,
        user_message: str,
        memory_messages: list[dict[str, object]] | None = None,
        retrieval_results: list[dict[str, object]] | None = None,
        evidence_items: list[dict[str, object]] | None = None,
        meta_state: dict[str, object] | None = None,
    ) -> str:
        normalized_evidence_items = evidence_items if evidence_items is not None else retrieval_results or []
        payload = self._gateway.create_structured_completion(
            self._build_messages(
                user_message=user_message,
                memory_messages=memory_messages or [],
                evidence_items=normalized_evidence_items,
                meta_state=meta_state or {},
            ),
            response_model=VideoAnswerPayload,
        )
        if not payload.answer.strip():
            raise ValueError("视频回答合成缺少 answer。")
        return payload.answer.strip()

    def build_text_messages(
        self,
        *,
        user_message: str,
        memory_messages: list[dict[str, object]] | None = None,
        retrieval_results: list[dict[str, object]] | None = None,
        evidence_items: list[dict[str, object]] | None = None,
        meta_state: dict[str, object] | None = None,
    ) -> list[AgentChatMessage]:
        normalized_evidence_items = evidence_items if evidence_items is not None else retrieval_results or []
        return self._build_messages(
            user_message=user_message,
            memory_messages=memory_messages or [],
            evidence_items=_number_evidence_items(normalized_evidence_items),
            meta_state=meta_state or {},
            text_only=True,
        )

    def _build_messages(
        self,
        *,
        user_message: str,
        memory_messages: list[dict[str, object]],
        evidence_items: list[dict[str, object]],
        meta_state: dict[str, object],
        text_only: bool = False,
    ) -> list[AgentChatMessage]:
        return [
            AgentChatMessage(
                role="system",
                content=(
                    VIDEO_ANSWER_SYNTHESIZER_SYSTEM_PROMPT
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
                    f"memory_messages:\n{json.dumps(memory_messages, ensure_ascii=False, indent=2)}\n\n"
                    f"evidence_items:\n{json.dumps(evidence_items, ensure_ascii=False, indent=2)}\n\n"
                    f"meta_state:\n{json.dumps(meta_state, ensure_ascii=False, indent=2)}"
                ),
            ),
        ]


_STREAMING_CITED_ANSWER_PROMPT = (
    "\n流式引用输出要求：\n"
    "- 只输出 answer 字段对应的 Markdown 回答正文。\n"
    "- evidence_items 已按 Source 1、Source 2 等数字编号。\n"
    "- 使用某条 Source 支持句子或段落时，在该句或段落末尾插入对应的数字引用，例如 [1] 或 [2]。\n"
    "- 只能使用真实存在的 Source 编号，不要输出 evidence_id、local-*、web-* 或 e* 这类内部 ID，不要编造引用编号。\n"
    "- 不要输出 JSON，不要输出额外字段。\n"
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
