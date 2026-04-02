from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.video_summary.domain.models import SummaryDocument, Transcript, TranscriptSegment, VideoAsset
from backend.video_summary.generation.usecases.generate_summary import GenerateVideoSummary


class FakeMediaProcessor:
    def __init__(self) -> None:
        self.extracted_audio_paths: list[Path] = []

    def probe_duration(self, video_path: Path) -> float:
        return 12.5

    def extract_audio(self, video_path: Path, audio_path: Path) -> Path:
        audio_path.write_text("audio", encoding="utf-8")
        self.extracted_audio_paths.append(audio_path)
        return audio_path


class FakeTranscriber:
    def __init__(self) -> None:
        self.output_stems: list[Path] = []

    def transcribe(self, audio_path: Path, output_stem: Path) -> Transcript:
        self.output_stems.append(output_stem)
        return Transcript(
            language="zh",
            segments=[
                TranscriptSegment(start_seconds=0.0, end_seconds=2.0, text="第一段"),
                TranscriptSegment(start_seconds=2.0, end_seconds=4.0, text="第二段"),
            ],
        )


class FakeSummarizer:
    def __init__(self) -> None:
        self.last_video: VideoAsset | None = None
        self.last_transcript: Transcript | None = None
        self.last_output_dir: Path | None = None

    def summarize(self, video: VideoAsset, transcript: Transcript, output_dir: Path) -> SummaryDocument:
        self.last_video = video
        self.last_transcript = transcript
        self.last_output_dir = output_dir
        return SummaryDocument(
            markdown="# Summary",
            summary_data={"title": video.title},
            mindmap_data={"id": "root"},
        )


class GenerateVideoSummaryTests(unittest.TestCase):
    def test_run_writes_cleaned_transcript_and_returns_summary(self) -> None:
        media_processor = FakeMediaProcessor()
        transcriber = FakeTranscriber()
        summarizer = FakeSummarizer()
        use_case = GenerateVideoSummary(
            media_processor=media_processor,
            transcriber=transcriber,
            summarizer=summarizer,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "demo.mp4"
            video_path.write_text("video", encoding="utf-8")
            output_dir = root / "output"

            result = use_case.run(video_path=video_path, output_dir=output_dir)

            self.assertEqual(result.markdown, "# Summary")
            self.assertEqual(media_processor.extracted_audio_paths, [output_dir / "audio.wav"])
            self.assertEqual(transcriber.output_stems, [output_dir / "transcript"])
            self.assertIsNotNone(summarizer.last_video)
            self.assertEqual(summarizer.last_video.title, "demo")
            self.assertEqual(summarizer.last_video.duration_seconds, 12.5)
            self.assertEqual(summarizer.last_output_dir, output_dir)

            transcript_payload = json.loads((output_dir / "transcript.cleaned.json").read_text(encoding="utf-8"))
            self.assertEqual(transcript_payload["title"], "demo")
            self.assertEqual(transcript_payload["language"], "zh")
            self.assertEqual(transcript_payload["duration_seconds"], 12.5)
            self.assertEqual(
                transcript_payload["segments"],
                [
                    {"start_seconds": 0.0, "end_seconds": 2.0, "text": "第一段"},
                    {"start_seconds": 2.0, "end_seconds": 4.0, "text": "第二段"},
                ],
            )


if __name__ == "__main__":
    unittest.main()
