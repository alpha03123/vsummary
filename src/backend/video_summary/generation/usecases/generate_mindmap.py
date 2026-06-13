from __future__ import annotations

from pathlib import Path

from backend.video_summary.generation.ports import GenerationArtifactStore, MindmapGenerator


class GenerateMindmap:
    def __init__(self, generator: MindmapGenerator, artifact_store: GenerationArtifactStore) -> None:
        self._generator = generator
        self._artifact_store = artifact_store

    async def run(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
        output_dir: Path,
    ) -> dict[str, object]:
        mindmap = await self._generator.generate(
            title=title,
            duration_seconds=duration_seconds,
            summary_data=summary_data,
        )
        await self._artifact_store.save_mindmap(mindmap=mindmap, output_dir=output_dir)
        return mindmap
