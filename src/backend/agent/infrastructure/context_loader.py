"""`AgentContextLoader` Port 的静态实现。

业务场景：在测试或单会话场景下，Agent 的"工作区上下文"不需要按 `session_id`
动态加载；本适配器以一个固定 `AgentContext` 作为输入，并在调用时按
`session_id` 复制出一份新的上下文返回。
"""

from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentContextLoader


class StaticAgentContextLoader:
    """把单一固定 `AgentContext` 暴露为按 `session_id` 加载的 Loader。

    业务场景：单元测试、单会话 Agent 流程以及"上下文无外部状态"场景下，
    使用方直接 new 一个 Loader 即可获得 `AgentContextLoader` Port 的实现；
    无需再依赖数据库或文件。

    实现要点：
    - 内部只保存一份 `_context`；`load(session_id)` 时若请求的 `session_id`
      与当前一致则原样返回，否则用 `model_copy` 复制一份并改写 `session_id`
      字段，避免污染原对象。
    """

    def __init__(self, context: AgentContext) -> None:
        """注入固定的 `AgentContext` 作为返回源。

        Args:
            context: 被该 Loader 暴露给所有 `load` 调用的工作区上下文。
        """
        self._context = context

    def load(self, session_id: str) -> AgentContext:
        """按 `session_id` 取一份 `AgentContext`。

        Args:
            session_id: 目标会话 ID。

        Returns:
            - 若与内部 `_context.session_id` 一致：返回同一对象。
            - 若不一致：返回一份 `session_id` 字段被改写的新 `AgentContext`。
        """
        if self._context.session_id == session_id:
            return self._context
        return self._context.model_copy(update={"session_id": session_id})
