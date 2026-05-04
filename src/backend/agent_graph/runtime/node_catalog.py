from __future__ import annotations


NODE_ALIASES: dict[str, str] = {
    "route_scope": "选择链路",
    "build_plan": "生成计划",
    "understand_query": "理解问题",
    "retrieve_evidence": "统一检索证据",
    "synthesize_answer": "合成回答",
    "advance_subplan": "推进子计划",
    "execute_series_meta": "读取系列元信息",
    "execute_summary": "读取视频概况",
    "execute_video_graph": "定位视频证据",
    "execute_video_rag": "统一检索证据",
    "execute_video_workflow": "还原视频流程",
    "read_meta_state": "读取当前状态",
    "dispatch_action": "执行动作",
    "answer": "生成回答",
    "finalize": "整理输出",
    "update_session_memory": "更新会话记忆",
}


def get_node_alias(node_id: str) -> str:
    normalized = str(node_id).strip()
    if not normalized:
        return ""
    return NODE_ALIASES.get(normalized, normalized)
