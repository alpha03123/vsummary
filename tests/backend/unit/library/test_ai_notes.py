from __future__ import annotations

import unittest

from backend.video_summary.library.models import VideoNoteDTO, VideoSourceDTO, VideoTranscriptDTO, TranscriptSegmentDTO
from backend.video_summary.library.usecases.ai_notes import GenerateVideoAiNote


class FakeWorkspace:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []

    def get_video_source(self, series_id: str, video_id: str):
        return VideoSourceDTO(series_id, video_id, "第一讲", "first.mp4", None, None, True)

    def get_video_transcript(self, series_id: str, video_id: str):
        return VideoTranscriptDTO(series_id, video_id, "第一讲", 10.0, [
            TranscriptSegmentDTO(0, 10, "重要内容"),
        ])

    def get_video_summary(self, series_id: str, video_id: str):
        return None

    def create_video_note(self, series_id: str, video_id: str, *, title: str, content: str, source: str):
        self.created.append({"title": title, "content": content, "source": source})
        return VideoNoteDTO("note-1", title, content, source, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")


class FakeGenerator:
    def run(self, *, transcript, summary, template: str) -> str:
        self.template = template
        return "## 重点\n\n内容"


class GenerateVideoAiNoteTests(unittest.TestCase):
    def test_generates_and_saves_agent_note(self) -> None:
        workspace = FakeWorkspace()
        generator = FakeGenerator()

        note = GenerateVideoAiNote(workspace, generator).run("series-1", "video-1", template="tutorial")

        self.assertEqual("note-1", note.id)
        self.assertEqual("tutorial", generator.template)
        self.assertEqual(
            [{"title": "第一讲", "content": "## 重点\n\n内容", "source": "agent"}],
            workspace.created,
        )


if __name__ == "__main__":
    unittest.main()
