from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.http.app import create_app


class MarkdownExportApiTests(unittest.TestCase):
    def test_exports_existing_summary_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_dir = _prepare_video_dir(root)
            (video_dir / "summary.md").write_bytes("# 已有摘要\n".encode("utf-8"))
            client = TestClient(create_app(_build_container(root)))

            response = client.get("/api/videos/series-1/video-1/exports/summary.md")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, "# 已有摘要\n".encode("utf-8"))
            self.assertIn("text/markdown", response.headers["content-type"])

    def test_export_header_supports_non_ascii_video_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_id = "1-4 准备工作：百度地图API秘钥(AK)"
            video_dir = root / "workspace" / "series-1" / video_id
            video_dir.mkdir(parents=True)
            (video_dir / "summary.md").write_text("# 第一讲\n", encoding="utf-8")
            client = TestClient(create_app(_build_container(root, video_id=video_id)))

            response = client.get(f"/api/videos/series-1/{video_id}/exports/summary.md")

            self.assertEqual(response.status_code, 200)
            self.assertIn("filename*=", response.headers["content-disposition"])

    def test_exports_transcript_markdown_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_dir = _prepare_video_dir(root)
            (video_dir / "transcript.cleaned.json").write_text(
                json.dumps(
                    {
                        "title": "第一讲",
                        "language": "zh",
                        "duration_seconds": 3.0,
                        "segments": [{"start_seconds": 0.0, "end_seconds": 3.0, "text": "开场"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(_build_container(root)))

            response = client.get("/api/videos/series-1/video-1/exports/transcript.md")

            self.assertEqual(response.status_code, 200)
            self.assertIn("# 第一讲 转写稿", response.text)
            self.assertIn("### 00:00 - 00:03\n开场", response.text)

    def test_exports_knowledge_cards_markdown_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_dir = _prepare_video_dir(root)
            (video_dir / "knowledge_cards.json").write_text(
                json.dumps(
                    {
                        "title": "第一讲",
                        "cards": [
                            {
                                "id": "card-1",
                                "title": "冷启动",
                                "kind": "method",
                                "summary": "先解决曝光。",
                                "details": "围绕目标用户发布内容。",
                                "tags": ["增长"],
                                "keywords": ["曝光"],
                                "related_card_ids": [],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(_build_container(root)))

            response = client.get("/api/videos/series-1/video-1/exports/knowledge-cards.md")

            self.assertEqual(response.status_code, 200)
            self.assertIn("# 第一讲 知识卡片", response.text)
            self.assertIn("## 冷启动", response.text)

    def test_missing_knowledge_cards_export_returns_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _prepare_video_dir(root)
            client = TestClient(create_app(_build_container(root)))

            response = client.get("/api/videos/series-1/video-1/exports/knowledge-cards.md")

            self.assertEqual(response.status_code, 404)

    def test_exports_notes_markdown_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_dir = _prepare_video_dir(root)
            (video_dir / "notes.json").write_text(
                json.dumps(
                    {
                        "notes": [
                            {
                                "id": "note-1",
                                "title": "重点",
                                "content": "这里是 **Markdown** 笔记。",
                                "source": "manual",
                                "created_at": "2026-06-06T10:00:00Z",
                                "updated_at": "2026-06-06T10:30:00Z",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(_build_container(root, title="第一讲")))

            response = client.get("/api/videos/series-1/video-1/exports/notes.md")

            self.assertEqual(response.status_code, 200)
            self.assertIn("# 第一讲 笔记", response.text)
            self.assertIn("## 重点", response.text)

    def test_missing_notes_export_returns_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _prepare_video_dir(root)
            client = TestClient(create_app(_build_container(root)))

            response = client.get("/api/videos/series-1/video-1/exports/notes.md")

            self.assertEqual(response.status_code, 404)

    def test_exports_series_archive_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = TestClient(create_app(_build_container(root)))

            response = client.get("/api/series/series-1/exports/mixed.zip")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"zip-content")
            self.assertEqual(response.headers["content-type"], "application/zip")
            self.assertIn("series-1-mixed.zip", response.headers["content-disposition"])


def _prepare_video_dir(root: Path) -> Path:
    video_dir = root / "workspace" / "series-1" / "video-1"
    video_dir.mkdir(parents=True)
    return video_dir


def _build_container(root: Path, title: str = "Video 1", video_id: str = "video-1"):
    source = SimpleNamespace(output_dir=root / "workspace" / "series-1" / video_id, title=title)
    return SimpleNamespace(
        root_dir=root,
        get_video_source=SimpleNamespace(run=lambda series_id, video_id: source),
        export_series_archive=SimpleNamespace(
            run=lambda series_id, export_kind: SimpleNamespace(
                filename=f"{series_id}-{export_kind}.zip",
                content=b"zip-content",
            )
        ),
    )


if __name__ == "__main__":
    unittest.main()
