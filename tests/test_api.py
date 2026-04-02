from __future__ import annotations

import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.api.app import app


class ApiContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_health_endpoint_returns_ok(self) -> None:
        response = await self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    async def test_videos_endpoint_returns_sample_library(self) -> None:
        response = await self.client.get("/api/videos")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["workspace"]["id"], ROOT.name)
        self.assertEqual(payload["series"][0]["id"], "output")
        self.assertGreaterEqual(len(payload["videos"]), 1)
        self.assertEqual(payload["series"][0]["videos"], payload["videos"])

    async def test_summary_endpoint_returns_existing_sample_summary(self) -> None:
        library = (await self.client.get("/api/videos")).json()
        video_id = library["videos"][0]["id"]

        response = await self.client.get(f"/api/videos/{video_id}/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["title"], video_id)
        self.assertIn("chapters", payload)
        self.assertIn("mindmap", payload)

    async def test_summary_endpoint_returns_404_for_missing_video(self) -> None:
        response = await self.client.get("/api/videos/not-found/summary")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "summary not found for video 'not-found'")


if __name__ == "__main__":
    unittest.main()
