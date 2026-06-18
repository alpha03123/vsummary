"""基于 LiteLLM 的系列级思维导图生成适配器。

把 `SeriesMindmapGenerator` 端口绑定到 LiteLLM 入口：使用系列目录 +
各视频概况构造中文提示词，调用 LLM 输出结构化的 `MindmapNodePayload`
（节点/边字典）。
"""

from __future__ import annotations

import json

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.generation.ports import SeriesMindmapGenerator
from backend.video_summary.infrastructure.prompts import SERIES_MINDMAP_PROMPT_TEMPLATE
from backend.video_summary.generation import MindmapNodePayload


class LiteLLMSeriesMindmapGenerator(SeriesMindmapGenerator):
    """通过 LiteLLM 异步调用 LLM 生成系列级跨视频思维导图的实现。

    业务场景：在系列总结场景中，基于系列目录（series_catalog.json）和各视频
    概况列表，让 LLM 提炼出跨视频的知识结构思维导图节点/边数据。

    实现要点：
    - 提示词构造：把 `series_title` / `catalog`（JSON） / `video_summaries`
      注入到 `SERIES_MINDMAP_PROMPT_TEMPLATE` 模板；
    - 输出约束：使用 `MindmapNodePayload` Pydantic schema 强制 LLM 输出结构，
      失败时由 `LiteLLMCompletionGateway` 自动重试最多 3 次；
    - 错误处理：LLM 解析失败、网关超时等异常由网关层抛出，本适配器
      不做静默兜底。
    """

    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        """注入 LiteLLM 网关实例。

        Args:
            gateway: 提供 `acomplete_structured` 能力的 LLM 网关。
        """
        self._gateway = gateway

    async def generate(
        self,
        *,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
    ) -> dict[str, object]:
        """生成一次系列级跨视频思维导图节点/边字典。

        Args:
            series_title: 系列标题，用于在提示词中给 LLM 上下文。
            catalog: 系列目录数据字典，会被 JSON 序列化后注入提示词。
            video_summaries: 各视频概况列表，每个元素包含 title / one_sentence_summary / chapters 等字段。

        Returns:
            `MindmapNodePayload.model_dump()` 的纯字典结果，便于跨层传输
            与持久化。

        Raises:
            RuntimeError: LLM 返回无法通过 schema 校验且重试仍失败时抛出。
        """
        prompt = build_series_mindmap_prompt(
            series_title=series_title,
            catalog=catalog,
            video_summaries=video_summaries,
        )
        payload = await self._gateway.acomplete_structured(
            [{"role": "user", "content": prompt}],
            response_model=MindmapNodePayload,
            retries=3,
        )
        return payload.model_dump()


def build_series_mindmap_prompt(
    *,
    series_title: str,
    catalog: dict[str, object] | None,
    video_summaries: list[dict[str, object]],
) -> str:
    """渲染系列思维导图提示词模板。

    Args:
        series_title: 系列标题。
        catalog: 系列目录数据字典，使用 ensure_ascii=False 以保留中文。
        video_summaries: 各视频概况列表，对每个视频只保留 title / one_sentence_summary / chapter_titles 字段以控制上下文长度。

    Returns:
        渲染完成的提示词字符串。
    """
    catalog_json = json.dumps(catalog, ensure_ascii=False, indent=2) if catalog else "（无系列目录）"
    trimmed = [
        {
            "title": s.get("title", ""),
            "one_sentence_summary": s.get("one_sentence_summary", ""),
            "chapter_titles": [
                (c.get("title", "") or "")[:200] for c in (s.get("chapters", []) or []) if isinstance(c, dict)
            ],
        }
        for s in video_summaries
    ]
    return SERIES_MINDMAP_PROMPT_TEMPLATE.format(
        series_title=series_title,
        series_catalog_json=catalog_json,
        video_summaries_json=json.dumps(trimmed, ensure_ascii=False, indent=2),
    )
