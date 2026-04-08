from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext
from backend.agent.runtime.video_evidence_selector import (
    VIDEO_EVIDENCE_SELECTOR_SYSTEM_PROMPT,
    VideoEvidenceMode,
    classify_video_evidence_need,
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
        assert VIDEO_EVIDENCE_SELECTOR_SYSTEM_PROMPT in messages[0].content
        return self._response


class VideoEvidenceSelectorTests(unittest.TestCase):
    def test_summary_question_prefers_summary(self) -> None:
        decision = classify_video_evidence_need(
            gateway=_SelectorGateway('{"mode":"summary","reason":"这是概括型问题。"}'),
            context=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            user_message="这个视频主要讲了什么？",
        )

        self.assertEqual(decision.mode, VideoEvidenceMode.SUMMARY)

    def test_quote_question_prefers_transcript(self) -> None:
        decision = classify_video_evidence_need(
            gateway=_SelectorGateway('{"mode":"transcript","reason":"需要原话级证据。"}'),
            context=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            user_message="视频原话里是怎么说的？",
        )

        self.assertEqual(decision.mode, VideoEvidenceMode.TRANSCRIPT)

    def test_action_request_falls_back(self) -> None:
        decision = classify_video_evidence_need(
            gateway=_SelectorGateway('{"mode":"fallback","reason":"这是动作型请求。"}'),
            context=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            user_message="打开概况",
        )

        self.assertEqual(decision.mode, VideoEvidenceMode.FALLBACK)


if __name__ == "__main__":
    unittest.main()
