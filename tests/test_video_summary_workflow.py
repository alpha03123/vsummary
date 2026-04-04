from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.video_summary.infrastructure import video_summary_workflow as workflow_module


class FakeUseCase:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path, object]] = []

    def run(self, video_path: Path, output_dir: Path, progress_reporter=None):
        self.calls.append((video_path, output_dir, progress_reporter))
        return {"title": video_path.stem}


class FakeApplication:
    def __init__(self, debug_mode: bool = False) -> None:
        self.use_case = FakeUseCase()
        self.settings = SimpleNamespace(debug=SimpleNamespace(mode=debug_mode))


class ConfiguredVideoSummaryWorkflowTests(unittest.TestCase):
    def test_reuses_loaded_application_when_signature_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True)
            (root / ".env").write_text(
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
            (config_dir / "settings.toml").write_text(
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
            workflow = workflow_module.ConfiguredVideoSummaryWorkflow(root)
            applications: list[FakeApplication] = []
            original_loader = workflow_module.load_video_summary_application

            def fake_loader(**kwargs):
                application = FakeApplication()
                applications.append(application)
                return application

            workflow_module.load_video_summary_application = fake_loader
            try:
                first = workflow.run(root / "videos" / "a.mp4", root / "workspace" / "a")
                second = workflow.run(root / "videos" / "b.mp4", root / "workspace" / "b")
            finally:
                workflow_module.load_video_summary_application = original_loader

            self.assertEqual(len(applications), 1)
            self.assertEqual(first["title"], "a")
            self.assertEqual(second["title"], "b")

    def test_writes_debug_log_when_debug_mode_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True)
            (root / ".env").write_text(
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
            (config_dir / "settings.toml").write_text(
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

[debug]
mode = true
                """.strip(),
                encoding="utf-8",
            )
            workflow = workflow_module.ConfiguredVideoSummaryWorkflow(root)
            original_loader = workflow_module.load_video_summary_application

            class FakeReporter:
                def update(self, stage, progress=None, detail=None):
                    return None

                def completed(self, detail=None):
                    return None

                def failed(self, message):
                    return None

                def is_cancel_requested(self):
                    return False

                def raise_if_cancelled(self):
                    return None

                def cancelled(self, detail=None):
                    return None

            def fake_loader(**kwargs):
                application = FakeApplication(debug_mode=True)

                def run(video_path: Path, output_dir: Path, progress_reporter=None):
                    progress_reporter.update("extract_audio", 15.0, "正在将视频转换为音频")
                    progress_reporter.update("transcribe", 60.0, "Whisper 正在转写音频")
                    progress_reporter.completed("AI 概况已生成")
                    return {"title": video_path.stem}

                application.use_case.run = run
                return application

            workflow_module.load_video_summary_application = fake_loader
            try:
                output_dir = root / "workspace" / "demo"
                workflow.run(root / "videos" / "demo.mp4", output_dir, progress_reporter=FakeReporter())
            finally:
                workflow_module.load_video_summary_application = original_loader

            log_text = (output_dir / "debug.log").read_text(encoding="utf-8")
            self.assertIn('"event": "run_started"', log_text)
            self.assertIn('"event": "stage_started"', log_text)
            self.assertIn('"event": "stage_completed"', log_text)
            self.assertIn('"event": "run_completed"', log_text)


if __name__ == "__main__":
    unittest.main()
