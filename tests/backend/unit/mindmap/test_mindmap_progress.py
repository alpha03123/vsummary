from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from backend.video_summary.generation.usecases.generate_mindmap import GenerateMindmap


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


class FakeMindmapGenerator:
    async def generate(self, *, title, duration_seconds, summary_data, transcript_text=""):
        return {"id": "root", "title": title, "children": []}


class FakeGenerationArtifactStore:
    def __init__(self, fail_on_save=False):
        self._saved = None
        self._fail_on_save = fail_on_save

    async def save_mindmap(self, *, mindmap, output_dir):
        if self._fail_on_save:
            raise IOError("disk full")
        self._saved = mindmap


class GenerateMindmapProgressTests(unittest.TestCase):
    def test_reports_progress_stages(self):
        reporter = StubProgressReporter()
        use_case = GenerateMindmap(
            generator=FakeMindmapGenerator(),
            artifact_store=FakeGenerationArtifactStore(),
        )
        asyncio.run(
            use_case.run(
                title="Test",
                duration_seconds=300.0,
                summary_data={"chapters": []},
                output_dir=Path("/tmp/test"),
                progress_reporter=reporter,
            )
        )
        stages = [u["stage"] for u in reporter.updates]
        self.assertIn("generate", stages)
        self.assertIn("save", stages)
        self.assertTrue(reporter._completed_called)

    def test_calls_completed_on_success(self):
        reporter = StubProgressReporter()
        use_case = GenerateMindmap(
            generator=FakeMindmapGenerator(),
            artifact_store=FakeGenerationArtifactStore(),
        )
        asyncio.run(
            use_case.run(
                title="Test", duration_seconds=300.0,
                summary_data={"chapters": []}, output_dir=Path("/tmp/test"),
                progress_reporter=reporter,
            )
        )
        self.assertTrue(reporter._completed_called)

    def test_propagates_generator_error_without_calling_failed(self):
        reporter = StubProgressReporter()
        class FailingGenerator:
            async def generate(self, **kwargs):
                raise RuntimeError("LLM connection failed")
        use_case = GenerateMindmap(
            generator=FailingGenerator(),
            artifact_store=FakeGenerationArtifactStore(),
        )
        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(
                use_case.run(
                    title="Test", duration_seconds=300.0,
                    summary_data={"chapters": []}, output_dir=Path("/tmp/test"),
                    progress_reporter=reporter,
                )
            )
        self.assertIn("LLM connection failed", str(ctx.exception))
        self.assertFalse(reporter._completed_called)
        # Note: use-case does NOT call reporter.failed() — the API route is
        # responsible for invoking failed() on the reporter when it catches
        # the propagated exception. Verifying failed() here would couple the
        # use-case to error-routing logic that lives upstream.

    def test_propagates_save_error_without_calling_failed(self):
        reporter = StubProgressReporter()
        use_case = GenerateMindmap(
            generator=FakeMindmapGenerator(),
            artifact_store=FakeGenerationArtifactStore(fail_on_save=True),
        )
        with self.assertRaises(IOError):
            asyncio.run(
                use_case.run(
                    title="Test", duration_seconds=300.0,
                    summary_data={"chapters": []}, output_dir=Path("/tmp/test"),
                    progress_reporter=reporter,
                )
            )
        self.assertFalse(reporter._completed_called)
        # Note: use-case does NOT call reporter.failed() — see comment above.

    def test_works_without_reporter(self):
        use_case = GenerateMindmap(
            generator=FakeMindmapGenerator(),
            artifact_store=FakeGenerationArtifactStore(),
        )
        result = asyncio.run(
            use_case.run(
                title="Test", duration_seconds=300.0,
                summary_data={"chapters": []}, output_dir=Path("/tmp/test"),
            )
        )
        self.assertEqual(result["title"], "Test")


if __name__ == "__main__":
    unittest.main()