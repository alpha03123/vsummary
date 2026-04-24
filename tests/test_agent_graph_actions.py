from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.runtime.graph import build_agent_graph
from backend.agent_graph.query.models import CompareSplitDecision, StructuredQueryPlan


class _Classifier:
    def __init__(self, decision: StructuredQueryPlan) -> None:
        self._decision = decision

    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = "", history_summary: str = "", history_selected_videos=None):
        del user_message, scope_type, series_id, video_id, history_summary, history_selected_videos
        return self._decision


class _Splitter:
    def run(self, *, user_message: str):
        del user_message
        return CompareSplitDecision(queries=[])


class _Retrieval:
    def search(self, **kwargs):
        return {
            "hits": [
                {
                    "video_id": kwargs.get("video_id", "video-1"),
                    "title": "Video 1",
                    "source_type": "summary",
                    "source_family": "summary",
                    "snippet": "这是摘要内容",
                }
            ]
        }


class _MetaStateReader:
    def read(self, **kwargs):
        del kwargs
        return {}


class _ActionDispatcher:
    def dispatch(self, *, scope_type: str, series_id: str, video_id: str, action_name: str, action_args: dict[str, object]):
        mapping = {
            "open_overview": ("我已经帮你打开概况工具。", {"selected_tool": "overview"}),
            "save_note": ("我已经帮你记好这条笔记。", {"selected_tool": "notes"}),
            "video_seek": ("我已经帮你定位到相关时间点。", {"selected_tool": "video"}),
        }
        message, payload = mapping[action_name]
        return {
            "direct_response": message,
            "tool_results": [
                {
                    "tool_name": action_name,
                    "status": "ok",
                    "payload": {**payload, **action_args},
                }
            ],
        }


class _Answer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        del user_message, retrieval_results, meta_state
        return "unused"


class _MemoryUpdater:
    def run(self, *, history_summary: str, user_message: str, assistant_message: str, task_outputs: list[dict[str, object]]):
        del history_summary, user_message, assistant_message, task_outputs
        return ""


class AgentGraphActionsTests(unittest.TestCase):
    def test_action_flow_dispatches_ui_action_without_answer_node(self) -> None:
        graph = build_agent_graph(
            classifier_program=_Classifier(
                StructuredQueryPlan(
                    goal="action",
                    target_source="all",
                    context_need="chunk",
                    reason="明确动作请求。",
                    action_name="open_overview",
                    action_args={},
                )
            ),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            action_dispatcher=_ActionDispatcher(),
            answer_program=_Answer(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "打开概况",
            }
        )

        self.assertEqual(result["direct_response"], "我已经帮你打开概况工具。")
        self.assertEqual(result["tool_results"][0]["tool_name"], "open_overview")

    def test_action_flow_dispatches_save_note(self) -> None:
        graph = build_agent_graph(
            classifier_program=_Classifier(
                StructuredQueryPlan(
                    goal="action",
                    target_source="all",
                    context_need="chunk",
                    reason="明确记笔记请求。",
                    action_name="save_note",
                    action_args={"note_title": "重点", "note_content": "内容"},
                )
            ),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            action_dispatcher=_ActionDispatcher(),
            answer_program=_Answer(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "帮我记一下重点",
            }
        )

        self.assertEqual(result["tool_results"][0]["tool_name"], "save_note")
        self.assertEqual(result["tool_results"][0]["payload"]["note_title"], "重点")

    def test_action_flow_uses_answer_node_output_when_save_note_lacks_note_fields(self) -> None:
        graph = build_agent_graph(
            classifier_program=_Classifier(
                StructuredQueryPlan(
                    goal="action",
                    target_source="all",
                    context_need="chunk",
                    reason="明确记笔记请求。",
                    action_name="save_note",
                    action_args={"content_type": "key_points"},
                )
            ),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            action_dispatcher=_ActionDispatcher(),
            answer_program=_Answer(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "帮我把重点记下来",
                "answer": "这是已经生成的回答",
            }
        )

        self.assertEqual(result["tool_results"][0]["tool_name"], "save_note")
        self.assertEqual(result["tool_results"][0]["payload"]["note_title"], "总结")
        self.assertEqual(result["tool_results"][0]["payload"]["note_content"], "unused")

    def test_action_flow_generates_content_before_save_note_when_note_fields_missing(self) -> None:
        class _Answer:
            def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
                del user_message, meta_state
                return f"总结：{retrieval_results[0]['snippet']}"

        graph = build_agent_graph(
            classifier_program=_Classifier(
                StructuredQueryPlan(
                    goal="action",
                    target_source="all",
                    context_need="chunk",
                    reason="明确记笔记请求。",
                    action_name="save_note",
                    action_args={"note_type": "key_points"},
                )
            ),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            action_dispatcher=_ActionDispatcher(),
            answer_program=_Answer(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "帮我把重点记下来",
            }
        )

        self.assertEqual(result["tool_results"][0]["tool_name"], "save_note")
        self.assertEqual(result["tool_results"][0]["payload"]["note_title"], "总结")
        self.assertEqual(result["tool_results"][0]["payload"]["note_content"], "总结：这是摘要内容")

    def test_action_flow_dispatches_video_seek(self) -> None:
        graph = build_agent_graph(
            classifier_program=_Classifier(
                StructuredQueryPlan(
                    goal="action",
                    target_source="all",
                    context_need="chunk",
                    reason="明确跳转视频请求。",
                    action_name="video_seek",
                    action_args={"seek_seconds": 32.0},
                )
            ),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            action_dispatcher=_ActionDispatcher(),
            answer_program=_Answer(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "跳到相关位置",
            }
        )

        self.assertEqual(result["tool_results"][0]["tool_name"], "video_seek")
        self.assertEqual(result["tool_results"][0]["payload"]["seek_seconds"], 32.0)


if __name__ == "__main__":
    unittest.main()
