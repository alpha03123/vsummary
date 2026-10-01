from __future__ import annotations

import unittest
from pathlib import Path
from tests._api_fixtures import make_api_container, make_workspace_services, mock_service
from backend.video_summary.library.models import VideoSourceDTO
from backend.video_summary.library.usecases import GetVideoSource, GetVideoTranscript

from fastapi.testclient import TestClient

from backend.local.http.app import create_app
from backend.video_summary.library.models import TranscriptSegmentDTO, VideoTranscriptDTO


class SubtitleWebVttApiTests(unittest.TestCase):
    def test_renders_current_transcript_as_webvtt(self) -> None:
        client = TestClient(create_app(_build_container(_transcript())))

        response = client.get("/api/videos/series-1/video-1/subtitles.vtt")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/vtt", response.headers["content-type"])
        self.assertEqual(
            response.text,
            "WEBVTT\n\n00:00:00.200 --> 00:00:07.977\n第一句 &amp; 第二句\n"
            "\n00:01:05.000 --> 01:01:01.250\n第二句\n",
        )

    def test_returns_not_found_without_a_current_transcript(self) -> None:
        client = TestClient(create_app(_build_container(None)))

        response = client.get("/api/videos/series-1/video-1/subtitles.vtt")

        self.assertEqual(response.status_code, 404)


def _transcript() -> VideoTranscriptDTO:
    return VideoTranscriptDTO(
        series_id="series-1",
        video_id="video-1",
        title="第一讲",
        duration_seconds=3661.25,
        segments=[
            TranscriptSegmentDTO(start_seconds=0.2, end_seconds=7.977, text="第一句 & 第二句"),
            TranscriptSegmentDTO(start_seconds=65, end_seconds=3661.25, text="第二句"),
        ],
    )


def _build_container(transcript: VideoTranscriptDTO | None):
    source = VideoSourceDTO(series_id="series-1", video_id="video-1", title="第一讲", source_name="video.mp4",
                            source_path=Path("video.mp4"), output_dir=Path("transcript"), processed=True)
    return make_api_container(services=make_workspace_services(
        get_video_source=mock_service(GetVideoSource, run=source),
        get_video_transcript=mock_service(GetVideoTranscript, run=transcript),
    ))


if __name__ == "__main__":
    unittest.main()
