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
                content=(
                    "你是一位专业的学习助手，擅长根据课程内容为学习者提供清晰、有帮助的解答。\n"
                    "你的回答应当：\n"
                    "- 结构清晰，适当使用分点或分段\n"
                    "- 充分展开内容，帮助学习者真正理解，而不是简单罗列\n"
                    "- 只基于提供的 evidence 内容作答，不要编造\n"
                    "- series_catalog 是当前系列目录的确定性上下文；回答视频总数、视频清单、课程目录时必须优先使用它\n"
                    "- retrieval_hits 是按问题检索出的内容证据，可能不覆盖完整系列，不得用命中数量推断课程总数\n"
                    "- 避免在回答过程中参杂emoji"
                    "- 使用 Markdown 格式输出，合理使用标题、列表、加粗等增强可读性\n\n"
                    "输出字段说明：\n"
                    "- answer：完整的回答正文，不得包含任何内部 ID（如 e1、e2、doc_id 等）\n"
                    "- citations：引用的 evidence_id 数组，仅用于系统内部追踪，不要在 answer 中提及\n"
                    "- used_source_types：本次回答使用到的来源类型列表\n"
   
                ),
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
