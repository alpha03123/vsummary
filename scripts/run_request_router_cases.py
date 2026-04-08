from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext
from backend.agent.runtime.request_router import (
    REQUEST_ROUTER_SYSTEM_PROMPT,
    classify_initial_route,
)
from backend.agent.schemas.messages import AgentChatMessage


class _RouterGateway:
    def __init__(self, response: str) -> None:
        self._response = response

    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion_stream(self, messages):
        del messages
        yield ""

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        assert REQUEST_ROUTER_SYSTEM_PROMPT in messages[0].content
        return self._response


def main() -> int:
    for case_id, context, message, response in [
        ("series-summary", AgentContext(session_id="series|series-a|series-home", scope_type="series", series_id="series-a"), "这个系列主要讲了哪些主题？", '{"kind":"series_summary","tool_name":null,"reason":"这是系列概括型问题。"}'),
        ("series-locate", AgentContext(session_id="series|series-a|series-home", scope_type="series", series_id="series-a"), "这个系列里哪里讲过 Nacos 3？", '{"kind":"series_locate","tool_name":null,"reason":"这是系列定位问题。"}'),
        ("series-open", AgentContext(session_id="series|series-a|series-home", scope_type="series", series_id="series-a"), "打开系列概览", '{"kind":"open_tool","tool_name":"open_series_overview","reason":"这是明确的打开系列概览请求。"}'),
        ("series-out-of-scope", AgentContext(session_id="series|series-a|series-home", scope_type="series", series_id="series-a"), "帮我写一份旅游攻略", '{"kind":"out_of_scope","tool_name":null,"reason":"这是明显超范围请求。"}'),
        ("video-summary", AgentContext(session_id="video|series-a|video-1|overview", scope_type="video", series_id="series-a", video_id="video-1"), "这个视频主要讲了什么？", '{"kind":"video_summary","tool_name":null,"reason":"这是概括型问题。"}'),
        ("video-transcript", AgentContext(session_id="video|series-a|video-1|overview", scope_type="video", series_id="series-a", video_id="video-1"), "视频原话里是怎么说的？", '{"kind":"video_transcript","tool_name":null,"reason":"这是原话型问题。"}'),
        ("video-save-note", AgentContext(session_id="video|series-a|video-1|overview", scope_type="video", series_id="series-a", video_id="video-1"), "帮我记一下这个视频的重点", '{"kind":"save_note","tool_name":null,"reason":"这是明确的记笔记请求。"}'),
        ("video-open", AgentContext(session_id="video|series-a|video-1|overview", scope_type="video", series_id="series-a", video_id="video-1"), "打开概况", '{"kind":"open_tool","tool_name":"open_overview","reason":"这是明确的打开概况请求。"}'),
    ]:
        decision = classify_initial_route(
            gateway=_RouterGateway(response),
            context=context,
            user_message=message,
        )
        print(f"=== request-router-case: {case_id} ===")
        print(f"message: {message}")
        print(json.dumps(decision.model_dump(mode='json'), ensure_ascii=False, indent=2))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
