from __future__ import annotations

import json
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
from backend.video_summary.infrastructure.faster_whisper_models import FasterWhisperModelInfo

app = api_module.app


class FakeGenerator:
    def run(
        self,
        source_path: Path,
        output_dir: Path,
        progress_reporter=None,
        transcript_enhancement_enabled=None,
    ) -> SummaryDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        if progress_reporter is not None:
            progress_reporter.update("transcribe", 55.0, "正在转写")
        payload = {
            "title": source_path.stem,
            "one_sentence_summary": "generated",
            "core_problem": "problem" if transcript_enhancement_enabled is not False else "problem-without-enhancement",
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
        }
        (output_dir / "summary.json").write_text(__import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8")
        (output_dir / "summary.md").write_text("# generated", encoding="utf-8")
        return SummaryDocument(markdown="# generated", summary_data=payload)


class FakeMindmapGenerator:
    def run(self, source_path: Path, output_dir: Path, summary_data: dict[str, object]) -> dict[str, object]:
        payload = {
            "id": "root",
            "title": source_path.stem,
            "summary": "mindmap",
            "start_seconds": 0.0,
            "end_seconds": 10.0,
            "children": [],
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "mindmap.json").write_text(__import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload


class FakeFasterWhisperModelManager:
    def __init__(self) -> None:
        self.downloaded_models = {"large-v3-turbo"}

    def is_supported(self, model_size: str) -> bool:
        return model_size in {"small", "medium", "large-v3", "large-v3-turbo"}

    def list_models(self, current_model_size: str) -> list[FasterWhisperModelInfo]:
        return [
            FasterWhisperModelInfo(
                id=model_id,
                label=model_id,
                downloaded=model_id in self.downloaded_models,
                current=model_id == current_model_size,
                recommended=model_id == "large-v3-turbo",
            )
            for model_id in ["small", "medium", "large-v3", "large-v3-turbo"]
        ]

    def download(self, model_size: str):
        self.downloaded_models.add(model_size)
        return model_size


class ApiContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "video_include"
        (self.root / "videos" / "series-a").mkdir(parents=True)
        (self.root / "config").mkdir(parents=True)
        (self.root / "videos" / "series-a" / "intro.mp4").write_text("video", encoding="utf-8")
        (self.root / "videos" / "series-a" / "advanced.mp4").write_text("video", encoding="utf-8")
        (self.root / "config" / "settings.toml").write_text(
            """
[asr]
provider = "faster_whisper"
language = "zh"
transcript_enhancement_enabled = true

[asr.faster_whisper]
device = "auto"
model_size = "large-v3-turbo"
compute_type = "float16"
transcription_mode = "fast"

[openai]
base_url = "http://127.0.0.1:8317/v1/responses"
model = "gpt-5.4"

[workspace_ui]
theme = "light"
show_takeaways = true
ai_transcript_enhancement = true
""".strip(),
            encoding="utf-8",
        )
        (self.root / "workspace" / "series-a" / "advanced").mkdir(parents=True)
        (self.root / "workspace" / "series-a" / "advanced" / "summary.json").write_text(
            json.dumps(
                {
                    "title": "advanced",
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
                    "key_takeaways": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.root / "workspace" / "series-a" / "advanced" / "transcript.cleaned.json").write_text(
            json.dumps(
                {
                    "segments": [
                        {"start_seconds": 1.0, "end_seconds": 2.0, "text": "第一句"},
                        {"start_seconds": 11.0, "end_seconds": 12.0, "text": "第二句"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.root / "workspace" / "series-a" / "advanced" / "mindmap.json").write_text(
            '{"id":"root","title":"advanced","summary":"","start_seconds":0,"end_seconds":0,"children":[]}',
            encoding="utf-8",
        )
        self.original_container = api_module.CONTAINER
        api_module.CONTAINER = build_api_container(
            self.root,
            generator=FakeGenerator(),
            mindmap_generator=FakeMindmapGenerator(),
            faster_whisper_model_manager=FakeFasterWhisperModelManager(),
        )
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

    async def test_settings_endpoint_returns_workspace_settings(self) -> None:
        response = await self.client.get("/api/settings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "theme": "light",
                "show_takeaways": True,
                "ai_transcript_enhancement": True,
                "asr_model_quality": "large-v3-turbo",
                "transcription_mode": "fast",
            },
        )

    async def test_settings_endpoint_updates_toml_file(self) -> None:
        response = await self.client.put(
            "/api/settings",
            json={
                "theme": "dark",
                "show_takeaways": False,
                "ai_transcript_enhancement": False,
                "asr_model_quality": "large-v3",
                "transcription_mode": "accurate",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "theme": "dark",
                "show_takeaways": False,
                "ai_transcript_enhancement": False,
                "asr_model_quality": "large-v3",
                "transcription_mode": "accurate",
            },
        )
        saved_text = (self.root / "config" / "settings.toml").read_text(encoding="utf-8")
        self.assertIn('theme = "dark"', saved_text)
        self.assertIn("show_takeaways = false", saved_text)
        self.assertIn("ai_transcript_enhancement = false", saved_text)
        self.assertIn('model_size = "large-v3"', saved_text)
        self.assertIn('transcription_mode = "accurate"', saved_text)

    async def test_faster_whisper_models_endpoint_returns_download_status(self) -> None:
        response = await self.client.get("/api/asr/faster-whisper/models")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["id"], "small")
        self.assertFalse(payload[0]["downloaded"])
        self.assertTrue(payload[-1]["downloaded"])
        self.assertTrue(payload[-1]["current"])

    async def test_faster_whisper_model_download_endpoint_marks_model_as_downloaded(self) -> None:
        response = await self.client.post("/api/asr/faster-whisper/models/medium/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "medium")
        self.assertTrue(response.json()["downloaded"])

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
        self.assertNotIn("mindmap", payload)
        self.assertEqual(
            payload["chapters"][0]["transcript_segments"],
            [{"start_seconds": 1.0, "end_seconds": 2.0, "text": "第一句"}],
        )

    async def test_summary_endpoint_returns_404_for_missing_video(self) -> None:
        response = await self.client.get("/api/videos/series-a/intro/summary")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "summary not found for video 'series-a/intro'")

    async def test_generate_endpoint_creates_summary_for_selected_video(self) -> None:
        response = await self.client.post("/api/videos/series-a/intro/generate")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "intro")
        self.assertTrue((self.root / "workspace" / "series-a" / "intro" / "summary.json").exists())
        self.assertFalse((self.root / "workspace" / "series-a" / "intro" / "mindmap.json").exists())

    async def test_generate_endpoint_accepts_transcript_enhancement_flag(self) -> None:
        response = await self.client.post(
            "/api/videos/series-a/intro/generate",
            json={"transcript_enhancement_enabled": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["core_problem"], "problem-without-enhancement")

    async def test_tools_endpoint_returns_generation_status_for_each_tool(self) -> None:
        response = await self.client.get("/api/videos/series-a/advanced/tools")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["overview"]["generated"])
        self.assertTrue(payload["mindmap"]["generated"])
        self.assertTrue(payload["preview"]["available"])
        self.assertEqual(payload["preview"]["preview_url"], "/api/videos/series-a/advanced/preview")

    async def test_mindmap_endpoint_returns_existing_mindmap(self) -> None:
        response = await self.client.get("/api/videos/series-a/advanced/mindmap")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "root")

    async def test_generate_mindmap_endpoint_requires_existing_summary(self) -> None:
        response = await self.client.post("/api/videos/series-a/intro/mindmap/generate")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "summary not found for video 'series-a/intro'")

    async def test_generate_mindmap_endpoint_creates_mindmap_when_summary_exists(self) -> None:
        response = await self.client.post("/api/videos/series-a/advanced/mindmap/generate")

        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.root / "workspace" / "series-a" / "advanced" / "mindmap.json").exists())

    async def test_generation_progress_endpoint_returns_completed_snapshot_after_generation(self) -> None:
        response = await self.client.post("/api/videos/series-a/intro/generate")

        self.assertEqual(response.status_code, 200)

        progress_response = await self.client.get("/api/videos/series-a/intro/generate/progress")

        self.assertEqual(progress_response.status_code, 200)
        self.assertIn('"status": "completed"', progress_response.text)
        self.assertIn('"progress": 100.0', progress_response.text)


if __name__ == "__main__":
    unittest.main()
