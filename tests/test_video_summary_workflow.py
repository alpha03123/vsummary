from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

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
    def __init__(self) -> None:
        self.use_case = FakeUseCase()


class ConfiguredVideoSummaryWorkflowTests(unittest.TestCase):
    def test_reuses_loaded_application_when_signature_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True)
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

[openai]
provider = "openai_compatible"
base_url = "http://127.0.0.1:8317/v1/responses"
model = "gpt-5.4"
api_key = "test-key"
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


if __name__ == "__main__":
    unittest.main()
