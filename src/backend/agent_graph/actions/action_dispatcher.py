from __future__ import annotations

from pydantic import TypeAdapter

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentToolExecutor
from backend.agent.schemas.tool_calls import ToolCall


class ActionDispatcher:
    def __init__(self, *, tool_executor: AgentToolExecutor) -> None:
        self._tool_executor = tool_executor
        self._tool_call_adapter = TypeAdapter(ToolCall)

    def dispatch(
        self,
        *,
        scope_type: str,
        series_id: str,
        video_id: str,
        action_name: str,
        action_args: dict[str, object],
    ) -> dict[str, object]:
        if not action_name.strip():
            raise ValueError("action_name 不能为空。")
        call = self._tool_call_adapter.validate_python(
            {
                "tool_name": action_name,
                **action_args,
            }
        )
        context = AgentContext(
            session_id=_build_session_id(scope_type=scope_type, series_id=series_id, video_id=video_id),
            scope_type=scope_type,
            series_id=series_id,
            video_id=video_id or None,
        )
        result = self._tool_executor.execute_call(call, context)
        return {
            "message": _default_action_response(action_name),
            "tool_results": [
                {
                    "tool_name": result.tool_name.value,
                    "status": result.status,
                    "payload": result.payload,
                }
            ],
        }


def _build_session_id(*, scope_type: str, series_id: str, video_id: str) -> str:
    if scope_type == "video":
        return f"video|{series_id}|{video_id}|graph"
    return f"series|{series_id}|graph"


def _default_action_response(action_name: str) -> str:
    mapping = {
        "open_overview": "我已经帮你打开概况工具。",
        "open_mindmap": "我已经帮你打开思维导图工具。",
        "open_notes": "我已经帮你打开笔记工具。",
        "open_video": "我已经帮你打开视频工具。",
        "save_note": "我已经帮你记好这条笔记。",
        "generate_overview": "我已经开始帮你生成概况。",
        "generate_mindmap": "我已经开始帮你生成思维导图。",
    }
    return mapping.get(action_name, "我已经执行了这个操作。")
