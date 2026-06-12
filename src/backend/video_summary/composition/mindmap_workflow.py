from __future__ import annotations

from pathlib import Path
from threading import Lock

from backend.video_summary.composition.application_builders import build_mindmap_application


class ConfiguredMindmapWorkflow:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._config_path = root_dir / "config" / "settings.toml"
        self._dotenv_path = root_dir / ".env"
        self._application_lock = Lock()
        self._cached_signature: tuple[str, str] | None = None
        self._cached_application = None

    async def run(self, source_path: Path, output_dir: Path, summary_data: dict[str, object]) -> None:
        application = self._get_application()
        await application.use_case.run(
            title=source_path.stem,
            duration_seconds=_resolve_duration_seconds(summary_data),
            summary_data=summary_data,
            output_dir=output_dir,
        )

    def _get_application(self):
        signature = (
            self._config_path.read_text(encoding="utf-8"),
            self._dotenv_path.read_text(encoding="utf-8") if self._dotenv_path.exists() else "",
        )
        with self._application_lock:
            if self._cached_application is None or self._cached_signature != signature:
                self._cached_application = build_mindmap_application(
                    config_path=self._config_path,
                    root_dir=self._root_dir,
                )
                self._cached_signature = signature
            return self._cached_application


def _resolve_duration_seconds(summary_data: dict[str, object]) -> float:
    chapters = summary_data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return 0.0
    chapter = chapters[-1]
    if not isinstance(chapter, dict):
        return 0.0
    end_seconds = chapter.get("end_seconds", 0.0)
    return float(end_seconds or 0.0)
