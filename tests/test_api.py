from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.api import app as api_module
from backend.api.bootstrap import build_api_container
from backend.video_summary.domain.models import SummaryDocument

app = api_module.app


class FakeGenerator:
    def run(self, source_path: Path, output_dir: Path) -> SummaryDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "title": source_path.stem,
            "one_sentence_summary": "generated",
            "core_problem": "problem",
            "key_takeaways": ["takeaway"],
            "chapters": [
                {
                    "id": "chapter-1",
                    "title": "Intro",
                    "summary": "summary",
                    "key_points": ["point"],
                    "start_seconds": 0.0,
                    "end_seconds": 10.0,
                }
            ],
            "mindmap": {
                "id": "root",
                "title": source_path.stem,
                "summary": "mindmap",
                "start_seconds": 0.0,
                "end_seconds": 10.0,
                "children": [],
            },
        }
        (output_dir / "summary.json").write_text(__import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8")
        (output_dir / "summary.md").write_text("# generated", encoding="utf-8")
        (output_dir / "mindmap.json").write_text(
            __import__("json").dumps(payload["mindmap"], ensure_ascii=False),
            encoding="utf-8",
        )
        return SummaryDocument(markdown="# generated", summary_data=payload, mindmap_data=payload["mindmap"])


class ApiContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "video_include"
        (self.root / "videos" / "series-a").mkdir(parents=True)
        (self.root / "videos" / "series-a" / "intro.mp4").write_text("video", encoding="utf-8")
        (self.root / "videos" / "series-a" / "advanced.mp4").write_text("video", encoding="utf-8")
        (self.root / "workspace" / "series-a" / "advanced").mkdir(parents=True)
        (self.root / "workspace" / "series-a" / "advanced" / "summary.json").write_text(
            '{"title":"advanced","chapters":[],"mindmap":{"id":"root","title":"advanced","children":[]}}',
            encoding="utf-8",
        )
        self.original_container = api_module.CONTAINER
        api_module.CONTAINER = build_api_container(self.root, generator=FakeGenerator())
        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        api_module.CONTAINER = self.original_container
        self.temp_dir.cleanup()

    async def test_health_endpoint_returns_ok(self) -> None:
        response = await self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    async def test_videos_endpoint_returns_workspace_library(self) -> None:
        response = await self.client.get("/api/videos")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["workspace"]["id"], "video_include")
        self.assertEqual(payload["series"][0]["id"], "series-a")
        self.assertEqual([video["id"] for video in payload["series"][0]["videos"]], ["advanced", "intro"])
        self.assertTrue(payload["series"][0]["videos"][0]["processed"])
        self.assertFalse(payload["series"][0]["videos"][1]["processed"])

    async def test_summary_endpoint_returns_existing_sample_summary(self) -> None:
        response = await self.client.get("/api/videos/series-a/advanced/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["title"], "advanced")
        self.assertIn("chapters", payload)
        self.assertIn("mindmap", payload)

    async def test_summary_endpoint_returns_404_for_missing_video(self) -> None:
        response = await self.client.get("/api/videos/series-a/intro/summary")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "summary not found for video 'series-a/intro'")

    async def test_generate_endpoint_creates_summary_for_selected_video(self) -> None:
        response = await self.client.post("/api/videos/series-a/intro/generate")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "intro")
        self.assertTrue((self.root / "workspace" / "series-a" / "intro" / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
