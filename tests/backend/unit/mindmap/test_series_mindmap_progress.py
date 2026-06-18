from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from backend.video_summary.generation.usecases.generate_series_mindmap import GenerateSeriesMindmap


class StubProgressReporter:
    def __init__(self):
        self.updates = []
        self._completed_called = False
        self._failed_called = False
        self._failed_message = None

    def update(self, stage, progress=None, detail=None):
        self.updates.append({"stage": stage, "progress": progress, "detail": detail})

    def completed(self, detail=None):
        self._completed_called = True

    def failed(self, message):
        self._failed_called = True
        self._failed_message = message

    def is_cancel_requested(self):
        return False

    def raise_if_cancelled(self):
        pass


class FakeSeriesMindmapGenerator:
    async def generate(self, *, series_title, catalog, video_summaries):
        return {"id": "root", "title": series_title, "children": []}


class FakeSeriesArtifactStore:
    async def save_mindmap(self, *, mindmap, output_dir):
        pass


class GenerateSeriesMindmapProgressTests(unittest.TestCase):
    def test_reports_progress_stages(self):
        reporter = StubProgressReporter()
        use_case = GenerateSeriesMindmap(
            generator=FakeSeriesMindmapGenerator(),
            artifact_store=FakeSeriesArtifactStore(),
        )
        asyncio.run(use_case.run(
            series_title="ML Course",
            catalog={"series_title": "ML Course", "videos": []},
            video_summaries=[{"title": "V1"}],
            output_dir=Path("/tmp/test"),
            progress_reporter=reporter,
        ))
        stages = [u["stage"] for u in reporter.updates]
        self.assertIn("generate", stages)
        self.assertIn("save", stages)
        self.assertTrue(reporter._completed_called)

    def test_calls_completed_on_success(self):
        reporter = StubProgressReporter()
        use_case = GenerateSeriesMindmap(
            generator=FakeSeriesMindmapGenerator(),
            artifact_store=FakeSeriesArtifactStore(),
        )
        asyncio.run(use_case.run(
            series_title="ML",
            catalog=None,
            video_summaries=[],
            output_dir=Path("/tmp/test"),
            progress_reporter=reporter,
        ))
        self.assertTrue(reporter._completed_called)

    def test_works_without_reporter(self):
        use_case = GenerateSeriesMindmap(
            generator=FakeSeriesMindmapGenerator(),
            artifact_store=FakeSeriesArtifactStore(),
        )
        result = asyncio.run(use_case.run(
            series_title="ML", catalog=None, video_summaries=[],
            output_dir=Path("/tmp/test"),
        ))
        self.assertEqual(result["title"], "ML")


if __name__ == "__main__":
    unittest.main()