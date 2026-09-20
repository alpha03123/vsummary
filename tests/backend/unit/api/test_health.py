from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from backend.api.routes.health import health


class HealthRouteTests(unittest.TestCase):
    def test_returns_ok_when_sql_workspace_is_readable(self) -> None:
        container = SimpleNamespace(sql_workspace=SimpleNamespace(get_workspace=lambda: object()))

        self.assertEqual(health(container).status, "ok")

    def test_returns_service_unavailable_when_sql_workspace_is_disconnected(self) -> None:
        def raise_disconnect():
            raise OperationalError("SELECT 1", {}, ConnectionError("connection refused"))

        container = SimpleNamespace(sql_workspace=SimpleNamespace(get_workspace=raise_disconnect))

        with self.assertRaises(HTTPException) as caught:
            health(container)

        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail, "数据服务暂不可用，正在恢复连接。")
