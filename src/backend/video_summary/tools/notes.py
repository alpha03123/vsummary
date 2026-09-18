from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import (
    OpenKnowledgeCardsCall,
    OpenNotesCall,
    ToolDefinition,
    ToolContextTag,
    ToolExecutionResult,
    ToolName,
    ToolPlane,
)

OPEN_KNOWLEDGE_CARDS_TOOL = ToolDefinition(
    name=ToolName.OPEN_KNOWLEDGE_CARDS,
    title="打开知识卡片",
    description="切换到知识卡片工具页。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.VIDEO,),
)

OPEN_NOTES_TOOL = ToolDefinition(
    name=ToolName.OPEN_NOTES,
    title="打开笔记工具",
    description="切换到笔记工具页。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.VIDEO,),
)


def execute_open_knowledge_cards(call: OpenKnowledgeCardsCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_KNOWLEDGE_CARDS,
        status="ok",
        payload={},
    )


def execute_open_notes(call: OpenNotesCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_NOTES,
        status="ok",
        payload={},
    )
