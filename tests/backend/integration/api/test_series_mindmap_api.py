from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import create_app


class SeriesMindmapApiTests(unittest.TestCase):
    """Integration tests for series mindmap endpoints."""

    def test_get_series_mindmap_returns_tree(self) -> None:
        mindmap_node = {"id": "root", "title": "测试系列", "summary": "", "children": [
            {"id": "t1", "title": "主题1", "summary": "", "children": []},
        ]}
        container = _build_series_container(mindmap_node=mindmap_node)
        client = TestClient(create_app(container))
        response = client.get("/api/series/s1/mindmap")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "测试系列")

    def test_get_series_mindmap_404_when_not_generated(self) -> None:
        container = _build_series_container(mindmap_node=None)
        client = TestClient(create_app(container))
        response = client.get("/api/series/s1/mindmap")
        self.assertEqual(response.status_code, 404)

    def test_export_series_mindmap_returns_markdown(self) -> None:
        mindmap_node = {"id": "root", "title": "测试系列", "summary": "", "children": []}
        container = _build_series_container(mindmap_node=mindmap_node)
        client = TestClient(create_app(container))
        response = client.get("/api/series/s1/mindmap/export?format=md")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response.headers["content-type"])

    def test_export_series_mindmap_returns_400_for_unsupported_format(self) -> None:
        mindmap_node = {"id": "root", "title": "测试系列", "summary": "", "children": []}
        container = _build_series_container(mindmap_node=mindmap_node)
        client = TestClient(create_app(container))
        response = client.get("/api/series/s1/mindmap/export?format=pdf")
        self.assertEqual(response.status_code, 400)

    def test_concurrent_generation_lock_mechanism(self) -> None:
        from backend.api.routes.videos import _acquire_series_mindmap_lock, _release_series_mindmap_lock
        acquired = _acquire_series_mindmap_lock("test-series")
        self.assertTrue(acquired)
        second = _acquire_series_mindmap_lock("test-series")
        self.assertFalse(second)
        _release_series_mindmap_lock("test-series")
        reacquired = _acquire_series_mindmap_lock("test-series")
        self.assertTrue(reacquired)
        _release_series_mindmap_lock("test-series")


def _build_series_container(
    *, mindmap_node: dict | None = None, series_id: str = "s1", title: str = "测试系列"
) -> SimpleNamespace:
    mindmap_dto = None
    if mindmap_node is not None:
        mindmap_dto = SimpleNamespace(
            series_id=series_id, video_id="", title=title, mindmap=mindmap_node,
        )
    return SimpleNamespace(
        get_series_mindmap=SimpleNamespace(run=lambda sid: mindmap_dto),
    )


if __name__ == "__main__":
    unittest.main()
