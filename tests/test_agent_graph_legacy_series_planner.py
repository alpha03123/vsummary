from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.series_planner import LegacyStyleSeriesPlanner, SeriesPlannerOutput
from backend.video_summary.library.views import SeriesView, VideoCardView, VideoSummaryView


class _FakeWorkspace:
    def list_series(self):
        return [
            SeriesView(
                id="agent-frameworks",
                title="Agent Frameworks",
                videos=[
                    VideoCardView(id="1-4", title="准备工作：百度地图API秘钥(AK)", source_name="1-4.mp4", processed=True, status="ready"),
                    VideoCardView(id="1-5", title="准备工作：安装Nacos 3", source_name="1-5.mp4", processed=True, status="ready"),
                    VideoCardView(id="1-6", title="仿Manus能自主决策的框架：Jmanus", source_name="1-6.mp4", processed=True, status="ready"),
                    VideoCardView(id="1-7", title="具备ReAct核心能力的框架：AgentScope", source_name="1-7.mp4", processed=True, status="ready"),
                ],
            )
        ]

    def get_video_summary(self, series_id: str, video_id: str):
        del series_id
        payload = {
            "1-4": {"one_sentence_summary": "讲 AK 的申请流程。", "core_problem": "准备地图 API Key。"},
            "1-5": {"one_sentence_summary": "讲如何通过 Docker 安装 Nacos 3。", "core_problem": "准备服务发现组件。"},
            "1-6": {"one_sentence_summary": "讲 JManus 的定位与示例执行流程。", "core_problem": "理解 Java 多智能体协作框架。"},
            "1-7": {"one_sentence_summary": "讲 AgentScope 的定位和 ReAct 思维链。", "core_problem": "理解多智能体自主代理框架。"},
        }.get(video_id)
        if payload is None:
            return None
        return VideoSummaryView(series_id="agent-frameworks", video_id=video_id, title=video_id, summary=payload)


class _CapturingGateway:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.messages = None

    def create_structured_completion(self, messages, response_model):
        self.messages = messages
        return response_model.model_validate(self.output)


class LegacySeriesPlannerTests(unittest.TestCase):
    def test_prompt_explicitly_forbids_exclude_reasoning(self) -> None:
        gateway = _CapturingGateway(
            {
                "selected_videos": [{"video_id": "1-4"}, {"video_id": "1-5"}],
                "selection_mode": "fresh",
                "subplans": [],
                "reason": "ok",
            }
        )
        planner = LegacyStyleSeriesPlanner(workspace=_FakeWorkspace(), gateway=gateway)

        planner.create_plan(
            user_message="把准备工作的视频找出来，并按顺序说每节在准备什么。",
            series_id="agent-frameworks",
        )

        self.assertIsNotNone(gateway.messages)
        system_prompt = gateway.messages[0].content
        self.assertIn("只输出 selected_videos，不要为未选中的视频写 exclude reason", system_prompt)

    def test_carry_forward_without_new_selected_videos_reuses_previous_selection(self) -> None:
        gateway = _CapturingGateway(
            {
                "selected_videos": [],
                "selection_mode": "carry_forward",
                "subplans": [],
                "reason": "reuse previous selection",
            }
        )
        planner = LegacyStyleSeriesPlanner(workspace=_FakeWorkspace(), gateway=gateway)

        result = planner.create_plan(
            user_message="继续比较它们的定位差异。",
            series_id="agent-frameworks",
            previous_selected_videos=[
                {"video_id": "1-6", "reason_for_selection": "框架课"},
                {"video_id": "1-7", "reason_for_selection": "框架课"},
            ],
        )

        self.assertEqual(result["selection_mode"], "carry_forward")
        self.assertEqual(result["candidate_video_ids"], ["1-6", "1-7"])
        self.assertEqual(result["selected_videos"][0]["video_id"], "1-6")

    def test_prompt_forbids_putting_contrast_video_into_selected_videos(self) -> None:
        gateway = _CapturingGateway(
            {
                "selected_videos": [
                    {"video_id": "1-4", "reason_for_selection": "AK 准备"},
                    {"video_id": "1-5", "reason_for_selection": "Nacos 安装"},
                    {"video_id": "1-6", "reason_for_selection": "JManus 初始化"},
                    {"video_id": "1-7", "reason_for_selection": "作为对照判断是否应排除"},
                ],
                "selection_mode": "fresh",
                "subplans": [],
                "reason": "legacy planner with contrast contamination",
            }
        )
        planner = LegacyStyleSeriesPlanner(workspace=_FakeWorkspace(), gateway=gateway)

        result = planner.create_plan(
            user_message="把 agent-frameworks 这个系列里，真正属于“安装 / 初始化 / 环境准备”的视频找出来，并按先后顺序告诉我每节到底在准备什么。不要把纯概念介绍的视频算进去。",
            series_id="agent-frameworks",
        )

        self.assertEqual(result["candidate_video_ids"], ["1-4", "1-5", "1-6", "1-7"])
        self.assertIsNotNone(gateway.messages)
        system_prompt = gateway.messages[0].content
        self.assertIn("selected_videos 只能包含最终要纳入回答主体的视频", system_prompt)
        self.assertIn("如果某个视频只是用来说明“为什么不算”或作为对照示例，它不能出现在 selected_videos 中", system_prompt)
        self.assertIn("你必须按视频整体主题来判断，而不是按视频里顺带出现的一小段内容来判断", system_prompt)
        self.assertIn("如果一节视频主体是在做框架介绍、能力说明、产品亮点或概念讲解，即使中间顺带出现启动、初始化、配置之类步骤，也不要把它放进 selected_videos", system_prompt)

    def test_prepare_work_filter_question_relies_on_prompt_contract_not_post_filter(self) -> None:
        gateway = _CapturingGateway(
            {
                "selected_videos": [
                    {"video_id": "1-4", "reason_for_selection": "AK 准备"},
                    {"video_id": "1-5", "reason_for_selection": "Nacos 安装"},
                    {"video_id": "1-6", "reason_for_selection": "JManus 初始化"},
                    {"video_id": "1-7", "reason_for_selection": "作为对照判断是否应排除"},
                ],
                "selection_mode": "fresh",
                "subplans": [
                    {
                        "target_video_ids": [],
                        "depth": "summary",
                        "query": "按顺序说明这些视频准备了什么",
                    }
                ],
                "reason": "bad output",
            }
        )
        planner = LegacyStyleSeriesPlanner(workspace=_FakeWorkspace(), gateway=gateway)

        result = planner.create_plan(
            user_message="把 agent-frameworks 这个系列里，真正属于“安装 / 初始化 / 环境准备”的视频找出来，并按先后顺序告诉我每节到底在准备什么。不要把纯概念介绍的视频算进去。",
            series_id="agent-frameworks",
        )

        self.assertEqual(result["candidate_video_ids"], ["1-4", "1-5", "1-6", "1-7"])
        self.assertEqual(
            [item["video_id"] for item in result["selected_videos"]],
            ["1-4", "1-5", "1-6", "1-7"],
        )
        self.assertEqual(result["subplans"][0]["target_video_ids"], ["1-4", "1-5", "1-6", "1-7"])
        self.assertIsNotNone(gateway.messages)
        system_prompt = gateway.messages[0].content
        self.assertIn("只输出 selected_videos，不要为未选中的视频写 exclude reason", system_prompt)
        self.assertIn("如果一节视频主体是在做框架介绍、能力说明、产品亮点或概念讲解，即使中间顺带出现启动、初始化、配置之类步骤，也不要把它放进 selected_videos", system_prompt)


if __name__ == "__main__":
    unittest.main()
