from __future__ import annotations

import json

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.generation.ports import MindmapGenerator
from backend.video_summary.infrastructure.structured_generation import MindmapNodePayload


class LiteLLMMindmapGenerator(MindmapGenerator):
    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        self._gateway = gateway

    async def generate(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
    ) -> dict[str, object]:
        prompt = build_mindmap_prompt(
            title=title,
            duration_seconds=duration_seconds,
            summary_data=summary_data,
        )
        payload = await self._gateway.acomplete_structured(
            [{"role": "user", "content": prompt}],
            response_model=MindmapNodePayload,
            retries=3,
        )
        return payload.model_dump()


def build_mindmap_prompt(*, title: str, duration_seconds: float, summary_data: dict[str, object]) -> str:
    return (
        "请基于以下视频概况信息，生成一个适合前端交互展示的思维导图 JSON。\n"
        "要求：\n"
        "1. 只输出 JSON，不要输出额外解释。\n"
        "2. 不要编造 summary 中不存在的信息。\n"
        "3. 导图节点必须是树结构，且每个节点都包含 id、title、summary、start_seconds、end_seconds、children。\n"
        "4. 请按知识结构组织节点，而不是机械复述章节目录；可以参考章节，但不要被时间顺序束缚。\n"
        "5. 层级深度由内容复杂度决定：简单主题可以较浅，复杂主题可以自然展开到更深层，但每一层都必须有信息价值。\n"
        "6. 节点标题尽量简洁，优先使用关键词或短语，不要把整句摘要直接当标题。\n"
        "7. 时间范围必须落在视频时长内。\n\n"
        f"视频标题：{title}\n"
        f"视频时长秒数：{int(duration_seconds)}\n"
        "概况 JSON：\n"
        f"{json.dumps(summary_data, ensure_ascii=False, indent=2)}\n"
    )
