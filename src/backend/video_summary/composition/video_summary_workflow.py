from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from threading import Lock

from backend.video_summary.summary_generation.ports import ProgressReporter
from backend.video_summary.composition.application_builders import build_video_summary_application


class ConfiguredVideoSummaryWorkflow:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._config_path = root_dir / "config" / "settings.toml"
        self._dotenv_path = root_dir / ".env"
        self._application_lock = Lock()
        self._cached_signature: tuple[str, str, bool | None] | None = None
        self._cached_application = None

    async def run(
        self,
        source_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> None:
        application = self._get_application(transcript_enhancement_enabled)
        resolved_progress_reporter = progress_reporter
        if progress_reporter is not None and application.settings.debug.mode:
            resolved_progress_reporter = DebugFileProgressReporter(
                wrapped=progress_reporter,
                log_path=output_dir / "debug.log",
            )
        await application.use_case.run(
            video_path=source_path,
            output_dir=output_dir,
            progress_reporter=resolved_progress_reporter,
        )

    def _get_application(self, transcript_enhancement_enabled: bool | None):
        signature = (
            self._config_path.read_text(encoding="utf-8"),
            self._dotenv_path.read_text(encoding="utf-8") if self._dotenv_path.exists() else "",
            transcript_enhancement_enabled,
        )
        with self._application_lock:
            if self._cached_signature != signature or self._cached_application is None:
                self._cached_application = build_video_summary_application(
                    config_path=self._config_path,
                    root_dir=self._root_dir,
                    transcript_enhancement_enabled=transcript_enhancement_enabled,
                )
                self._cached_signature = signature
            return self._cached_application


class DebugFileProgressReporter:
    def __init__(self, wrapped: ProgressReporter, log_path: Path) -> None:
        self._wrapped = wrapped
        self._log_path = log_path
        self._started_at = time.perf_counter()
        self._current_stage: str | None = None
        self._current_stage_started_at: float | None = None
        self._log("run_started", detail="开始生成 AI 概况")

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        now = time.perf_counter()
        if stage != self._current_stage:
            self._log_stage_completed(now)
            self._current_stage = stage
            self._current_stage_started_at = now
            self._log(
                "stage_started",
                stage=stage,
                progress=progress,
                detail=detail,
                elapsed_seconds=now - self._started_at,
            )
        else:
            self._log(
                "stage_progress",
                stage=stage,
                progress=progress,
                detail=detail,
                elapsed_seconds=now - self._started_at,
                stage_elapsed_seconds=(
                    None if self._current_stage_started_at is None else now - self._current_stage_started_at
                ),
            )
        self._wrapped.update(stage, progress, detail)

    def completed(self, detail: str | None = None) -> None:
        now = time.perf_counter()
        self._log_stage_completed(now)
        self._log(
            "run_completed",
            detail=detail,
            elapsed_seconds=now - self._started_at,
        )
        self._wrapped.completed(detail)

    def failed(self, message: str) -> None:
        now = time.perf_counter()
        self._log_stage_completed(now)
        self._log(
            "run_failed",
            detail=message,
            elapsed_seconds=now - self._started_at,
        )
        self._wrapped.failed(message)

    def is_cancel_requested(self) -> bool:
        return self._wrapped.is_cancel_requested()

    def raise_if_cancelled(self) -> None:
        self._wrapped.raise_if_cancelled()

    def cancelled(self, detail: str | None = None) -> None:
        now = time.perf_counter()
        self._log_stage_completed(now)
        self._log(
            "run_cancelled",
            detail=detail,
            elapsed_seconds=now - self._started_at,
        )
        self._wrapped.cancelled(detail)

    def _log_stage_completed(self, now: float) -> None:
        if self._current_stage is None or self._current_stage_started_at is None:
            return
        self._log(
            "stage_completed",
            stage=self._current_stage,
            elapsed_seconds=now - self._started_at,
            stage_elapsed_seconds=now - self._current_stage_started_at,
        )
        self._current_stage = None
        self._current_stage_started_at = None

    def _log(
        self,
        event: str,
        *,
        stage: str | None = None,
        progress: float | None = None,
        detail: str | None = None,
        elapsed_seconds: float | None = None,
        stage_elapsed_seconds: float | None = None,
    ) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "stage": stage,
            "progress": progress,
            "detail": detail,
            "elapsed_seconds": _round_seconds(elapsed_seconds),
            "stage_elapsed_seconds": _round_seconds(stage_elapsed_seconds),
        }
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _round_seconds(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, value), 3)
