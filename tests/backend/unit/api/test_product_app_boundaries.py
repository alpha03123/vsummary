from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.common.app import create_app as create_common_app
from backend.core.context import WorkspaceContext
from backend.local.http.app import create_app as create_local_app


class ProductAppBoundaryTests(unittest.TestCase):
    def test_common_app_does_not_register_local_routes(self) -> None:
        client = TestClient(create_common_app(SimpleNamespace(root_dir=None)))

        schema = client.get("/openapi.json").json()

        self.assertNotIn("/api/import/local/select", schema["paths"])
        self.assertNotIn("/api/linked/bilibili/cookie/init", schema["paths"])
        self.assertNotIn("/api/application-update", schema["paths"])
        self.assertEqual(client.get("/api/import/local/select").status_code, 404)
        self.assertEqual(client.get("/mcp").status_code, 404)
        self.assertEqual(client.get("/api/capabilities").json(), {
            "local_file_picker": False,
            "model_download": False,
            "billing": False,
            "workspace_members": False,
        })

    def test_local_app_registers_local_routes(self) -> None:
        root_dir = Path(__file__).resolve().parents[4]
        client = TestClient(create_local_app(SimpleNamespace(root_dir=root_dir)))

        schema = client.get("/openapi.json").json()

        self.assertIn("/api/import/local/select", schema["paths"])
        self.assertIn("/api/linked/bilibili/cookie/init", schema["paths"])
        self.assertIn("/api/application-update", schema["paths"])
        self.assertIn("/mcp", {getattr(route, "path", None) for route in client.app.routes})

    def test_common_app_rejects_a_request_context_without_a_matching_service_scope(self) -> None:
        container = SimpleNamespace(
            root_dir=None,
            context_provider=SimpleNamespace(
                get_context=lambda **_kwargs: WorkspaceContext("cloud-workspace", "cloud-user", "request-1")
            ),
            workspace_services_provider=SimpleNamespace(
                get_services=lambda _context: (_ for _ in ()).throw(LookupError("workspace missing"))
            ),
        )

        response = TestClient(create_common_app(container)).get("/api/videos")

        self.assertEqual(response.status_code, 404)

    def test_common_route_executes_the_scope_selected_by_request_context(self) -> None:
        selected_workspace_ids: list[str] = []
        scope = SimpleNamespace(check_health=lambda: object())
        container = SimpleNamespace(
            root_dir=None,
            context_provider=SimpleNamespace(
                get_context=lambda **_kwargs: WorkspaceContext("cloud-workspace", "cloud-user", "request-1")
            ),
            workspace_services_provider=SimpleNamespace(
                get_services=lambda context: selected_workspace_ids.append(context.workspace_id) or scope
            ),
        )

        response = TestClient(create_common_app(container)).get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(selected_workspace_ids, ["cloud-workspace"])
