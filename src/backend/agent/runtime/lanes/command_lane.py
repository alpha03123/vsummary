from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.runtime.request_router import RouteKind, RouteToolName
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import (
    GenerateMindmapCall,
    GenerateOverviewCall,
    OpenKnowledgeCardsCall,
    OpenMindmapCall,
    OpenNotesCall,
    OpenOverviewCall,
    OpenSeriesHomeCall,
    OpenSeriesOverviewCall,
    OpenVideoCall,
    SaveNoteCall,
    ToolCall,
    ToolExecutionResult,
    ToolName,
)
from backend.agent.tools import get_tool_definition


def build_open_tool_plan(context: AgentContext, tool_name: RouteToolName | None, reason: str) -> AgentActionPlan | None:
    if tool_name is None:
        return None
    mapping: dict[RouteToolName, tuple[str, list[ToolCall]]] = {
        RouteToolName.OPEN_SERIES_HOME: ("open_tool", [OpenSeriesHomeCall(tool_name=ToolName.OPEN_SERIES_HOME)]),
        RouteToolName.OPEN_SERIES_OVERVIEW: ("open_tool", [OpenSeriesOverviewCall(tool_name=ToolName.OPEN_SERIES_OVERVIEW)]),
        RouteToolName.OPEN_OVERVIEW: ("open_tool", _build_open_overview_calls(context)),
        RouteToolName.OPEN_MINDMAP: ("open_tool", _build_open_mindmap_calls(context)),
        RouteToolName.OPEN_KNOWLEDGE_CARDS: ("open_tool", [OpenKnowledgeCardsCall(tool_name=ToolName.OPEN_KNOWLEDGE_CARDS)]),
        RouteToolName.OPEN_NOTES: ("open_tool", [OpenNotesCall(tool_name=ToolName.OPEN_NOTES)]),
        RouteToolName.OPEN_VIDEO: ("open_tool", [OpenVideoCall(tool_name=ToolName.OPEN_VIDEO)]),
    }
    intent_type, calls = mapping[tool_name]
    return AgentActionPlan(
        intent_type=intent_type,
        scope_type="series" if tool_name in {RouteToolName.OPEN_SERIES_HOME, RouteToolName.OPEN_SERIES_OVERVIEW} else "video",
        tool_calls=calls,
        reason=reason or "这是明确的页面切换请求，直接执行工具。",
    )


def build_generation_plan(route_kind: RouteKind, scope_type: str, reason: str) -> AgentActionPlan | None:
    if route_kind == RouteKind.GENERATE_OVERVIEW:
        return AgentActionPlan(
            intent_type="generate_overview",
            scope_type=scope_type,
            tool_calls=[GenerateOverviewCall(tool_name=ToolName.GENERATE_OVERVIEW)],
            reason=reason or "这是明确的生成概况请求，直接执行工具。",
        )
    if route_kind == RouteKind.GENERATE_MINDMAP:
        return AgentActionPlan(
            intent_type="generate_mindmap",
            scope_type=scope_type,
            tool_calls=[GenerateMindmapCall(tool_name=ToolName.GENERATE_MINDMAP)],
            reason=reason or "这是明确的生成导图请求，直接执行工具。",
        )
    return None


def build_save_note_plan(context: AgentContext, reason: str) -> AgentActionPlan | None:
    if context.scope_type != "video":
        return None
    if not context.series_id or not context.video_id:
        return None
    from backend.agent.schemas.tool_calls import GetVideoSummaryCall

    return AgentActionPlan(
        intent_type="save_note",
        scope_type="video",
        tool_calls=[
            GetVideoSummaryCall(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                series_id=context.series_id,
                video_id=context.video_id,
            )
        ],
        reason=reason or "先读取当前视频概况，再整理成一条可直接保存的笔记。",
    )


def build_deterministic_assistant_message(
    plan: AgentActionPlan,
    tool_results: list[ToolExecutionResult],
) -> str | None:
    if not tool_results:
        return None
    last_result = tool_results[-1]
    title = get_tool_definition(last_result.tool_name).title
    if plan.intent_type.value == "open_tool":
        if any(
            result.tool_name in {ToolName.GENERATE_OVERVIEW, ToolName.GENERATE_MINDMAP}
            for result in tool_results
        ):
            return f"我已经开始帮你生成并打开{_strip_open_prefix(title)}。"
        return f"我已经帮你{title}。"
    if plan.intent_type.value in {"generate_overview", "generate_mindmap"}:
        return f"我已经开始帮你{title}。"
    if plan.intent_type.value == "save_note" and last_result.tool_name == ToolName.SAVE_NOTE:
        return "我已经帮你记好这条笔记。"
    if plan.intent_type.value == "out_of_scope":
        return "这个问题超出了当前视频知识工作台的支持范围。我更适合帮你处理系列总结、视频概括、原话定位、时间点定位和笔记整理这类问题。"
    return None


def _build_open_overview_calls(context: AgentContext) -> list[ToolCall]:
    if context.scope_type == "video" and not context.overview.generated:
        return [
            GenerateOverviewCall(tool_name=ToolName.GENERATE_OVERVIEW),
            OpenOverviewCall(tool_name=ToolName.OPEN_OVERVIEW),
        ]
    return [OpenOverviewCall(tool_name=ToolName.OPEN_OVERVIEW)]


def _build_open_mindmap_calls(context: AgentContext) -> list[ToolCall]:
    if context.scope_type == "video" and not context.mindmap.generated:
        return [
            GenerateMindmapCall(tool_name=ToolName.GENERATE_MINDMAP),
            OpenMindmapCall(tool_name=ToolName.OPEN_MINDMAP),
        ]
    return [OpenMindmapCall(tool_name=ToolName.OPEN_MINDMAP)]


def _strip_open_prefix(title: str) -> str:
    normalized = title.strip()
    if normalized.startswith("打开"):
        return normalized[2:] or normalized
    return normalized
