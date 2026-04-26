from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy.programs import (
    ActionAfterContentReplyProgram,
    AnswerSynthesisProgram,
    CompareSplitProgram,
    NoteSynthesisProgram,
    SeriesQueryClassifierProgram,
)
from backend.agent_graph.query.planning import build_structured_query_plan


class AgentGraphProgramsTests(unittest.TestCase):
    def test_series_query_classifier_program_returns_structured_fields(self) -> None:
        program = SeriesQueryClassifierProgram(
            predictor=lambda **_: {
                "goal": "locate",
                "target_source": "transcript",
                "context_need": "chunk",
                "reason": "需要定位命中位置。",
            }
        )

        result = program.run(
            user_message="这个系列里哪里讲过 Nacos 3？",
            scope_type="series",
            series_id="agent-frameworks",
        )

        self.assertEqual(result.goal, "locate")
        self.assertEqual(result.target_source, "transcript")
        self.assertEqual(result.context_need, "chunk")

    def test_compare_split_program_returns_atomic_queries(self) -> None:
        program = CompareSplitProgram(
            predictor=lambda **_: {
                "queries": ["百度地图 API Key", "Nacos 3"],
                "reason": "需要分开检索。",
            }
        )

        result = program.run(
            user_message="百度地图 API Key 和 Nacos 3 在课程里分别承担什么作用？",
        )

        self.assertEqual(result.queries, ["百度地图 API Key", "Nacos 3"])

    def test_answer_synthesis_program_returns_answer_text(self) -> None:
        program = AnswerSynthesisProgram(
            predictor=lambda **_: {
                "answer": "Nacos 3 主要出现在 1-5，重点讲安装和课程中的定位。"
            }
        )

        answer = program.run(
            user_message="这个系列里哪里讲过 Nacos 3？",
            retrieval_results=[{"video_id": "1-5", "snippet": "这里讲 Nacos 3。"}],
        )

        self.assertIn("Nacos 3", answer)

    def test_answer_synthesis_program_accepts_meta_state_argument(self) -> None:
        captured = {}

        def predictor(**kwargs):
            captured.update(kwargs)
            return {"answer": "资源状态已整理。"}

        program = AnswerSynthesisProgram(predictor=predictor)

        answer = program.run(
            user_message="这个视频有哪些工具已经生成了？",
            retrieval_results=[],
            meta_state={"overview": {"status": "ready"}},
        )

        self.assertEqual(answer, "资源状态已整理。")
        self.assertEqual(captured["meta_state"]["overview"]["status"], "ready")

    def test_note_synthesis_program_returns_markdown(self) -> None:
        program = NoteSynthesisProgram(
            predictor=lambda **_: {
                "markdown": "## 重点\n- Nacos 3 用于服务发现"
            }
        )

        markdown = program.run(
            user_message="帮我记一下这个视频的重点",
            retrieval_results=[{"video_id": "1-5", "snippet": "Nacos 3 用于服务发现。"}],
        )

        self.assertIn("## 重点", markdown)

    def test_action_after_content_reply_program_returns_reply(self) -> None:
        program = ActionAfterContentReplyProgram(
            predictor=lambda **_: {
                "reply": "已记录当前视频重点，主要涉及 Nacos 3 的作用和端口。"
            }
        )

        reply = program.run(
            user_message="帮我记一下这个视频的重点",
            action_name="save_note",
            generated_content="## 重点\n- Nacos 3",
        )

        self.assertIn("已记录", reply)

    def test_series_query_classifier_program_accepts_structured_planning_fields(self) -> None:
        program = SeriesQueryClassifierProgram(
            predictor=lambda **_: {
                "goal": "locate",
                "target_source": "transcript",
                "context_need": "chunk",
                "reason": "需要对目标视频下钻。",
                "candidate_video_ids": ["1-5"],
                "selected_videos": [
                    {"video_id": "1-5", "reason_for_selection": "安装 Nacos 3 的目标视频。"}
                ],
                "selection_mode": "fresh",
                "subplans": [
                    {
                        "target_video_ids": ["1-5"],
                        "depth": "video_graph",
                        "query": "定位讲 Docker 安装 Nacos 3 的时间点",
                    }
                ],
            }
        )

        result = program.run(
            user_message="这个系列里哪里讲过 Nacos 3？",
            scope_type="series",
            series_id="agent-frameworks",
        )

        self.assertEqual(result.candidate_video_ids, ["1-5"])
        self.assertEqual(result.selected_videos[0].video_id, "1-5")
        self.assertEqual(result.subplans[0].depth.value, "video_graph")

    def test_series_query_classifier_program_injects_scope_filtered_available_actions(self) -> None:
        captured = {}

        def predictor(**kwargs):
            captured.update(kwargs)
            return {
                "goal": "action",
                "target_source": "all",
                "context_need": "chunk",
                "reason": "动作请求。",
                "action_name": "open_notes",
                "action_args": {},
            }

        program = SeriesQueryClassifierProgram(predictor=predictor)

        result = program.run(
            user_message="帮我整理整理",
            scope_type="series",
            series_id="agent-frameworks",
        )

        self.assertEqual(result.action_name, "open_notes")
        self.assertIn("open_series_home", captured["available_actions"])
        self.assertIn("open_series_overview", captured["available_actions"])
        self.assertNotIn("open_notes", captured["available_actions"])
        self.assertNotIn("generate_overview", captured["available_actions"])
        self.assertNotIn("generate_mindmap", captured["available_actions"])

    def test_video_query_classifier_program_injects_video_only_actions(self) -> None:
        captured = {}

        def predictor(**kwargs):
            captured.update(kwargs)
            return {
                "goal": "action",
                "target_source": "all",
                "context_need": "chunk",
                "reason": "动作请求。",
                "action_name": "generate_overview",
                "action_args": {},
            }

        program = SeriesQueryClassifierProgram(predictor=predictor)

        result = program.run(
            user_message="帮我整理整理",
            scope_type="video",
            series_id="agent-frameworks",
            video_id="1-4 准备工作：百度地图API秘钥(AK)",
        )

        self.assertEqual(result.action_name, "generate_overview")
        self.assertIn("generate_overview", captured["available_actions"])

    def test_build_structured_query_plan_supports_carry_forward_previous_selection(self) -> None:
        plan = build_structured_query_plan(
            state={
                "session_id": "series|agent-frameworks|series-home",
                "scope_type": "series",
                "series_id": "agent-frameworks",
                "user_message": "继续比较它们的定位差异",
                "history_selected_videos": [
                    {"video_id": "1-6", "reason_for_selection": "上一轮框架课"},
                    {"video_id": "1-7", "reason_for_selection": "上一轮框架课"},
                ],
            },
            current_instruction="继续比较它们的定位差异",
            decision_payload={
                "goal": "understand",
                "target_source": "summary",
                "context_need": "chunk",
                "reason": "承接上一轮视频集",
                "selection_mode": "carry_forward",
            },
        )

        self.assertEqual(plan["selection_mode"], "carry_forward")
        self.assertEqual(plan["candidate_video_ids"], ["1-6", "1-7"])
        self.assertEqual(plan["selected_videos"][0]["video_id"], "1-6")
        self.assertEqual(plan["subplans"][0]["target_video_ids"], ["1-6", "1-7"])

    def test_build_structured_query_plan_video_scope_uses_summary_only_when_requested(self) -> None:
        plan = build_structured_query_plan(
            state={
                "session_id": "video|agent-frameworks|1-5|overview",
                "scope_type": "video",
                "series_id": "agent-frameworks",
                "video_id": "1-5",
                "user_message": "这个视频主要讲了什么",
            },
            current_instruction="这个视频主要讲了什么",
            decision_payload={
                "goal": "understand",
                "target_source": "summary",
                "context_need": "chunk",
            },
        )

        self.assertEqual([item["depth"] for item in plan["subplans"]], ["summary"])

    def test_build_structured_query_plan_video_scope_uses_rag_only_for_transcript(self) -> None:
        plan = build_structured_query_plan(
            state={
                "session_id": "video|agent-frameworks|1-5|overview",
                "scope_type": "video",
                "series_id": "agent-frameworks",
                "video_id": "1-5",
                "user_message": "原话在哪",
            },
            current_instruction="原话在哪",
            decision_payload={
                "goal": "locate",
                "target_source": "transcript",
                "context_need": "chunk",
            },
        )

        self.assertEqual([item["depth"] for item in plan["subplans"]], ["video_rag"])


if __name__ == "__main__":
    unittest.main()
