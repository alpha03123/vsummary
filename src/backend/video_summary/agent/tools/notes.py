from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import (
    OpenKnowledgeCardsCall,
    OpenNotesCall,
    SaveNoteCall,
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

SAVE_NOTE_TOOL = ToolDefinition(
    name=ToolName.SAVE_NOTE,
    title="保存笔记",
    description="为当前视频创建一条笔记，适合用户要求你整理、记录或摘出重点时使用。",
    plane=ToolPlane.UI_ACTION,
    arguments={
        "note_title": "笔记标题",
        "note_content": "支持 Markdown 的笔记正文",
    },
    contexts=(ToolContextTag.VIDEO,),
)


def execute_open_knowledge_cards(call: OpenKnowledgeCardsCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_KNOWLEDGE_CARDS,
        status="ok",
        payload={"selected_tool": "knowledge-cards"},
    )


def execute_open_notes(call: OpenNotesCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_NOTES,
        status="ok",
        payload={"selected_tool": "notes"},
    )


def execute_save_note(call: SaveNoteCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.SAVE_NOTE,
        status="ok",
        payload={
            "action": "save_note",
            "selected_tool": "notes",
            "note_title": call.note_title.strip(),
            "note_content": call.note_content.strip(),
            "note_source": "agent",
        },
    )
