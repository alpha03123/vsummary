from tests._api_fixtures import make_api_container, make_workspace_services, mock_service

from fastapi import Request

from backend.api.dependencies import get_workspace_context, get_workspace_services
from backend.core.context import WorkspaceContext, WorkspaceContextProvider, WorkspaceServicesProvider
from backend.local.composition import LocalWorkspaceContextProvider


def test_request_workspace_context_overrides_product_default_context() -> None:
    scope = {"type": "http", "headers": [], "state": {}}
    request = Request(scope)
    expected = WorkspaceContext(workspace_id="cloud-workspace", actor_id="cloud-user", request_id="request-1")
    request.state.workspace_context = expected
    provider = mock_service(WorkspaceContextProvider, get_context=None)
    container = make_api_container(context_provider=provider)

    assert get_workspace_context(request, container) == expected
    provider.get_context.assert_not_called()


def test_product_context_provider_is_used_without_request_override() -> None:
    scope = {"type": "http", "headers": [], "state": {}}
    request = Request(scope)
    request.state.request_id = "request-1"
    expected = WorkspaceContext(workspace_id="local-workspace", actor_id="local-user", request_id="request-1")
    container = make_api_container(context_provider=LocalWorkspaceContextProvider(workspace_id="local-workspace"))

    assert get_workspace_context(request, container) == expected


def test_workspace_services_are_resolved_from_the_request_context() -> None:
    context = WorkspaceContext(workspace_id="cloud-workspace", actor_id="cloud-user", request_id="request-1")
    expected = make_workspace_services(workspace_id="cloud-workspace")
    provider = mock_service(WorkspaceServicesProvider, get_services=expected)
    container = make_api_container(workspace_services_provider=provider)

    services = get_workspace_services(context=context, container=container)

    assert services is expected
    provider.get_services.assert_called_once_with(context)
