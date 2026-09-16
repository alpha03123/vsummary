from __future__ import annotations

import asyncio
import unittest

from backend.video_summary.library.usecases.auto_generate_artifacts import AutoGenerateVideoArtifacts


class AutoGenerateVideoArtifactsTests(unittest.TestCase):
    def test_runs_every_enabled_artifact(self) -> None:
        calls: list[str] = []

        async def generate_mindmap(series_id: str, video_id: str) -> None:
            calls.append(f"mindmap:{series_id}/{video_id}")

        def generate_cards(series_id: str, video_id: str) -> None:
            calls.append(f"cards:{series_id}/{video_id}")

        def generate_note(series_id: str, video_id: str) -> None:
            calls.append(f"notes:{series_id}/{video_id}")

        workflow = AutoGenerateVideoArtifacts(
            load_enabled_artifacts=lambda: ("mindmap", "knowledge_cards", "notes"),
            generate_mindmap=generate_mindmap,
            generate_knowledge_cards=generate_cards,
            generate_note=generate_note,
        )

        asyncio.run(workflow.run("series-1", "video-1"))

        self.assertEqual(
            ["mindmap:series-1/video-1", "cards:series-1/video-1", "notes:series-1/video-1"],
            calls,
        )


if __name__ == "__main__":
    unittest.main()
