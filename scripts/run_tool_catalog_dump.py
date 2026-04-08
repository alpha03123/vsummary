from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext, CandidateBufferEntry, InspectionStage
from backend.agent.schemas.tool_calls import ToolPlane
from backend.agent.tools import (
    list_model_visible_tool_definitions_for_context,
    list_tool_definitions_for_context,
    list_tool_definitions_for_plane,
)


def main() -> int:
    _print_plane_catalog()
    _print_context_catalogs()
    return 0


def _print_plane_catalog() -> None:
    print("=== tool-plane-catalog ===")
    for plane in ToolPlane:
        print(f"[{plane.value}]")
        for tool in list_tool_definitions_for_plane(plane):
            print(f"- {tool.name.value}: {tool.title}")
        print()


def _print_context_catalogs() -> None:
    print("=== tool-context-catalog ===")
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
            candidate_buffer=[CandidateBufferEntry(video_id="video-1", title="Video 1")],
        ),
        "video": AgentContext(
            session_id="video|agent-frameworks|video-1|overview",
            scope_type="video",
            series_id="agent-frameworks",
            video_id="video-1",
        ),
    }
    for label, context in contexts.items():
        tools = [
            {
                "name": tool.name.value,
                "plane": tool.plane.value,
                "batch_tag": tool.batch_tag,
            }
            for tool in list_tool_definitions_for_context(context)
        ]
        model_visible_tools = [
            tool.name.value
            for tool in list_model_visible_tool_definitions_for_context(context)
        ]
        print(f"[{label}]")
        print(json.dumps(tools, ensure_ascii=False, indent=2))
        print("model_visible:")
        print(json.dumps(model_visible_tools, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    raise SystemExit(main())
