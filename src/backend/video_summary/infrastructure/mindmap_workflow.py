from __future__ import annotations

from pathlib import Path

from backend.video_summary.infrastructure.openai_mindmap_generator import OpenAIMindmapGenerator
from backend.video_summary.infrastructure.settings import load_settings


class ConfiguredMindmapWorkflow:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._config_path = root_dir / "config" / "settings.toml"

    def run(self, source_path: Path, output_dir: Path, summary_data: dict[str, object]) -> dict[str, object]:
        settings = load_settings(config_path=self._config_path, root_dir=self._root_dir)
        generator = OpenAIMindmapGenerator(
            model=settings.openai.model,
            base_url=settings.openai.base_url,
            api_key=settings.openai.api_key,
        )
        return generator.generate(
            title=source_path.stem,
            duration_seconds=_resolve_duration_seconds(summary_data),
            summary_data=summary_data,
            output_dir=output_dir,
        )


def _resolve_duration_seconds(summary_data: dict[str, object]) -> float:
    chapters = summary_data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return 0.0
    chapter = chapters[-1]
    if not isinstance(chapter, dict):
        return 0.0
    end_seconds = chapter.get("end_seconds", 0.0)
    return float(end_seconds or 0.0)
