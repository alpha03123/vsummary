from __future__ import annotations

import json

from backend.video_summary.generation.ports import MindmapGenerator
from backend.video_summary.infrastructure.openai_summary import MindmapNodePayload, OpenAICompletionGateway


class OpenAIMindmapGenerator(MindmapGenerator):
    def __init__(self, gateway: OpenAICompletionGateway) -> None:
        self._gateway = gateway

    async def generate(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
    ) -> dict[str, object]:
        prompt = build_mindmap_prompt(title=title, duration_seconds=duration_seconds, summary_data=summary_data)
        payload = await self._gateway.create_structured_completion(
            prompt=prompt,
            response_model=MindmapNodePayload,
        )
        return payload.model_dump()


def build_mindmap_prompt(*, title: str, duration_seconds: float, summary_data: dict[str, object]) -> str:
    return (
        "请基于以下视频概况信息，生成一个适合前端交互展示的思维导图 JSON。\n"
        "要求：\n"
        "1. 只输出 JSON，不要输出额外解释。\n"
        "2. 不要编造 summary 中不存在的信息。\n"
        "3. 导图节点必须是树结构，且每个节点都包含 id、title、summary、start_seconds、end_seconds、children。\n"
        "4. 一级节点尽量对应视频主章节，二三级节点用于展开要点。\n"
        "5. 时间范围必须落在视频时长内。\n\n"
        f"视频标题：{title}\n"
        f"视频时长秒数：{int(duration_seconds)}\n"
        "概况 JSON：\n"
        f"{json.dumps(summary_data, ensure_ascii=False, indent=2)}\n"
    )
