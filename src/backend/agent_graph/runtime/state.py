"""LangGraph 工作流的全局状态定义。

本模块定义 `AgentGraphState`——Agent 在多轮对话与多次节点执行中累积的全部上下文。
"""

from __future__ import annotations

from typing import NotRequired, TypedDict


class AgentGraphState(TypedDict):
    """LangGraph 工作流跨节点的全局状态。

    在 `series`（跨视频）与 `video`（单视频）两种 scope 下被节点读写。
    必填字段由入口节点填入；可选字段（`NotRequired`）由后续节点按需追加，
    不保证所有节点都执行过的状态被填齐。

    Attributes:
        session_id: 会话唯一 ID，用于跨调用关联同一段对话。
        scope_type: 当前会话作用域，"series" 或 "video"。
        series_id: `series` scope 下的目标系列 ID。
        video_id: `video` scope 下的目标视频 ID；非 `video` scope 时为 `NotRequired`。
        user_message: 用户最新问题原文。
        memory_messages: 多轮对话历史（已发生的消息），按时间顺序。
        task_outputs: 推理节点产出的结构化中间结果（如 query understanding 后的产物）。
        query_understanding: 查询理解节点对用户问题的解析结果（意图、关键实体等）。
        series_catalog: `series` scope 下的视频目录索引。
        retrieval_request: 检索节点即将发起的检索请求参数。
        retrieval_results: 检索节点返回的原始结果。
        web_search_results: 启用网页搜索时的搜索结果列表。
        web_search_used: 是否实际触发了网页搜索。
        evidence_items: 跨多源汇总后的证据片段（带引用），供答案合成使用。
        answer_payload: 已组装的答案结构（标题、章节、引用等），未发出。
        tool_calls: 视频 scope 下 LLM 规划出的工具调用计划。
        tool_results: 工具调用的实际返回结果列表。
        action_summary: 工具调用链路的自然语言总结。
        video_context_mode: 视频上下文构建模式（"summary"/"transcript"/"rag" 等）。
        video_summary_included: 最终答案是否包含了视频总结内容。
        defer_answer_stream: 是否延迟到所有工具完成后再流式输出答案。
        stream_answer_messages: 流式输出过程中已发送的消息分片。
        assistant_message: 单条助手消息（非流式场景下使用）。
        answer: 最终回复文本。
        error: 节点执行失败时的错误信息；若执行成功则该键不出现。
    """

    session_id: str
    scope_type: str
    series_id: str
    video_id: NotRequired[str]
    user_message: str
    memory_messages: NotRequired[list[dict[str, object]]]
    task_outputs: NotRequired[list[dict[str, object]]]
    query_understanding: NotRequired[dict[str, object]]
    series_catalog: NotRequired[dict[str, object]]
    retrieval_request: NotRequired[dict[str, object]]
    retrieval_results: NotRequired[list[dict[str, object]]]
    web_search_results: NotRequired[list[dict[str, object]]]
    web_search_used: NotRequired[bool]
    evidence_items: NotRequired[list[dict[str, object]]]
    answer_payload: NotRequired[dict[str, object]]
    tool_calls: NotRequired[list[dict[str, object]]]
    tool_results: NotRequired[list[dict[str, object]]]
    action_summary: NotRequired[str]
    video_context_mode: NotRequired[str]
    video_summary_included: NotRequired[bool]
    defer_answer_stream: NotRequired[bool]
    stream_answer_messages: NotRequired[list[dict[str, object]]]
    assistant_message: NotRequired[str]
    answer: NotRequired[str]
    error: NotRequired[str]
