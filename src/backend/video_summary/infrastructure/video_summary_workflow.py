from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from backend.video_summary.bootstrap import load_video_summary_application
from backend.video_summary.domain.models import SummaryDocument
from backend.video_summary.generation.ports import ProgressReporter


class ConfiguredVideoSummaryWorkflow:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._config_path = root_dir / "config" / "settings.toml"
        self._application_lock = Lock()
        self._cached_signature: tuple[str, str | None, str | None, bool | None] | None = None
        self._cached_application = None

    def run(
        self,
        source_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> SummaryDocument:
        application = self._get_application(transcript_enhancement_enabled)
        return application.use_case.run(
            video_path=source_path,
            output_dir=output_dir,
            progress_reporter=progress_reporter,
        )

    def _get_application(self, transcript_enhancement_enabled: bool | None):
        base_url = os.environ.get("OPENAI_BASE_URL")
        model = os.environ.get("OPENAI_MODEL")
        signature = (
            self._config_path.read_text(encoding="utf-8"),
            base_url,
            model,
            transcript_enhancement_enabled,
        )
        with self._application_lock:
            if self._cached_signature != signature or self._cached_application is None:
                self._cached_application = load_video_summary_application(
                    config_path=self._config_path,
                    root_dir=self._root_dir,
                    base_url=base_url,
                    model=model,
                    transcript_enhancement_enabled=transcript_enhancement_enabled,
                )
                self._cached_signature = signature
            return self._cached_application
