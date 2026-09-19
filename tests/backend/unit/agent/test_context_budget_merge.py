from backend.agent.context.budget import _merge_context
from backend.agent.memory.context import AgentContext, ToolAvailability
from backend.video_summary.agent_adapter import _parse_session_id


def test_merge_context_revalidates_tool_availability_models():
    base_context = AgentContext(
        session_id="session-1",
        overview=ToolAvailability(available=True, generated=True, status="ready"),
    )
    context_override = AgentContext(
        session_id="session-1",
        overview=ToolAvailability(available=False, generated=False, status="idle"),
    )

    merged_context = _merge_context(base_context, context_override)

    assert isinstance(merged_context.overview, ToolAvailability)
    assert merged_context.overview.available is False
    assert merged_context.overview.generated is False
    assert merged_context.overview.status == "idle"


def test_session_parser_ignores_frontend_conversation_instance_suffix():
    assert _parse_session_id("video|series-1|video-1::1758274800000") == (
        "video",
        "series-1",
        "video-1",
    )
