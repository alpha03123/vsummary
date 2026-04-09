from __future__ import annotations

import json

from backend.agent.memory.context import AgentContext


def render_model_visible_context_json(context: AgentContext) -> str:
    return json.dumps(build_model_visible_context(context), ensure_ascii=False, indent=2)


def build_model_visible_context(context: AgentContext) -> dict[str, object]:
    payload = context.model_dump(mode="json")
    payload.pop("inspection_stage", None)
    return payload
