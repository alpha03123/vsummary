from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext
from backend.agent_graph.service import SeriesAgentGraphService
from backend.api.bootstrap import LazyAgentRuntimeProvider, build_api_container
from backend.agent.schemas.stream_events import AgentStreamEvent


class _FakeGraph:
    def invoke(self, payload):
        return {
            **payload,
            "answer": "graph answer",
        }


class AgentGraphServiceTests(unittest.TestCase):
    def test_series_agent_graph_service_runs_graph_with_loaded_context(self) -> None:
        service = SeriesAgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                )
            ),
            graph=_FakeGraph(),
        )

        result = service.run(
            session_id="series|series-a|series-home",
            user_message="这个系列主要讲了什么？",
        )

        self.assertEqual(result.assistant_message, "graph answer")

    def test_bootstrap_can_build_series_agent_graph_service(self) -> None:
        with patch("backend.api.bootstrap.SeriesRetrievalService", return_value=object()):
            container = build_api_container(ROOT)

            generic_service = container.get_agent_graph_service()
            service = container.get_series_agent_graph_service()

        self.assertIsNotNone(generic_service)
        self.assertIsNotNone(service)

    def test_lazy_provider_loads_compiled_split_compare_program(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config" / "settings.toml").write_text("", encoding="utf-8")
            (root / ".env").write_text("OPENAI_API_KEY=test-key\nOPENAI_MODEL=gpt-5.4\n", encoding="utf-8")

            provider = LazyAgentRuntimeProvider(
                root_dir=root,
                workspace=SimpleNamespace(),
            )
            fake_settings = SimpleNamespace(
                agent_context=SimpleNamespace(
                    window_tokens=1000,
                    reserved_output_tokens=100,
                    warning_threshold_ratio=0.7,
                    compact_threshold_ratio=0.8,
                    blocking_threshold_ratio=0.9,
                )
            )
            with (
                patch("backend.api.bootstrap.load_env_settings", return_value=SimpleNamespace(api_key="test-key", model="gpt-5.4", base_url="http://127.0.0.1:8317/v1")),
                patch("backend.api.bootstrap.normalize_openai_base_url", return_value="http://127.0.0.1:8317/v1"),
                patch("backend.api.bootstrap.dspy.configure"),
                patch("backend.api.bootstrap.ProxyStreamingLM"),
                patch("backend.api.bootstrap.load_settings", return_value=fake_settings),
                patch("backend.api.bootstrap.create_list_series_videos_handler", return_value=object()),
                patch("backend.api.bootstrap.create_get_video_summary_handler", return_value=object()),
                patch("backend.api.bootstrap.create_get_video_tools_handler", return_value=object()),
                patch("backend.api.bootstrap.create_get_video_transcript_handler", return_value=object()),
                patch("backend.api.bootstrap._build_tool_executor", return_value=object()),
                patch("backend.api.bootstrap.SeriesRetrievalService", return_value=object()),
                patch("backend.api.bootstrap.MetaStateReader", return_value=object()),
                patch("backend.api.bootstrap.ActionDispatcher", return_value=object()),
                patch("backend.api.bootstrap.load_or_create_decompose_program", return_value="decompose-program"),
                patch("backend.api.bootstrap.load_or_create_classifier_program", return_value="classifier-program"),
                patch("backend.api.bootstrap.load_or_create_split_compare_program", return_value="split-program") as split_loader,
                patch("backend.api.bootstrap.build_agent_graph", return_value=_FakeGraph()) as build_graph,
            ):
                provider.get_agent_graph_service()

            split_loader.assert_called_once_with(
                artifact_path=root / "data" / "agent_graph" / "dspy" / "split_compare" / "program.json",
            )
            self.assertEqual(build_graph.call_args.kwargs["compare_split_program"], "split-program")

    def test_graph_service_streams_basic_events(self) -> None:
        service = SeriesAgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                )
            ),
            graph=_FakeGraph(),
        )

        events = list(
            service.stream_with_context(
                session_id="series|series-a|series-home",
                user_message="这个系列主要讲了什么？",
                context_override=None,
            )
        )

        self.assertTrue(all(isinstance(event, AgentStreamEvent) for event in events))
        self.assertIn("answer_completed", [event.type for event in events])


if __name__ == "__main__":
    unittest.main()
