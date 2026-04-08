from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.infrastructure.chat_gateway import LiteLLMChatGateway
from backend.agent.schemas.messages import AgentChatMessage
from backend.api.bootstrap import build_api_container
from backend.video_summary.infrastructure.faster_whisper_models import FasterWhisperModelInfo
from backend.video_summary.domain.models import SummaryDocument


class FakeGenerator:
    async def run(
        self,
        source_path: Path,
        output_dir: Path,
        progress_reporter=None,
        transcript_enhancement_enabled=None,
    ) -> SummaryDocument:
        del source_path, progress_reporter, transcript_enhancement_enabled
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "title": "intro",
            "one_sentence_summary": "generated",
            "chapters": [],
            "key_takeaways": [],
        }
        (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return SummaryDocument(markdown="# generated", summary_data=payload)


class FakeMindmapGenerator:
    async def run(self, source_path: Path, output_dir: Path, summary_data: dict[str, object]) -> dict[str, object]:
        del source_path, summary_data
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = {"id": "root", "title": "intro", "summary": "", "start_seconds": 0, "end_seconds": 0, "children": []}
        (output_dir / "mindmap.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload


class FakeFasterWhisperModelManager:
    def is_supported(self, model_size: str) -> bool:
        return model_size in {"small", "medium", "large-v3", "large-v3-turbo"}

    def list_models(self, current_model_size: str) -> list[FasterWhisperModelInfo]:
        return [
            FasterWhisperModelInfo(
                id=current_model_size,
                label=current_model_size,
                downloaded=True,
                current=True,
                recommended=True,
            )
        ]

    def download(self, model_size: str, progress_reporter=None):
        del progress_reporter
        return model_size


def main() -> int:
    _probe_gateway_sync()
    _probe_gateway_stream()
    _probe_structured_fail_fast()
    _probe_context_budget_bootstrap()
    return 0


def _probe_gateway_sync() -> None:
    captured_calls: list[dict[str, object]] = []

    def fake_completion(**kwargs):
        captured_calls.append(kwargs)
        return {"choices": [{"message": {"content": "sync-ok"}}]}

    gateway = LiteLLMChatGateway(
        provider="openai_compatible",
        model="gpt-5.4",
        base_url="https://example.com/v1",
        api_key="test-key",
        completion_fn=fake_completion,
    )
    output = gateway.create_text_completion([AgentChatMessage(role="user", content="hello")])
    print("=== provider-sync ===")
    print(f"output: {output}")
    print(f"normalized_model: {captured_calls[0]['model']}")
    print()


def _probe_gateway_stream() -> None:
    def fake_completion(**kwargs):
        del kwargs
        return iter(
            [
                {"choices": [{"delta": {"content": "stream"}}]},
                {"choices": [{"delta": {"content": "-ok"}}]},
            ]
        )

    gateway = LiteLLMChatGateway(
        provider="openai_compatible",
        model="gpt-5.4",
        base_url="https://example.com/v1",
        api_key="test-key",
        completion_fn=fake_completion,
    )
    output = "".join(gateway.create_text_completion_stream([AgentChatMessage(role="user", content="hello")]))
    print("=== provider-stream ===")
    print(f"output: {output}")
    print()


def _probe_structured_fail_fast() -> None:
    gateway = LiteLLMChatGateway(
        provider="openai_compatible",
        model="gpt-5.4",
        base_url="https://example.com/v1",
        api_key="test-key",
        completion_fn=lambda **kwargs: kwargs,
    )
    print("=== provider-structured ===")
    try:
        gateway.create_structured_completion([], dict)  # type: ignore[arg-type]
    except RuntimeError as error:
        print(f"expected_error: {error}")
    print()


def _probe_context_budget_bootstrap() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "videos" / "series-a").mkdir(parents=True)
        (root / "workspace").mkdir(parents=True)
        (root / "config").mkdir(parents=True)
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
        (root / "config" / "settings.toml").write_text(
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
""".strip(),
            encoding="utf-8",
        )
        container = build_api_container(
            root,
            generator=FakeGenerator(),
            mindmap_generator=FakeMindmapGenerator(),
            faster_whisper_model_manager=FakeFasterWhisperModelManager(),
        )
        budget_service = container.get_agent_context_usage()
        print("=== provider-budget-service ===")
        print(f"service_type: {budget_service.__class__.__name__}")
        print("note: context usage can bootstrap without instantiating the gateway")
        print()


if __name__ == "__main__":
    raise SystemExit(main())
