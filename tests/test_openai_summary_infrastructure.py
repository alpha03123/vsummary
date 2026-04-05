from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.openai_summary.client import OpenAIResponsesGateway
from backend.video_summary.infrastructure.openai_summary.parsers import extract_json_block
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
    def test_gateway_retries_on_transient_status_and_returns_output_text(self) -> None:
        responses = iter(
            [
                httpx.Response(502, request=httpx.Request("POST", "https://example.com/v1/responses"), text="bad gateway"),
                httpx.Response(200, request=httpx.Request("POST", "https://example.com/v1/responses"), json={"output_text": "final answer"}),
            ]
        )
        transport = httpx.MockTransport(lambda request: next(responses))
        gateway = OpenAIResponsesGateway(
            model="gpt-5.4",
            base_url="https://example.com/v1/responses",
            api_key="test-key",
            transport=transport,
        )

        result = asyncio.run(gateway.create_text("hello"))

        self.assertEqual(result, "final answer")

    def test_extract_json_block_ignores_non_json_braces_before_payload(self) -> None:
        payload = extract_json_block(
            '<think>先看看这个例子 {"noise": true}</think>\n最终答案：{"title":"demo","chapters":[],"key_takeaways":[]}'
        )

        self.assertEqual(payload["title"], "demo")

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
