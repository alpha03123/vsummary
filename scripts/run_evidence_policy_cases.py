from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.runtime.evidence_policy import build_followup_plan
from backend.agent.schemas.action_plan import AgentActionPlan, IntentType, ScopeType
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


def main() -> int:
    for case in _build_cases():
        print(f"=== evidence-case: {case['id']} ===")
        print(f"note: {case['note']}")
        plan = build_followup_plan(
            context=case["context"],
            observed_tool_results=case["observed_tool_results"],
            last_tool_plan=case["last_tool_plan"],
        )
        print("context:")
        print(json.dumps(case["context"].model_dump(mode="json"), ensure_ascii=False, indent=2))
        print("observed_tool_results:")
        print(
            json.dumps(
                [item.model_dump(mode="json") for item in case["observed_tool_results"]],
                ensure_ascii=False,
                indent=2,
            )
        )
        print("followup_plan:")
        print(
            json.dumps(
                None if plan is None else plan.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        )
        print()
    return 0


def _build_cases() -> list[dict[str, object]]:
    return [
        {
            "id": "series-summary-first",
            "note": "series_answer 在读取系列列表后，默认批量读取 summary。",
            "context": AgentContext(
                session_id="series|agent-frameworks|series-home",
                scope_type="series",
                series_id="agent-frameworks",
                inspection_stage=InspectionStage.VIDEO_INSPECTION,
            ),
            "observed_tool_results": [
                ToolExecutionResult(
                    tool_name=ToolName.LIST_SERIES_VIDEOS,
                    status="ok",
                    payload={
                        "videos": [
                            {"video_id": "video-1", "title": "Video 1"},
                            {"video_id": "video-2", "title": "Video 2"},
                        ]
                    },
                )
            ],
            "last_tool_plan": AgentActionPlan(
                intent_type=IntentType.SERIES_ANSWER,
                scope_type=ScopeType.SERIES,
                reason="先列出系列视频",
            ),
        },
        {
            "id": "series-already-read",
            "note": "如果已经读取过 series 级内容证据，就不再重复生成 followup plan。",
            "context": AgentContext(
                session_id="series|agent-frameworks|series-home",
                scope_type="series",
                series_id="agent-frameworks",
                inspection_stage=InspectionStage.VIDEO_INSPECTION,
            ),
            "observed_tool_results": [
                ToolExecutionResult(
                    tool_name=ToolName.LIST_SERIES_VIDEOS,
                    status="ok",
                    payload={"videos": [{"video_id": "video-1", "title": "Video 1"}]},
                ),
                ToolExecutionResult(
                    tool_name=ToolName.GET_VIDEO_SUMMARY,
                    status="ok",
                    payload={"video_id": "video-1"},
                ),
            ],
            "last_tool_plan": AgentActionPlan(
                intent_type=IntentType.SERIES_ANSWER,
                scope_type=ScopeType.SERIES,
                reason="先列出系列视频",
            ),
        },
        {
            "id": "video-no-series-policy",
            "note": "非 series_answer 场景不会套用这条 series summary-first 策略。",
            "context": AgentContext(
                session_id="video|agent-frameworks|video-1|overview",
                scope_type="video",
                series_id="agent-frameworks",
                video_id="video-1",
            ),
            "observed_tool_results": [],
            "last_tool_plan": AgentActionPlan(
                intent_type=IntentType.ANSWER_QUESTION,
                scope_type=ScopeType.VIDEO,
                reason="直接回答",
            ),
        },
    ]


if __name__ == "__main__":
    raise SystemExit(main())
