from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.settings import (
    AgentContextSettings,
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
from backend.video_summary.infrastructure.structured_generation.schemas import SummaryPayload


async def _async_return(value):
    return value


class LiteLLMVideoSummaryInfrastructureTests(unittest.TestCase):
    def test_gateway_returns_text_from_async_completion(self) -> None:
        gateway = LiteLLMCompletionGateway(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            completion_fn=lambda **kwargs: {"choices": [{"message": {"content": "unused"}}]},
            acompletion_fn=lambda **kwargs: _async_return(
                {"choices": [{"message": {"content": "final answer"}}]}
            ),
        )

        result = asyncio.run(
            gateway.acomplete_text([{"role": "user", "content": "hello"}])
        )

        self.assertEqual(result, "final answer")

    def test_gateway_async_text_falls_back_to_stream_when_content_is_empty(self) -> None:
        class FakeAsyncStream:
            def __init__(self, chunks):
                self._chunks = iter(chunks)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._chunks)
                except StopIteration as error:
                    raise StopAsyncIteration from error

        async def fake_acompletion(**kwargs):
            if kwargs.get("stream"):
                return FakeAsyncStream(
                    [
                        {"choices": [{"delta": {"content": "回退"}}]},
                        {"choices": [{"delta": {"content": "成功"}}]},
                    ]
                )
            return {"choices": [{"message": {"content": None}}]}

        gateway = LiteLLMCompletionGateway(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            completion_fn=lambda **kwargs: {"choices": [{"message": {"content": "unused"}}]},
            acompletion_fn=fake_acompletion,
        )

        result = asyncio.run(
            gateway.acomplete_text([{"role": "user", "content": "hello"}])
        )

        self.assertEqual(result, "回退成功")

    def test_gateway_returns_structured_payload_from_json_completion(self) -> None:
        gateway = LiteLLMCompletionGateway(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            completion_fn=lambda **kwargs: {"choices": [{"message": {"content": "unused"}}]},
            acompletion_fn=lambda **kwargs: _async_return(
                {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"title":"demo","one_sentence_summary":"一句话","core_problem":"问题","chapters":[],"key_takeaways":["结论"]}'
                                )
                            }
                        }
                    ]
                }
            ),
        )

        payload = asyncio.run(
            gateway.acomplete_structured(
                [{"role": "user", "content": "提取视频摘要"}],
                response_model=SummaryPayload,
            )
        )

        self.assertEqual(payload.title, "demo")
        self.assertEqual(payload.key_takeaways, ["结论"])

    def test_gateway_retries_structured_payload_after_validation_error(self) -> None:
        call_count = 0

        async def fake_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"choices": [{"message": {"content": '{"wrong":"field"}'}}]}
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"title":"demo","one_sentence_summary":"一句话","core_problem":"问题","chapters":[],"key_takeaways":["结论"]}'
                            )
                        }
                    }
                ]
            }

        gateway = LiteLLMCompletionGateway(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            completion_fn=lambda **kwargs: {"choices": [{"message": {"content": "unused"}}]},
            acompletion_fn=fake_acompletion,
        )

        payload = asyncio.run(
            gateway.acomplete_structured(
                [{"role": "user", "content": "提取视频摘要"}],
                response_model=SummaryPayload,
            )
        )

        self.assertEqual(call_count, 2)
        self.assertEqual(payload.title, "demo")

    def test_gateway_extracts_structured_payload_from_tool_calls(self) -> None:
        gateway = LiteLLMCompletionGateway(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com/v1",
            api_key="test-key",
            completion_fn=lambda **kwargs: {"choices": [{"message": {"content": "unused"}}]},
            acompletion_fn=lambda **kwargs: _async_return(
                {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "json_tool_call",
                                            "arguments": '{"title":"demo","one_sentence_summary":"一句话","core_problem":"问题","chapters":[],"key_takeaways":["结论"]}',
                                        }
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
        )

        payload = asyncio.run(
            gateway.acomplete_structured(
                [{"role": "user", "content": "提取视频摘要"}],
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
            agent_context=AgentContextSettings(
                window_tokens=1_000_000,
                reserved_output_tokens=20_000,
                warning_threshold_ratio=0.60,
                compact_threshold_ratio=0.80,
                blocking_threshold_ratio=0.92,
                keep_tail_messages=6,
                projection_max_tokens_ratio=0.08,
            ),
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
