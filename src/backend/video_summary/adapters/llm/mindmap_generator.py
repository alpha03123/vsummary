from __future__ import annotations

import json

from backend.llm_gateway import LiteLLMCompletionGateway
from backend.video_summary.summary_generation.ports import MindmapGenerator
from backend.video_summary.adapters.llm.prompts import MINDMAP_PROMPT_TEMPLATE
from backend.video_summary.summary_generation import MindmapNodePayload


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
    return MINDMAP_PROMPT_TEMPLATE.format(
        title=title,
        duration_seconds=int(duration_seconds),
        summary_json=json.dumps(summary_data, ensure_ascii=False, indent=2),
    )
