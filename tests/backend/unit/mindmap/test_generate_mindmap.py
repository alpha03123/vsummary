from __future__ import annotations

import asyncio
import unittest

from backend.video_summary.library.models import (
    VideoSummaryDTO,
    WorkspaceDTO,
)
from backend.video_summary.library.usecases.mindmap_generation import GenerateVideoMindmapFromLibrary


class FakeWorkspaceForMindmap:
    def __init__(self, summary=None, transcript_text=None):
        self._summary = summary
        self._transcript_text = transcript_text
        self._mindmap = None

    def get_video_summary(self, series_id, video_id):
        return self._summary

    def get_video_transcript(self, series_id, video_id):
        if self._transcript_text is None:
            return None
        return _FakeTranscript(self._transcript_text)

    def get_video_source(self, series_id, video_id):
        return None

    def list_series(self):
        return []

    def get_workspace(self):
        return WorkspaceDTO(id="ws", title="ws")

    def get_video_mindmap(self, series_id, video_id):
        return self._mindmap


class _FakeSegment:
    def __init__(self, text):
        self.text = text


class _FakeTranscript:
    def __init__(self, text):
        self.segments = [_FakeSegment(text)]


class FakeMindmapGenerator:
    def __init__(self):
        self.last_call_args = None

    async def run(self, *, series_id, video_id, summary_data, transcript_text="", progress_reporter=None):
        self.last_call_args = {
            "series_id": series_id,
            "video_id": video_id,
            "summary_data": summary_data,
            "transcript_text": transcript_text,
            "progress_reporter": progress_reporter,
        }


class GenerateVideoMindmapTranscriptTests(unittest.TestCase):
    def test_passes_transcript_text_to_generator(self):
        generator = FakeMindmapGenerator()
        workspace = FakeWorkspaceForMindmap(
            summary=VideoSummaryDTO(
                series_id="s1", video_id="v1", title="Test", summary={"chapters": []}
            ),
            transcript_text="转写全文内容在这里",
        )
        use_case = GenerateVideoMindmapFromLibrary(workspace, generator)
        asyncio.run(use_case.run("s1", "v1"))
        self.assertEqual(generator.last_call_args["transcript_text"], "转写全文内容在这里")

    def test_passes_empty_string_when_transcript_is_none(self):
        generator = FakeMindmapGenerator()
        workspace = FakeWorkspaceForMindmap(
            summary=VideoSummaryDTO(
                series_id="s1", video_id="v1", title="Test", summary={"chapters": []}
            ),
            transcript_text=None,
        )
        use_case = GenerateVideoMindmapFromLibrary(workspace, generator)
        asyncio.run(use_case.run("s1", "v1"))
        self.assertEqual(generator.last_call_args["transcript_text"], "")

    def test_returns_none_when_summary_missing(self):
        generator = FakeMindmapGenerator()
        workspace = FakeWorkspaceForMindmap(summary=None)
        use_case = GenerateVideoMindmapFromLibrary(workspace, generator)
        result = asyncio.run(use_case.run("s1", "v1"))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
