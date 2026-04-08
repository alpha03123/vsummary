from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.ports import ChatGateway
from backend.agent.runtime.note_drafter import VIDEO_NOTE_DRAFTER_SYSTEM_PROMPT
from backend.agent.runtime.request_router import REQUEST_ROUTER_SYSTEM_PROMPT
from backend.agent.runtime.routed_answerer import ROUTED_ANSWERER_SYSTEM_PROMPT
from backend.agent.runtime.series_locator import SERIES_LOCATOR_SYSTEM_PROMPT
from backend.agent.runtime.video_seek_locator import VIDEO_SEEK_LOCATOR_SYSTEM_PROMPT
from backend.agent.schemas.messages import AgentChatMessage

PLAN_SENTINEL = "<<PLAN>>"


@dataclass(frozen=True)
class GatewayTraceRecord:
    call_kind: str
    mode: str
    duration_ms: int
    saw_plan_sentinel: bool


class TracingChatGateway:
    def __init__(self, delegate: ChatGateway) -> None:
        self._delegate = delegate
        self.records: list[GatewayTraceRecord] = []

    def create_text_completion(self, messages: list[AgentChatMessage]) -> str:
        started_at = perf_counter()
        content = self._delegate.create_text_completion(messages)
        self.records.append(
            GatewayTraceRecord(
                call_kind=_classify_call_kind(messages),
                mode="sync",
                duration_ms=_elapsed_ms(started_at),
                saw_plan_sentinel=PLAN_SENTINEL in content,
            )
        )
        return content

    def create_text_completion_stream(self, messages: list[AgentChatMessage]):
        started_at = perf_counter()
        buffered_chunks: list[str] = []
        for chunk in self._delegate.create_text_completion_stream(messages):
            buffered_chunks.append(chunk)
            yield chunk
        self.records.append(
            GatewayTraceRecord(
                call_kind=_classify_call_kind(messages),
                mode="stream",
                duration_ms=_elapsed_ms(started_at),
                saw_plan_sentinel=PLAN_SENTINEL in "".join(buffered_chunks),
            )
        )

    def create_structured_completion(self, messages, response_model):
        return self._delegate.create_structured_completion(messages, response_model)


def attach_tracing_gateway(service) -> TracingChatGateway:
    tracing_gateway = TracingChatGateway(service._gateway)
    service._gateway = tracing_gateway
    service._runtime._gateway = tracing_gateway
    return tracing_gateway


def format_trace_summary(records: list[GatewayTraceRecord]) -> str:
    planner_calls = sum(1 for item in records if item.call_kind == "planner")
    routed_calls = sum(1 for item in records if item.call_kind in {"router", "series_locator", "video_seek_locator", "note_drafter", "routed_answerer"})
    responder_calls = sum(1 for item in records if item.call_kind == "responder")
    plan_sentinel_seen = any(item.saw_plan_sentinel for item in records)
    return (
        f"model_calls={len(records)}, "
        f"planner_calls={planner_calls}, "
        f"routed_calls={routed_calls}, "
        f"responder_calls={responder_calls}, "
        f"plan_sentinel_seen={plan_sentinel_seen}"
    )


def _classify_call_kind(messages: list[AgentChatMessage]) -> str:
    if not messages:
        return "unknown"
    system_prompt = messages[0].content
    if REQUEST_ROUTER_SYSTEM_PROMPT in system_prompt:
        return "router"
    if ROUTED_ANSWERER_SYSTEM_PROMPT in system_prompt:
        return "routed_answerer"
    if VIDEO_NOTE_DRAFTER_SYSTEM_PROMPT in system_prompt:
        return "note_drafter"
    if SERIES_LOCATOR_SYSTEM_PROMPT in system_prompt:
        return "series_locator"
    if VIDEO_SEEK_LOCATOR_SYSTEM_PROMPT in system_prompt:
        return "video_seek_locator"
    if "Planner Agent" in system_prompt:
        return "planner"
    return "other"


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))
