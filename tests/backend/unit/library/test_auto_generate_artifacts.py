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

        workflow = AutoGenerateVideoArtifacts(
            load_enabled_artifacts=lambda: ("mindmap", "knowledge_cards"),
            generate_mindmap=generate_mindmap,
            generate_knowledge_cards=generate_cards,
        )

        asyncio.run(workflow.run("series-1", "video-1"))

        self.assertEqual(
            ["mindmap:series-1/video-1", "cards:series-1/video-1"],
            calls,
        )

    def test_waits_once_for_visual_evidence_shared_by_standard_visual_artifacts(self) -> None:
        calls: list[str] = []

        async def generate_mindmap(series_id: str, video_id: str) -> None:
            calls.append("mindmap")

        def generate_cards(series_id: str, video_id: str) -> None:
            calls.append("cards")

        async def wait_for_visual_evidence(series_id: str, video_id: str) -> None:
            calls.append(f"evidence:{series_id}/{video_id}")

        workflow = AutoGenerateVideoArtifacts(
            load_enabled_artifacts=lambda: ("mindmap", "knowledge_cards"),
            generate_mindmap=generate_mindmap,
            generate_knowledge_cards=generate_cards,
            requires_visual_evidence=lambda artifact: artifact in {"mindmap", "knowledge_cards"},
            wait_for_visual_evidence=wait_for_visual_evidence,
        )

        asyncio.run(workflow.run("series-1", "video-1"))

        self.assertEqual(["evidence:series-1/video-1", "mindmap", "cards"], calls)


if __name__ == "__main__":
    unittest.main()
