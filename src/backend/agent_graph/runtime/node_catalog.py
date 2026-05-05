from __future__ import annotations


NODE_ALIASES: dict[str, str] = {
    "route_scope": "选择链路",
    "build_video_context": "读取视频上下文",
    "plan_and_execute_video_actions": "规划并执行视频动作",
    "understand_query": "理解问题",
    "retrieve_evidence": "统一检索证据",
    "synthesize_answer": "合成回答",
    "answer": "生成回答",
    "finalize": "整理输出",
    "update_session_memory": "更新会话记忆",
}


def get_node_alias(node_id: str) -> str:
    normalized = str(node_id).strip()
    if not normalized:
        return ""
    return NODE_ALIASES.get(normalized, normalized)
