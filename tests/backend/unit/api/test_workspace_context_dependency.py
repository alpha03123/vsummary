from types import SimpleNamespace

from fastapi import Request

from backend.api.dependencies import get_workspace_context
from backend.core.context import WorkspaceContext


def test_request_workspace_context_overrides_product_default_context() -> None:
    scope = {"type": "http", "headers": [], "state": {}}
    request = Request(scope)
    expected = WorkspaceContext(workspace_id="cloud-workspace", actor_id="cloud-user", request_id="request-1")
    request.state.workspace_context = expected
    container = SimpleNamespace(context_provider=SimpleNamespace(get_context=lambda **_kwargs: None))

    assert get_workspace_context(request, container) == expected


def test_product_context_provider_is_used_without_request_override() -> None:
    scope = {"type": "http", "headers": [], "state": {}}
    request = Request(scope)
    expected = WorkspaceContext(workspace_id="local-workspace", actor_id="local-user", request_id="request-1")
    container = SimpleNamespace(context_provider=SimpleNamespace(get_context=lambda **_kwargs: expected))

    assert get_workspace_context(request, container) == expected
