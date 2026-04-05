from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.openai_summary.client import OpenAICompletionGateway
from backend.video_summary.infrastructure.openai_summary.schemas import SummaryPayload
from backend.video_summary.infrastructure.settings import (
    AppSettings,
    AsrSettings,
    DebugSettings,
    FasterWhisperSettings,
    OpenAISettings,
    WorkspaceUiSettings,
    replace_faster_whisper_model_size,
    replace_faster_whisper_transcription_mode,
    replace_transcript_enhancement_enabled,
    replace_workspace_ui_settings,
)


class OpenAISummaryInfrastructureTests(unittest.TestCase):
    def test_gateway_returns_text_from_chat_completion(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(str(request.url), "https://example.com/v1/chat/completions")
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "final answer",
                            }
                        }
                    ]
                },
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        gateway = OpenAICompletionGateway(
            model="gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            http_client=http_client,
        )

        result = asyncio.run(gateway.create_text("hello"))

        self.assertEqual(result, "final answer")

    def test_gateway_returns_structured_payload_from_instructor_client(self) -> None:
        gateway = OpenAICompletionGateway(
            model="gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request))),
        )
        gateway._structured_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: _return_async(
                        SummaryPayload(
                            title="demo",
                            one_sentence_summary="一句话",
                            core_problem="问题",
                            chapters=[],
                            key_takeaways=["结论"],
                        )
                    )
                )
            )
        )

        payload = asyncio.run(
            gateway.create_structured_completion(
                prompt="提取视频摘要",
                response_model=SummaryPayload,
            )
        )

        self.assertEqual(payload.title, "demo")

    def test_settings_replace_helpers_preserve_other_fields(self) -> None:
        settings = AppSettings(
            asr=AsrSettings(
                provider="faster_whisper",
                language="zh",
                transcript_enhancement_enabled=True,
                faster_whisper=FasterWhisperSettings(
                    device="auto",
                    model_size="small",
                    compute_type="int8",
                    transcription_mode="fast",
                    models_dir=Path("models"),
                ),
            ),
            openai=OpenAISettings(
                provider="openai_compatible",
                base_url="https://api.openai.com/v1",
                model="gpt-5.4",
                api_key="secret",
            ),
            workspace_ui=WorkspaceUiSettings(theme="light", show_takeaways=True),
            debug=DebugSettings(mode=False),
        )

        next_settings = replace_workspace_ui_settings(
            settings,
            WorkspaceUiSettings(theme="dark", show_takeaways=False),
        )
        next_settings = replace_transcript_enhancement_enabled(next_settings, False)
        next_settings = replace_faster_whisper_model_size(next_settings, "large-v3")
        next_settings = replace_faster_whisper_transcription_mode(next_settings, "accurate")

        self.assertEqual(next_settings.workspace_ui.theme, "dark")
        self.assertFalse(next_settings.workspace_ui.show_takeaways)
        self.assertFalse(next_settings.asr.transcript_enhancement_enabled)
        self.assertEqual(next_settings.asr.faster_whisper.model_size, "large-v3")
        self.assertEqual(next_settings.asr.faster_whisper.transcription_mode, "accurate")
        self.assertEqual(next_settings.openai.api_key, "secret")

    def test_mindmap_workflow_uses_bootstrap_loader(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir(parents=True)
            (root / "config" / "settings.toml").write_text(
                """
[asr]
provider = "faster_whisper"
language = "zh"
transcript_enhancement_enabled = true

[asr.faster_whisper]
device = "auto"
model_size = "small"
compute_type = "int8"
transcription_mode = "fast"
                """.strip(),
                encoding="utf-8",
            )
            (root / ".env").write_text(
                "\n".join(
                    [
                        "OPENAI_PROVIDER=openai_compatible",
                        "OPENAI_BASE_URL=https://example.com/v1",
                        "OPENAI_MODEL=gpt-5.4",
                        "OPENAI_API_KEY=test-key",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            workflow = ConfiguredMindmapWorkflow(root)
            import backend.video_summary.infrastructure.mindmap_workflow as workflow_module

            captured: list[tuple[str, float]] = []
            original_loader = workflow_module.load_mindmap_application

            class FakeUseCase:
                async def run(self, *, title: str, duration_seconds: float, summary_data: dict[str, object], output_dir: Path):
                    captured.append((title, duration_seconds))
                    return {"id": "root", "title": title, "summary": "", "start_seconds": 0.0, "end_seconds": duration_seconds, "children": []}

            class FakeApplication:
                use_case = FakeUseCase()

            workflow_module.load_mindmap_application = lambda **kwargs: FakeApplication()
            try:
                result = asyncio.run(
                    workflow.run(
                        source_path=root / "videos" / "demo.mp4",
                        output_dir=root / "workspace" / "demo",
                        summary_data={"chapters": [{"end_seconds": 42.0}]},
                    )
                )
            finally:
                workflow_module.load_mindmap_application = original_loader

            self.assertEqual(result["title"], "demo")
            self.assertEqual(captured, [("demo", 42.0)])


if __name__ == "__main__":
    unittest.main()


async def _return_async(value):
    return value
