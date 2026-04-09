from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.agent.prompt import build_agent_responder_prompt
from backend.agent.context.budget import _estimate_tokens
from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.runtime.note_drafter import VIDEO_NOTE_DRAFTER_SYSTEM_PROMPT
from backend.agent.runtime.request_router import REQUEST_ROUTER_SYSTEM_PROMPT
from backend.agent.runtime.routed_answerer import ROUTED_ANSWERER_SYSTEM_PROMPT
from backend.agent.runtime.series_locator import SERIES_LOCATOR_SYSTEM_PROMPT
from backend.agent.runtime.video_seek_locator import VIDEO_SEEK_LOCATOR_SYSTEM_PROMPT
from backend.agent.tools import list_model_visible_tool_definitions_for_context


def main() -> int:
    contexts = {
        "series_discovery": AgentContext(
            session_id="series|agent-frameworks|series-home",
            scope_type="series",
            series_id="agent-frameworks",
            inspection_stage=InspectionStage.SERIES_DISCOVERY,
        ),
        "series_inspection": AgentContext(
            session_id="series|agent-frameworks|series-home",
            scope_type="series",
            series_id="agent-frameworks",
            inspection_stage=InspectionStage.VIDEO_INSPECTION,
        ),
        "video": AgentContext(
            session_id="video|agent-frameworks|video-1|overview",
            scope_type="video",
            series_id="agent-frameworks",
            video_id="video-1",
        ),
    }

    print("=== prompt-size-report ===")
    for label, context in contexts.items():
        responder_prompt = build_agent_responder_prompt(context)
        payload = {
            "router_chars": len(REQUEST_ROUTER_SYSTEM_PROMPT),
            "router_estimated_tokens": _estimate_tokens(REQUEST_ROUTER_SYSTEM_PROMPT),
            "routed_answerer_chars": len(ROUTED_ANSWERER_SYSTEM_PROMPT),
            "routed_answerer_estimated_tokens": _estimate_tokens(ROUTED_ANSWERER_SYSTEM_PROMPT),
            "responder_chars": len(responder_prompt),
            "responder_estimated_tokens": _estimate_tokens(responder_prompt),
            "series_locator_estimated_tokens": _estimate_tokens(SERIES_LOCATOR_SYSTEM_PROMPT),
            "video_seek_locator_estimated_tokens": _estimate_tokens(VIDEO_SEEK_LOCATOR_SYSTEM_PROMPT),
            "note_drafter_estimated_tokens": _estimate_tokens(VIDEO_NOTE_DRAFTER_SYSTEM_PROMPT),
            "model_visible_tools": [
                tool.name.value
                for tool in list_model_visible_tool_definitions_for_context(context)
            ],
        }
        print(f"[{label}]")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
