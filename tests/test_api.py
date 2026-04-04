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
from backend.video_summary.infrastructure.settings import normalize_openai_base_url

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


class FakeAgentService:
    def __init__(self) -> None:
        self.last_context_override = None

    def run_with_context(self, *, session_id: str, user_message: str, context_override=None):
        from backend.agent.schemas.action_plan import AgentActionPlan, AgentTurnResult
        from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName

        self.last_context_override = context_override
        return AgentTurnResult(
            assistant_message=f"已收到：{user_message}",
            plan=AgentActionPlan(
                intent_type="open_tool",
                scope_type="video",
                assistant_message="",
                tool_calls=[],
                reason=f"session={session_id}",
                out_of_scope_reason="",
            ),
            tool_results=[
                ToolExecutionResult(
                    tool_name=ToolName.OPEN_OVERVIEW,
                    status="ok",
                    payload={"selected_tool": "overview"},
                )
            ],
        )


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

    def download(self, model_size: str, progress_reporter=None):
        if progress_reporter is not None:
            progress_reporter.update("download", 45.0, "正在下载 model.bin")
            progress_reporter.completed("模型下载完成")
        self.downloaded_models.add(model_size)
        return model_size


class ApiContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "video_include"
        (self.root / "videos" / "series-a").mkdir(parents=True)
        (self.root / "config").mkdir(parents=True)
        (self.root / ".env").write_text(
            "\n".join(
                [
                    "OPENAI_PROVIDER=openai_compatible",
                    "OPENAI_BASE_URL=http://127.0.0.1:8317/v1",
                    "OPENAI_MODEL=gpt-5.4",
                    "OPENAI_API_KEY=test-key",
                    "",
                ]
            ),
            encoding="utf-8",
        )
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

[workspace_ui]
theme = "light"
show_takeaways = true
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
        self.fake_agent_service = FakeAgentService()
        api_module.CONTAINER = api_module.CONTAINER.__class__(**{
            **api_module.CONTAINER.__dict__,
            "get_agent_service": lambda: self.fake_agent_service,
        })
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

    async def test_openai_base_url_is_normalized_to_api_root(self) -> None:
        self.assertEqual(
            normalize_openai_base_url("https://api.openai.com/v1/chat/completions"),
            "https://api.openai.com/v1",
        )
        self.assertEqual(
            normalize_openai_base_url("https://api.openai.com/v1/responses"),
            "https://api.openai.com/v1",
        )
        self.assertEqual(
            normalize_openai_base_url("https://api.openai.com/v1"),
            "https://api.openai.com/v1",
        )

    async def test_settings_endpoint_returns_workspace_settings(self) -> None:
        response = await self.client.get("/api/settings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "theme": "light",
                "show_takeaways": True,
                "transcript_enhancement_enabled": True,
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
                "transcript_enhancement_enabled": False,
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
                "transcript_enhancement_enabled": False,
                "asr_model_quality": "large-v3",
                "transcription_mode": "accurate",
            },
        )
        saved_text = (self.root / "config" / "settings.toml").read_text(encoding="utf-8")
        self.assertIn('theme = "dark"', saved_text)
        self.assertIn("show_takeaways = false", saved_text)
        self.assertIn("transcript_enhancement_enabled = false", saved_text)
        self.assertIn('model_size = "large-v3"', saved_text)
        self.assertIn('transcription_mode = "accurate"', saved_text)
        self.assertNotIn("[openai]", saved_text)
        self.assertNotIn("api_key =", saved_text)
        env_text = (self.root / ".env").read_text(encoding="utf-8")
        self.assertIn("OPENAI_API_KEY=test-key", env_text)

    async def test_provider_settings_endpoint_reads_env_file(self) -> None:
        response = await self.client.get("/api/provider-settings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "llm_provider": "openai_compatible",
                "openai_base_url": "http://127.0.0.1:8317/v1",
                "openai_model": "gpt-5.4",
                "has_openai_api_key": True,
                "openai_api_key_masked": "********",
            },
        )

    async def test_provider_settings_endpoint_updates_env_file(self) -> None:
        response = await self.client.put(
            "/api/provider-settings",
            json={
                "llm_provider": "openai_compatible",
                "openai_base_url": "https://api.openai.com/v1",
                "openai_model": "gpt-5.4",
                "openai_api_key": "next-key",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["has_openai_api_key"])
        self.assertEqual(response.json()["openai_api_key_masked"], "********")
        env_text = (self.root / ".env").read_text(encoding="utf-8")
        self.assertIn("OPENAI_BASE_URL=https://api.openai.com/v1", env_text)
        self.assertIn("OPENAI_MODEL=gpt-5.4", env_text)
        self.assertIn("OPENAI_API_KEY=next-key", env_text)

    async def test_provider_settings_endpoint_keeps_existing_api_key_when_request_omits_it(self) -> None:
        response = await self.client.put(
            "/api/provider-settings",
            json={
                "llm_provider": "openai_compatible",
                "openai_base_url": "https://api.openai.com/v1",
                "openai_model": "gpt-5.4",
                "openai_api_key": None,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["has_openai_api_key"])
        self.assertEqual(response.json()["openai_api_key_masked"], "********")
        env_text = (self.root / ".env").read_text(encoding="utf-8")
        self.assertIn("OPENAI_BASE_URL=https://api.openai.com/v1", env_text)
        self.assertIn("OPENAI_API_KEY=test-key", env_text)

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

    async def test_faster_whisper_model_download_progress_endpoint_returns_completed_snapshot(self) -> None:
        response = await self.client.post("/api/asr/faster-whisper/models/medium/download")

        self.assertEqual(response.status_code, 200)

        progress_response = await self.client.get("/api/asr/faster-whisper/models/medium/download/progress")

        self.assertEqual(progress_response.status_code, 200)
        self.assertIn('"status": "completed"', progress_response.text)

    async def test_faster_whisper_model_download_cancel_endpoint_marks_task_cancelled(self) -> None:
        response = await self.client.post("/api/asr/faster-whisper/models/medium/download/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")

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

    async def test_summary_endpoint_rejects_stale_workspace_output_when_source_video_is_missing(self) -> None:
        stale_dir = self.root / "workspace" / "series-a" / "ghost"
        stale_dir.mkdir(parents=True)
        (stale_dir / "summary.json").write_text(json.dumps({"title": "ghost"}), encoding="utf-8")

        response = await self.client.get("/api/videos/series-a/ghost/summary")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "video not found 'series-a/ghost'")

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
        self.assertFalse(payload["knowledge_cards"]["generated"])
        self.assertTrue(payload["mindmap"]["generated"])
        self.assertTrue(payload["notes"]["available"])
        self.assertTrue(payload["preview"]["available"])
        self.assertEqual(payload["preview"]["preview_url"], "/api/videos/series-a/advanced/preview")

    async def test_cards_endpoint_derives_cards_from_summary(self) -> None:
        response = await self.client.get("/api/videos/series-a/advanced/cards")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["series_id"], "series-a")
        self.assertEqual(payload["video_id"], "advanced")
        self.assertEqual(payload["cards"][0]["id"], "chapter-1")
        self.assertEqual(payload["cards"][0]["kind"], "chapter")

    async def test_generate_knowledge_cards_endpoint_creates_independent_knowledge_cards_file(self) -> None:
        response = await self.client.post("/api/videos/series-a/advanced/knowledge-cards/generate")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["series_id"], "series-a")
        self.assertEqual(payload["video_id"], "advanced")
        self.assertEqual(payload["cards"][0]["kind"], "concept")
        self.assertIn("source_refs", payload["cards"][0])
        self.assertTrue((self.root / "workspace" / "series-a" / "advanced" / "knowledge_cards.json").exists())

    async def test_generate_knowledge_cards_endpoint_does_not_write_when_video_source_is_missing(self) -> None:
        stale_dir = self.root / "workspace" / "series-a" / "ghost"
        stale_dir.mkdir(parents=True)
        (stale_dir / "summary.json").write_text(
            json.dumps({"title": "ghost", "chapters": [], "key_takeaways": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        response = await self.client.post("/api/videos/series-a/ghost/knowledge-cards/generate")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "video not found 'series-a/ghost'")
        self.assertFalse((stale_dir / "knowledge_cards.json").exists())

    async def test_knowledge_cards_endpoint_returns_404_before_generation(self) -> None:
        response = await self.client.get("/api/videos/series-a/advanced/knowledge-cards")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "knowledge cards not found for video 'series-a/advanced'")

    async def test_notes_crud_endpoints_persist_notes(self) -> None:
        create_response = await self.client.post(
            "/api/videos/series-a/advanced/notes",
            json={
                "title": "准备工作",
                "content": "记下 API Key 申请是前置步骤。",
                "source": "manual",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        created_note = create_response.json()
        note_id = created_note["id"]
        self.assertEqual(created_note["title"], "准备工作")
        self.assertEqual(created_note["source"], "manual")

        list_response = await self.client.get("/api/videos/series-a/advanced/notes")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["notes"]), 1)

        update_response = await self.client.put(
            f"/api/videos/series-a/advanced/notes/{note_id}",
            json={
                "title": "准备工作更新",
                "content": "API Key 申请和配额确认都要提前做。",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["title"], "准备工作更新")

        delete_response = await self.client.delete(f"/api/videos/series-a/advanced/notes/{note_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["status"], "deleted")

        final_list_response = await self.client.get("/api/videos/series-a/advanced/notes")
        self.assertEqual(final_list_response.status_code, 200)
        self.assertEqual(final_list_response.json()["notes"], [])

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

    async def test_agent_chat_endpoint_returns_tool_results(self) -> None:
        response = await self.client.post(
            "/api/agent/chat",
            json={
                "session_id": "video|series-a|advanced|overview",
                "message": "打开概况",
                "context": {
                    "scope_type": "video",
                    "series_id": "series-a",
                    "series_title": "series-a",
                    "video_id": "advanced",
                    "video_title": "advanced",
                    "selected_tool": "overview",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assistant_message"], "已收到：打开概况")
        self.assertEqual(payload["intent_type"], "open_tool")
        self.assertEqual(payload["scope_type"], "video")
        self.assertEqual(payload["tool_results"][0]["tool_name"], "open_overview")
        self.assertEqual(payload["tool_results"][0]["payload"]["selected_tool"], "overview")
        self.assertIsNotNone(self.fake_agent_service.last_context_override)
        self.assertEqual(self.fake_agent_service.last_context_override.selected_tool, "overview")
        self.assertEqual(self.fake_agent_service.last_context_override.video_id, "advanced")

    async def test_agent_chat_endpoint_returns_503_when_agent_is_not_configured(self) -> None:
        (self.root / ".env").write_text(
            "\n".join(
                [
                    "OPENAI_PROVIDER=openai_compatible",
                    "OPENAI_BASE_URL=http://127.0.0.1:8317/v1",
                    "OPENAI_MODEL=gpt-5.4",
                    "OPENAI_API_KEY=",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        api_module.CONTAINER = build_api_container(
            self.root,
            generator=FakeGenerator(),
            mindmap_generator=FakeMindmapGenerator(),
            faster_whisper_model_manager=FakeFasterWhisperModelManager(),
        )

        health_response = await self.client.get("/api/health")
        self.assertEqual(health_response.status_code, 200)

        response = await self.client.post(
            "/api/agent/chat",
            json={
                "session_id": "library",
                "message": "打开概况",
            },
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "缺少 API Key，无法调用 Agent 模型。")


if __name__ == "__main__":
    unittest.main()
