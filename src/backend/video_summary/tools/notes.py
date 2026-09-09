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
    description=(
        "为当前视频创建一条 Agent 笔记。当用户语义上要求生成、整理、记录或保存一份可回看的笔记时，"
        "必须调用本工具一次；只回复一段聊天文本不能替代保存操作。"
        "当用户要求生成笔记时，标题和正文必须基于当前视频的概况、转写和可用 evidence；证据不足时不要调用。"
        "正文使用清晰、适合长期阅读的 Markdown，提炼核心主题、关键结论、重要细节与行动要点，"
        "避免机械堆砌标题或过度展开，篇幅应与视频内容匹配。"
    ),
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
