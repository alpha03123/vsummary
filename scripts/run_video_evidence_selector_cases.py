from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext
from backend.agent.runtime.video_evidence_selector import (
    VIDEO_EVIDENCE_SELECTOR_SYSTEM_PROMPT,
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


def main() -> int:
    context = AgentContext(
        session_id="video|series-a|video-1|overview",
        scope_type="video",
        series_id="series-a",
        video_id="video-1",
    )
    for case_id, message, response in [
        ("video-summary", "这个视频主要讲了什么？", '{"mode":"summary","reason":"这是概括型问题。"}'),
        ("video-transcript", "视频原话里是怎么说的？", '{"mode":"transcript","reason":"需要原话级证据。"}'),
        ("video-fallback", "打开概况", '{"mode":"fallback","reason":"这是动作型请求。"}'),
    ]:
        decision = classify_video_evidence_need(
            gateway=_SelectorGateway(response),
            context=context,
            user_message=message,
        )
        print(f"=== video-evidence-case: {case_id} ===")
        print(f"message: {message}")
        print(json.dumps(decision.model_dump(mode='json'), ensure_ascii=False, indent=2))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
