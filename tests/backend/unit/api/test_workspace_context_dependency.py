from dataclasses import fields
from types import SimpleNamespace

from fastapi import Request

from backend.api.dependencies import get_workspace_context, get_workspace_services
from backend.api.di.bootstrap import ApiContainer
from backend.api.di.workspace_services import WorkspaceServices
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


def test_workspace_services_are_resolved_from_the_request_context() -> None:
    context = WorkspaceContext(workspace_id="cloud-workspace", actor_id="cloud-user", request_id="request-1")
    expected = SimpleNamespace(marker="cloud-scope")
    container = SimpleNamespace(
        workspace_services_provider=SimpleNamespace(get_services=lambda received: expected if received == context else None)
    )

    services = get_workspace_services(context=context, container=container)

    assert services.marker == "cloud-scope"


def test_host_container_cannot_expose_workspace_bound_services() -> None:
    host_fields = {field.name for field in fields(ApiContainer)}
    scope_fields = {field.name for field in fields(WorkspaceServices)}

    assert {"sql_workspace", "list_video_library", "get_video_summary", "job_summary_generator"}.isdisjoint(host_fields)
    assert {"workspace_id", "list_video_library", "get_video_summary", "job_summary_generator"}.issubset(scope_fields)
    assert "job_repository" in host_fields
