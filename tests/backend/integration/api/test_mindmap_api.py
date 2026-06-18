from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import create_app


class MindmapExportApiTests(unittest.TestCase):
    """Integration tests for GET /api/videos/{series_id}/{video_id}/mindmap/export."""

    def test_export_returns_markdown_content_type(self) -> None:
        mindmap_node = {
            "id": "root",
            "title": "测试导图",
            "summary": "",
            "start_seconds": 0.0,
            "end_seconds": 0.0,
            "children": [
                {"id": "c1", "title": "子节点1", "summary": "摘要", "start_seconds": 0.0, "end_seconds": 60.0, "children": []},
            ],
        }
        container = _build_container(mindmap_node=mindmap_node, title="测试视频")
        client = TestClient(create_app(container))

        response = client.get("/api/videos/s1/v1/mindmap/export?format=md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response.headers["content-type"])
        self.assertIn("charset=utf-8", response.headers["content-type"])

    def test_export_returns_content_disposition_header(self) -> None:
        mindmap_node = {
            "id": "root",
            "title": "测试导图",
            "summary": "",
            "start_seconds": 0.0,
            "end_seconds": 0.0,
            "children": [],
        }
        container = _build_container(mindmap_node=mindmap_node, title="测试视频")
        client = TestClient(create_app(container))

        response = client.get("/api/videos/s1/v1/mindmap/export?format=md")

        self.assertIn("attachment", response.headers["content-disposition"])

    def test_export_returns_404_when_mindmap_not_found(self) -> None:
        container = _build_container(mindmap_node=None)
        client = TestClient(create_app(container))

        response = client.get("/api/videos/s1/v1/mindmap/export?format=md")

        self.assertEqual(response.status_code, 404)

    def test_export_returns_400_for_unsupported_format(self) -> None:
        mindmap_node = {
            "id": "root",
            "title": "测试导图",
            "summary": "",
            "start_seconds": 0.0,
            "end_seconds": 0.0,
            "children": [],
        }
        container = _build_container(mindmap_node=mindmap_node)
        client = TestClient(create_app(container))

        response = client.get("/api/videos/s1/v1/mindmap/export?format=pdf")

        self.assertEqual(response.status_code, 400)


def _build_container(
    *,
    root: Path | None = None,
    title: str = "测试视频",
    mindmap_node: dict | None = None,
) -> SimpleNamespace:
    """Build a minimal mock ApiContainer for mindmap export endpoint testing.

    Args:
        root: Temp directory root (defaults to current working directory).
        title: Video title used in the mindmap DTO and video source.
        mindmap_node: The mindmap dict to return, or None to simulate missing mindmap.

    Returns:
        SimpleNamespace with enough attributes for the mindmap export endpoint.
    """
    resolved_root = root or Path.cwd()

    mindmap_dto = None
    if mindmap_node is not None:
        mindmap_dto = SimpleNamespace(
            series_id="s1",
            video_id="v1",
            title=title,
            mindmap=mindmap_node,
        )

    video_source = SimpleNamespace(
        output_dir=resolved_root / "workspace" / "s1" / "v1",
        title=title,
    )

    return SimpleNamespace(
        root_dir=resolved_root,
        get_video_source=SimpleNamespace(run=lambda series_id, video_id: video_source),
        get_video_mindmap=SimpleNamespace(run=lambda series_id, video_id: mindmap_dto),
    )


if __name__ == "__main__":
    unittest.main()
