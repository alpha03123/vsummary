from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentTranscriptLookup
from backend.agent.schemas.tool_calls import TranscriptLookupCall, ToolDefinition, ToolExecutionResult, ToolName

TRANSCRIPT_LOOKUP_TOOL = ToolDefinition(
    name=ToolName.TRANSCRIPT_LOOKUP,
    title="检索转写文本",
    description="基于转写或章节内容检索答案。",
    arguments={"query": "用户要查找的关键词或问题"},
)


def create_transcript_lookup_handler(lookup: AgentTranscriptLookup):
    def execute_transcript_lookup(call: TranscriptLookupCall, context: AgentContext) -> ToolExecutionResult:
        lookup_result = lookup.lookup(context, call.query.strip())
        payload: dict[str, object] = {
            "query": lookup_result.query,
            "matches": [
                {
                    "source": item.source,
                    "text": item.text,
                    "start_seconds": item.start_seconds,
                    "end_seconds": item.end_seconds,
                    "chapter_title": item.chapter_title,
                    "score": round(item.score, 3),
                }
                for item in lookup_result.matches
            ],
        }
        if lookup_result.seek_seconds is not None and lookup_result.matches:
            top_match = lookup_result.matches[0]
            payload.update(
                {
                    "selected_tool": "video",
                    "seek_seconds": lookup_result.seek_seconds,
                    "match_end_seconds": top_match.end_seconds,
                    "matched_text": top_match.text,
                    "chapter_title": top_match.chapter_title,
                }
            )
        return ToolExecutionResult(
            tool_name=ToolName.TRANSCRIPT_LOOKUP,
            status="ok",
            payload=payload,
        )

    return execute_transcript_lookup
