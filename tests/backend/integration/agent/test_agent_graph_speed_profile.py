from __future__ import annotations

import importlib.util
import sys
import unittest
from contextlib import ExitStack

from tests import _path_setup

ROOT = _path_setup.REPO_ROOT

from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext
from backend.agent_graph.runtime.service import AgentGraphService


def _load_script_module():
    module_path = ROOT / "scripts" / "analysis" / "run_speed_profile.py"
    spec = importlib.util.spec_from_file_location("run_speed_profile", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeSessionStore:
    def get_snapshot(self, session_id: str):
        del session_id
        return None

    def append_turn(self, **kwargs):
        del kwargs
        return None


class _FakeClassifier:
    def run(self, **kwargs):
        del kwargs
        return {"goal": "understand", "target_source": "summary", "context_need": "chunk", "reason": ""}


class _FakeRetriever:
    def search(self, **kwargs):
        del kwargs
        return {"hits": [{"video_id": "video-1", "source_type": "summary_global", "snippet": "摘要"}]}


class _FakeAnswer:
    def run(self, **kwargs):
        del kwargs
        return "graph answer"


class _FakeGraph:
    def __init__(self, *, classifier, retriever, answer) -> None:
        self._classifier = classifier
        self._retriever = retriever
        self._answer = answer

    def invoke(self, payload):
        query_plan = self._classifier.run(
            user_message=payload["user_message"],
            scope_type=payload["scope_type"],
            series_id=payload["series_id"],
            video_id=payload.get("video_id", ""),
        )
        retrieval = self._retriever.search(
            scope_type=payload["scope_type"],
            series_id=payload["series_id"],
            video_id=payload.get("video_id", ""),
            query=payload["user_message"],
            target_source=query_plan["target_source"],
            expand_context=True,
            context_window_seconds=120,
            max_hits=5,
        )
        answer = self._answer.run(
            user_message=payload["user_message"],
            retrieval_results=retrieval["hits"],
            meta_state={},
        )
        return {
            **payload,
            "query_plan": query_plan,
            "retrieval_results": retrieval["hits"],
            "answer": answer,
        }


class AgentGraphSpeedProfileTests(unittest.TestCase):
    def test_attach_service_profiling_collects_graph_stage_spans(self) -> None:
        module = _load_script_module()
        classifier = _FakeClassifier()
        retriever = _FakeRetriever()
        answer = _FakeAnswer()
        service = AgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                )
            ),
            graph=_FakeGraph(
                classifier=classifier,
                retriever=retriever,
                answer=answer,
            ),
            session_store=_FakeSessionStore(),
        )

        profiler = module.Profiler()
        with ExitStack() as stack:
            module._attach_service_profiling(stack, service, profiler)
            service.run_turn(
                session_id="series|series-a|series-home",
                user_message="这个系列主要讲了什么？",
            )

        span_names = [record.name for record in profiler.records]
        self.assertIn("graph_service.run_turn", span_names)
        self.assertIn("context_loader.load", span_names)
        self.assertIn("session_store.get_snapshot", span_names)
        self.assertIn("graph.invoke", span_names)
        self.assertIn("session_store.append_turn", span_names)


if __name__ == "__main__":
    unittest.main()

