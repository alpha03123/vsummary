from __future__ import annotations

import os
from pathlib import Path

from backend.video_summary.bootstrap import load_video_summary_application
from backend.video_summary.domain.models import SummaryDocument
from backend.video_summary.generation.ports import ProgressReporter


class ConfiguredVideoSummaryWorkflow:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._config_path = root_dir / "config" / "settings.toml"

    def run(
        self,
        source_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> SummaryDocument:
        application = load_video_summary_application(
            config_path=self._config_path,
            root_dir=self._root_dir,
            base_url=os.environ.get("OPENAI_BASE_URL"),
            model=os.environ.get("OPENAI_MODEL"),
            transcript_enhancement_enabled=transcript_enhancement_enabled,
        )
        return application.use_case.run(
            video_path=source_path,
            output_dir=output_dir,
            progress_reporter=progress_reporter,
        )
