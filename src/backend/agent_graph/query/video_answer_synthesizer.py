"""video scope 的 answer synthesis 阶段：基于当前视频资料合成回答。

`AnswerSynthesisProgram` 负责 video talk 流程的最后一公里：把视频
evidence（概况/完整字幕/字幕检索片段 + 可选联网证据）、历史 memory 与
`meta_state` 注入 LLM，输出一个仅含 `answer` Markdown 的结构化结果，
同时为流式输出提供一份带数字引用（`[1]`/`[2]` ...）的消息集合。
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.evidence.transcript_anchors import number_evidence_items_for_citations
from backend.agent_graph.prompts import (
    VIDEO_ANSWER_SYNTHESIZER_SYSTEM_PROMPT,
    build_answer_detail_level_prompt,
    build_talk_custom_prompt,
)


class VideoAnswerPayload(BaseModel):
    """video answer synthesis 的结构化输出。

    Attributes:
        answer: 完整的 Markdown 回答正文；不包含 doc_id 等内部 ID。
    """

    answer: str


class AnswerSynthesisProgram:
    """video scope 的"程序化 answer 合成器"（即 video talk 的最终回答节点）。

    业务场景：video talk 流程在完成 `build_video_context` / 可选联网检索
    与工具执行后，会调用本合成器把"当前资料 + memory + meta_state"统一
    喂给 LLM，得到一个可直接发给用户的 Markdown 回答。本类同时支持
    "流式引用输出"，即让模型在流式返回时只产出 `[1]`/`[2]` 这类数字引用。
    """

    def __init__(self, *, gateway, answer_detail_level: str = "medium", talk_custom_prompt: str = "") -> None:
        """注入 LLM 网关与回答风格参数。

        Args:
            gateway: 提供 `create_structured_completion` 的 LLM 入口。
            answer_detail_level: 回答长度偏好，取值 `short` / `medium` / `long`，
                注入到 system prompt 中由 LLM 自行遵循。
            talk_custom_prompt: 用户在"Talk"模式下配置的自定义风格提示词；
                为空字符串时不注入额外约束。
        """
        self._gateway = gateway
        self._answer_detail_level = answer_detail_level
        self._talk_custom_prompt = talk_custom_prompt

    def run(
        self,
        *,
        user_message: str,
        memory_messages: list[dict[str, object]] | None = None,
        retrieval_results: list[dict[str, object]] | None = None,
        evidence_items: list[dict[str, object]] | None = None,
        meta_state: dict[str, object] | None = None,
    ) -> str:
        """执行一次结构化补全并返回 Markdown `answer` 文本。

        实现要点：
        - 优先使用 `evidence_items`；若未传，则回退到 `retrieval_results`；
        - 对模型返回的空 `answer` 主动抛错，避免静默给出空回答。

        Args:
            user_message: 用户原始问题。
            memory_messages: Session memory 中的历史消息。
            retrieval_results: 备用输入 —— 当 `evidence_items` 为 `None` 时使用。
            evidence_items: 已归一化的证据列表（已与可选联网证据合并）。
            meta_state: 视频级上下文状态（如当前播放位置、笔记列表等）。

        Returns:
            去首尾空白后的 Markdown 回答正文。

        Raises:
            ValueError: 模型返回的 `answer` 为空字符串或仅含空白。
        """
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
        """构造仅输出 Markdown + 数字引用的"流式引用"消息集合。

        与 `run` 的差别：本方法不会调用 LLM，而是构造两份可直接送入
        流式 chat 入口的 `AgentChatMessage`：在 system prompt 末尾追加
        `_STREAMING_CITED_ANSWER_PROMPT` 并对证据做数字编号，使模型在
        流式输出时只产出 Markdown 正文与 `[1]`/`[2]` 等数字引用。

        Args:
            user_message: 用户原始问题。
            memory_messages: Session memory 中的历史消息。
            retrieval_results: 备用输入 —— 当 `evidence_items` 为 `None` 时使用。
            evidence_items: 已归一化的证据列表。
            meta_state: 视频级上下文状态。

        Returns:
            `[system_message, user_message]` 形式的可流式发送的消息列表。
        """
        normalized_evidence_items = evidence_items if evidence_items is not None else retrieval_results or []
        return self._build_messages(
            user_message=user_message,
            memory_messages=memory_messages or [],
            evidence_items=number_evidence_items_for_citations(normalized_evidence_items),
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
        """构造最终送入 LLM 的两段式消息（system + user）。

        关键行为：
        - `text_only=True` 时在 system prompt 末尾追加流式引用约束片段，
          让模型按 `[1]`/`[2]` 等数字编号引用 Source；
        - `meta_state`（如当前视频播放位置、当前笔记）作为独立字段注入，
          便于模型在回答中引用上下文状态。

        Args:
            user_message: 用户原始问题。
            memory_messages: Session memory 历史消息。
            evidence_items: 已归一化的证据字典列表。
            meta_state: 视频级上下文状态。
            text_only: 为 `True` 时启用流式引用输出模式。

        Returns:
            `[system_message, user_message]` 形式的 LLM 消息列表。
        """
        return [
            AgentChatMessage(
                role="system",
                content=(
                    VIDEO_ANSWER_SYNTHESIZER_SYSTEM_PROMPT
                    + "\n"
                    + build_answer_detail_level_prompt(self._answer_detail_level)
                    + build_talk_custom_prompt(self._talk_custom_prompt)
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


# 追加到流式输出 system prompt 末尾的约束片段。
#
# 目的：让模型在流式输出场景下只产出 Markdown 回答正文 + citation
# marker，不要输出 JSON、doc_id 等内部 ID，也不要输出额外字段。
_STREAMING_CITED_ANSWER_PROMPT = (
    "\n流式引用输出要求：\n"
    "- 只输出 answer 字段对应的 Markdown 回答正文。\n"
    "- evidence_items 已按 Source 1、Source 2 等数字编号。\n"
    "- summary / web evidence 使用 Source 编号引用，例如 [1] 或 [2]。\n"
    "- transcript evidence 如果包含 segments，必须使用 segment 的 anchor_id 引用，例如 [2.1]，不要用粗粒度 [2]。\n"
    "- 只能使用真实存在的 Source 编号或 transcript anchor_id，不要输出 evidence_id、local-*、web-* 或 e* 这类内部 ID，不要编造引用编号。\n"
    "- 不要输出 JSON，不要输出额外字段。\n"
)
