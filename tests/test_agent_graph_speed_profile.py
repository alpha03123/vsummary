from __future__ import annotations

import importlib.util
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext
from backend.agent_graph.runtime.service import AgentGraphService


def _load_script_module():
    module_path = ROOT / "scripts" / "run_speed_profile.py"
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


class _FakeDecomposer:
    def run(self, **kwargs):
        del kwargs
        return {"tasks": [{"task_id": "task-1", "instruction": "任务", "depends_on": [], "kind_hint": ""}], "reason": ""}


class _FakeClassifier:
    def run(self, **kwargs):
        del kwargs
        return {"goal": "understand", "target_source": "summary", "context_need": "chunk", "reason": ""}


class _FakeRetriever:
    def search(self, **kwargs):
        del kwargs
        return {"hits": [{"video_id": "video-1", "source_type": "summary", "snippet": "摘要"}]}


class _FakeAnswer:
    def run(self, **kwargs):
        del kwargs
        return "graph answer"


class _FakeMemoryUpdater:
    def run(self, **kwargs):
        del kwargs
        return "memory summary"


class _FakeGraph:
    def __init__(self, *, decomposer, classifier, retriever, answer, memory_updater) -> None:
        self._decomposer = decomposer
        self._classifier = classifier
        self._retriever = retriever
        self._answer = answer
        self._memory_updater = memory_updater

    def invoke(self, payload):
        self._decomposer.run(
            user_message=payload["user_message"],
            scope_type=payload["scope_type"],
            series_id=payload["series_id"],
            video_id=payload.get("video_id", ""),
        )
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
        history_summary_update = self._memory_updater.run(
            history_summary=payload.get("history_summary", ""),
            user_message=payload["user_message"],
            assistant_message=answer,
            task_outputs=[],
        )
        return {
            **payload,
            "query_plan": query_plan,
            "retrieval_results": retrieval["hits"],
            "answer": answer,
            "history_summary_update": history_summary_update,
        }


class AgentGraphSpeedProfileTests(unittest.TestCase):
    def test_attach_service_profiling_collects_graph_stage_spans(self) -> None:
        module = _load_script_module()
        decomposer = _FakeDecomposer()
        classifier = _FakeClassifier()
        retriever = _FakeRetriever()
        answer = _FakeAnswer()
        memory_updater = _FakeMemoryUpdater()
        service = AgentGraphService(
            context_loader=StaticAgentContextLoader(
                AgentContext(
                    session_id="series|series-a|series-home",
                    scope_type="series",
                    series_id="series-a",
                )
            ),
            graph=_FakeGraph(
                decomposer=decomposer,
                classifier=classifier,
                retriever=retriever,
                answer=answer,
                memory_updater=memory_updater,
            ),
            session_store=_FakeSessionStore(),
            decomposer_program=decomposer,
            classifier_program=classifier,
            retrieval_service=retriever,
            answer_program=answer,
            memory_update_program=memory_updater,
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
        self.assertIn("decomposer.run", span_names)
        self.assertIn("classifier.run", span_names)
        self.assertIn("retrieval.search", span_names)
        self.assertIn("answer_program.run", span_names)
        self.assertIn("memory_update.run", span_names)
        self.assertIn("session_store.append_turn", span_names)


if __name__ == "__main__":
    unittest.main()
