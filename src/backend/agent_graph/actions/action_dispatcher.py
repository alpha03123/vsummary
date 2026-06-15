"""video/series scope 下的动作分发器（plan → 执行）。

本模块是 LangGraph `plan_and_execute_video_actions` 节点下游的执行者：
接收 `VideoActionPlanner` 产出的工具调用（或更通用的 `action_name` +
`action_args` 字典），用 `AgentToolExecutor` 真正落地执行，并返回给前端
一条可读的默认回复 + 工具执行结果。
"""

from __future__ import annotations

from pydantic import TypeAdapter

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentToolExecutor
from backend.agent.schemas.tool_calls import ToolCall


class ActionDispatcher:
    """video/series scope 下的工具调用分发器。

    业务目的：在 video scope 中，LLM 规划完动作后由本类把 `ToolCall` 交给
    `AgentToolExecutor` 执行，并把执行结果包成统一的 `{message, tool_results}`
    字典返回给节点写入 state。

    关键不变量：
        - `action_name` 必须非空（前端/规划器传空会被视为非法）；
        - `video_id` 为空字符串时会归一化为 `None`，避免 `AgentContext` 出现空值。
    """

    def __init__(self, *, tool_executor: AgentToolExecutor) -> None:
        """注入工具执行器端口；并预热 `ToolCall` 的 `TypeAdapter` 用于参数校验。"""
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
        """把一次动作分发到 `AgentToolExecutor` 并返回结构化结果。

        Args:
            scope_type: 作用域（`series` / `video`），用于构造 session_id。
            series_id: 所属系列 ID。
            video_id: 视频 ID（`scope_type == "video"` 时使用；其他可空）。
            action_name: 要执行的工具名（对应 `ToolName`）。
            action_args: 工具参数（会被合并到 `{tool_name, **action_args}` 后校验）。

        Returns:
            包含 `message`（给用户的中文回复）和 `tool_results`（工具执行结果）
            的字典，供 graph 节点写入 state。

        Raises:
            ValueError: `action_name` 为空。
        """
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
    """按 scope 拼接稳定的 graph session_id，供下游 `AgentContext` 使用。

    Args:
        scope_type: `video` 时返回 `video|{series_id}|{video_id}|graph`；
            其他情况返回 `series|{series_id}|graph`。
        series_id: 所属系列 ID。
        video_id: 视频 ID（仅 `scope_type == "video"` 时参与拼接）。

    Returns:
        拼接好的 session_id 字符串。
    """
    if scope_type == "video":
        return f"video|{series_id}|{video_id}|graph"
    return f"series|{series_id}|graph"


def _default_action_response(action_name: str) -> str:
    """根据工具名返回给前端的默认中文回复。

    Args:
        action_name: 工具名（字符串）。

    Returns:
        命中内置映射时返回对应回复，否则返回通用兜底文案"我已经执行了这个操作。"
    """
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
