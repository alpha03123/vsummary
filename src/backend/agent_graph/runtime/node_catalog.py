"""LangGraph 节点 ID 到中文展示名的注册表。

本模块集中维护 `node_id -> 中文别名` 的映射，供 `AgentGraphStreamOrchestrator`
把节点进度事件翻译为前端可读标签；未在表中注册的 ID 会原样回传，便于
新增节点无须同步更新本表也能跑通。
"""

from __future__ import annotations


NODE_ALIASES: dict[str, str] = {
    "route_scope": "选择链路",
    "build_video_context": "读取视频上下文",
    "plan_and_execute_video_actions": "规划并执行",
    "understand_query": "理解问题",
    "retrieve_evidence": "检索证据",
    "optional_web_search": "联网搜索",
    "build_evidence_items": "整理回答证据",
    "synthesize_answer": "合成回答",
    "answer": "生成回答",
    "finalize": "整理输出",
}


def get_node_alias(node_id: str) -> str:
    """根据节点 ID 返回中文别名；未注册则原样回传。

    Args:
        node_id: 节点 ID 字符串，会先 `strip`。

    Returns:
        注册表中命中的中文别名；未命中或 `node_id` 为空时：
            - 空字符串 → 返回空字符串；
            - 非空未命中 → 返回原 `node_id`。
    """
    normalized = str(node_id).strip()
    if not normalized:
        return ""
    return NODE_ALIASES.get(normalized, normalized)
