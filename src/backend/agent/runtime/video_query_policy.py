from __future__ import annotations

from dataclasses import dataclass

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.action_plan import AgentActionPlan, ScopeType
from backend.agent.schemas.tool_calls import GetVideoToolsCall, ToolExecutionResult, ToolName


@dataclass(frozen=True)
class VideoQueryPolicyDecision:
    kind: str


def build_video_query_policy_plan(
    *,
    context: AgentContext,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
) -> AgentActionPlan | None:
    if context.scope_type != "video":
        return None

    decision = classify_video_query(user_message)
    if decision is None:
        return None

    if decision.kind == "resource_status":
        has_status_evidence = any(
            result.tool_name == ToolName.GET_VIDEO_TOOLS and result.status == "ok"
            for result in observed_tool_results
        )
        if has_status_evidence:
            return AgentActionPlan(
                scope_type=ScopeType.VIDEO,
                tool_calls=[],
                reason="当前问题属于视频资源状态查询，已拿到结构化工具状态证据，可以直接组织回答。",
                direct_response="",
                use_answerer=True,
            )
        return AgentActionPlan(
            scope_type=ScopeType.VIDEO,
            tool_calls=[
                GetVideoToolsCall(
                    tool_name=ToolName.GET_VIDEO_TOOLS,
                    series_id=context.series_id,
                    video_id=context.video_id,
                )
            ],
            reason="当前问题属于视频资源状态查询，需要先读取该视频的结构化工具状态。",
            direct_response="",
            use_answerer=False,
        )

    if decision.kind == "cross_scope":
        return AgentActionPlan(
            scope_type=ScopeType.VIDEO,
            tool_calls=[],
            reason="当前问题需要跨视频判断衔接关系，已超出单视频证据范围，应明确引导用户切到 series 视角。",
            direct_response=(
                "这个问题需要结合整个系列来判断哪一节最衔接。"
                "你可以切到系列视图继续问我，我再基于整个系列帮你分析。"
            ),
            use_answerer=False,
        )

    return None


def classify_video_query(user_message: str) -> VideoQueryPolicyDecision | None:
    normalized = user_message.strip().lower()
    if not normalized:
        return None

    if _looks_like_resource_status_query(normalized):
        return VideoQueryPolicyDecision(kind="resource_status")
    if _looks_like_cross_scope_query(normalized):
        return VideoQueryPolicyDecision(kind="cross_scope")
    return None


def _looks_like_resource_status_query(normalized: str) -> bool:
    status_terms = ("状态", "已生成", "生成了", "生成情况", "有哪些工具", "什么状态")
    resource_terms = ("导图", "思维导图", "知识卡片", "卡片", "笔记", "概况", "工具")
    return any(term in normalized for term in status_terms) and any(term in normalized for term in resource_terms)


def _looks_like_cross_scope_query(normalized: str) -> bool:
    scope_terms = ("后面哪一节", "下一节", "哪一节最可能", "最可能与它衔接", "最可能衔接", "后续哪一节")
    relation_terms = ("衔接", "下一节", "后面", "后续")
    return any(term in normalized for term in scope_terms) or any(term in normalized for term in relation_terms)
