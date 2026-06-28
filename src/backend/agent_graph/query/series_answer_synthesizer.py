"""系列级 answer synthesis 阶段：把证据 + 系列目录合成为结构化回答。

`SeriesAnswerSynthesizer` 负责 series scope 的"最后一公里"：把 query
理解结果、RAG 检索命中、可选联网证据、系列目录与历史 memory 注入
LLM，得到符合 `SeriesAnswerPayload` schema 的回答，同时为流式输出
提供一份仅含 Markdown 正文 + 数字引用（`[1]`/`[2]` ...）的消息集合。
"""

from __future__ import annotations

import json

from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.evidence.transcript_anchors import number_evidence_items_for_citations
from backend.agent_graph.prompts import (
    SERIES_ANSWER_SYNTHESIZER_SYSTEM_PROMPT,
    build_answer_detail_level_prompt,
    build_talk_custom_prompt,
)
from backend.agent_graph.query.models import RetrievalHit, SeriesAnswerPayload, SeriesQueryUnderstanding


class SeriesAnswerSynthesizer:
    """把系列级证据 + 目录 + memory 合成最终结构化回答的合成器。

    业务场景：series scope 的 LangGraph 节点在完成检索与可选联网之后，
    调用本合成器生成符合 `SeriesAnswerPayload` schema 的最终回答。
    同一组合成器也支持"流式引用输出"模式 —— 此时只产出 Markdown 正文
    与 `[1]`/`[2]` 形式的数字引用，便于前端按块渲染。
    """

    def __init__(self, *, gateway, answer_detail_level: str = "medium", talk_custom_prompt: str = "") -> None:
        """注入 LLM 网关与回答风格参数。

        Args:
            gateway: 提供 `create_structured_completion` 的结构化补全入口。
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
        query_understanding: SeriesQueryUnderstanding,
        retrieval_hits: list[RetrievalHit] | None = None,
        evidence_items: list[dict[str, object]] | None = None,
        series_catalog: dict[str, object] | None = None,
        memory_messages: list[dict[str, object]] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> SeriesAnswerPayload:
        """执行一次结构化补全，得到完整的 `SeriesAnswerPayload`。

        优先使用上游已经合并好的 `evidence_items`；若上游未传，再回退到
        把 `retrieval_hits` 通过 `model_dump` 转成字典形式注入。

        Args:
            user_message: 用户原始问题。
            query_understanding: `SeriesQueryProcessor` 的改写结果。
            retrieval_hits: 备用输入 —— 当 `evidence_items` 为 `None` 时使用。
            evidence_items: 上游已归一化的证据列表（已与可选联网证据合并）。
            series_catalog: 系列目录信息（含视频列表等）。
            memory_messages: Session memory 中的历史消息。
            debug_trace: 可选的调试 trace 容器；传入时会写入
                `answer_synthesis.input` 与 `answer_synthesis.output`。

        Returns:
            LLM 输出的 `SeriesAnswerPayload`，含 `answer` Markdown、
            `citations` evidence_id 列表、`used_source_types`。
        """
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
        """构造仅输出 Markdown + 数字引用的"流式引用"消息集合。

        与 `run` 的差别：本方法不会调用 LLM，而是构造两份可直接送入
        流式 chat 入口的 `AgentChatMessage`：在 system prompt 末尾追加
        `_STREAMING_CITED_ANSWER_PROMPT` 并对证据做数字编号，使模型在
        流式输出时只产出 Markdown 正文与 `[1]`/`[2]` 等数字引用。

        Args:
            user_message: 用户原始问题。
            query_understanding: `SeriesQueryProcessor` 的改写结果。
            retrieval_hits: 备用输入 —— 当 `evidence_items` 为 `None` 时使用。
            evidence_items: 上游已归一化的证据列表。
            series_catalog: 系列目录信息。
            memory_messages: Session memory 中的历史消息。

        Returns:
            `[system_message, user_message]` 形式的可流式发送的消息列表。
        """
        normalized_evidence_items = _normalize_evidence_items(
            evidence_items=evidence_items,
            retrieval_hits=retrieval_hits or [],
        )
        return self._build_messages(
            user_message=user_message,
            query_understanding=query_understanding,
            evidence_items=number_evidence_items_for_citations(normalized_evidence_items),
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
        """构造最终送入 LLM 的两段式消息（system + user）。

        关键行为：
        - 在 `series_catalog` 顶层补一个 `video_count` 字段，便于 LLM 在
          评估"系列覆盖度"时直接拿到数量；
        - `text_only=True` 时在 system prompt 末尾追加流式引用约束片段，
          让模型按 `[1]`/`[2]` 等数字编号引用 Source。

        Args:
            user_message: 用户原始问题。
            query_understanding: 改写后的查询合同。
            evidence_items: 已归一化的证据字典列表。
            series_catalog: 系列目录；必须是含 `videos` 字段的字典。
            memory_messages: Session memory 中的历史消息。
            text_only: 为 `True` 时启用流式引用输出模式。

        Returns:
            `[system_message, user_message]` 形式的 LLM 消息列表。

        Raises:
            ValueError: `series_catalog.videos` 不是数组时抛出。
        """
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
                    + build_talk_custom_prompt(self._talk_custom_prompt)
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
    """把"上游 evidence_items"或"原始检索命中"归一化为 dict 列表。

    Args:
        evidence_items: 上游已经合并过的证据字典列表；非 `None` 时优先使用。
        retrieval_hits: 备选输入 —— 当 `evidence_items` 为 `None` 时，
            通过 `model_dump(mode="json")` 转成字典列表。

    Returns:
        可直接 JSON 序列化的证据字典列表；不修改原对象（对 dict 做浅拷贝）。
    """
    if evidence_items is not None:
        return [dict(item) for item in evidence_items]
    return [item.model_dump(mode="json") for item in retrieval_hits]


# 追加到流式输出 system prompt 末尾的约束片段。
#
# 目的：让模型在流式输出场景下只产出 Markdown 回答正文 + citation
# marker，不要输出 JSON、citations、used_source_types 等结构化
# 字段，也不要暴露 evidence_id、local-*、web-*、e* 等内部 ID。
_STREAMING_CITED_ANSWER_PROMPT = (
    "\n流式引用输出要求：\n"
    "- 只输出 answer 字段对应的 Markdown 回答正文。\n"
    "- evidence_items 已按 Source 1、Source 2 等数字编号。\n"
    "- summary / web evidence 使用 Source 编号引用，例如 [1] 或 [2]。\n"
    "- transcript evidence 如果包含 segments，必须使用 segment 的 anchor_id 引用，例如 [2.1]，不要用粗粒度 [2]。\n"
    "- 只能使用真实存在的 Source 编号或 transcript anchor_id，不要输出 evidence_id、local-*、web-* 或 e* 这类内部 ID，不要编造引用编号。\n"
    "- 不要输出 JSON，不要输出 citations 或 used_source_types 字段。\n"
)
