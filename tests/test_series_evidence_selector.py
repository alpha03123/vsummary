from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext
from backend.agent.runtime.series_evidence_selector import (
    SERIES_EVIDENCE_SELECTOR_SYSTEM_PROMPT,
    SeriesEvidenceMode,
    classify_series_evidence_need,
)
from backend.agent.schemas.messages import AgentChatMessage


class _SelectorGateway:
    def __init__(self, response: str) -> None:
        self._response = response

    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion_stream(self, messages):
        del messages
        yield ""

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        assert SERIES_EVIDENCE_SELECTOR_SYSTEM_PROMPT in messages[0].content
        return self._response


class SeriesEvidenceSelectorTests(unittest.TestCase):
    def test_series_summary_question_prefers_summary_workflow(self) -> None:
        decision = classify_series_evidence_need(
            gateway=_SelectorGateway('{"mode":"summary","reason":"这是系列概括型问题。"}'),
            context=AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
            ),
            user_message="这个系列主要讲了哪些主题？",
        )

        self.assertEqual(decision.mode, SeriesEvidenceMode.SUMMARY)

    def test_series_action_request_falls_back(self) -> None:
        decision = classify_series_evidence_need(
            gateway=_SelectorGateway('{"mode":"fallback","reason":"这是动作型请求。"}'),
            context=AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
            ),
            user_message="打开系列概览",
        )

        self.assertEqual(decision.mode, SeriesEvidenceMode.FALLBACK)


if __name__ == "__main__":
    unittest.main()
