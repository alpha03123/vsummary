"""video scope 动作规划阶段的 system prompt 模板集合。

本模块集中维护"video talk 流程中调用 video 工具"所需的 system prompt，
用于驱动 LangGraph 的 `plan_and_execute_video_actions` 节点：让 LLM
在只读回答 vs. 状态变更动作之间二选一并返回对应的 tool_calls。
"""

from __future__ import annotations


# video scope 动作规划器的 system prompt。
#
# 目的：让 LLM 担任"动作判别器"，仅在用户意图**确实**需要改变当前视频
# 工作区状态时才返回 tool_calls，纯问答场景应返回空 tool_calls。具体工具的
# 名称、用途和参数说明由工具注册表动态注入，避免这里与工具定义出现两份规则。
VIDEO_ACTION_PLANNER_SYSTEM_PROMPT = (
    "你是 video scope 动作规划器，只判断是否需要执行当前视频动作。\n"
    "先根据用户语义填写 requested_artifact：用户要求生成、整理、记录或保存一份可回看的笔记时填 note；其他情况填 none。\n"
    "只在用户意图需要改变当前视频工作区状态时返回 tool_calls。\n"
    "如果用户意图只是获取信息（解释、回答、比较），不包含状态变更需求，返回空 tool_calls。\n"
    "如果用户意图同时包含内容问答和状态变更（如「总结一下并保存笔记」），仍应返回相应 tool_calls。\n"
    "requested_artifact 为 note 时，必须且只能返回一次 save_note；只在聊天中输出笔记正文不算完成请求。\n"
    "只使用下方工具说明中列出的工具，并遵守其用途与参数要求。\n"
)
