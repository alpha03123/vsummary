from backend.agent.context.budget import _merge_context
from backend.agent.memory.context import AgentContext, ToolAvailability


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
