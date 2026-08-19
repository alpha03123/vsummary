from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.video_summary.domain.models import ManualTranscriptInput, SummaryDocument, Transcript, TranscriptSegment
from backend.video_summary.generation.renderers import parse_markdown
from backend.video_summary.generation.usecases.generate_summary import GenerateVideoSummary
from backend.video_summary.infrastructure.storage.filesystem_generation_artifact_store import FileSystemGenerationArtifactStore
from backend.video_summary.infrastructure.subtitle_transcripts import ManualSrtTranscriptProvider, parse_srt_transcript


_SRT = """1
00:00:00,000 --> 00:00:02,000
人工字幕第一句

2
00:00:02,000 --> 00:00:04,000
人工字幕第二句
"""


class _UnexpectedMediaProcessor:
    def probe_duration(self, video_path: Path) -> float:
        raise AssertionError("人工 SRT 不应探测媒体")

    def extract_audio(self, video_path: Path, audio_path: Path, cancellation=None) -> Path:
        raise AssertionError("人工 SRT 不应抽取音频")


class _UnexpectedTranscriber:
    def transcribe(self, audio_path: Path, output_stem: Path, on_progress=None) -> Transcript:
        raise AssertionError("人工 SRT 不应调用 ASR")


class _UnexpectedSubtitleProvider:
    def load(self, video_path: Path, staging_dir: Path, cancellation=None) -> Transcript | None:
        raise AssertionError("人工 SRT 不应探测在线视频或内嵌字幕")


class _Summarizer:
    def __init__(self) -> None:
        self.transcripts: list[Transcript] = []

    async def summarize(self, video, transcript, cancellation=None) -> SummaryDocument:
        self.transcripts.append(transcript)
        return SummaryDocument(markdown="# 新概况", summary_data={"title": "新概况", "chapters": []})


class _FailingSummarizer:
    async def summarize(self, video, transcript, cancellation=None) -> SummaryDocument:
        raise RuntimeError("模型不可用")


class _AutomaticMediaProcessor:
    def probe_duration(self, video_path: Path) -> float:
        return 4.0

    def extract_audio(self, video_path: Path, audio_path: Path, cancellation=None) -> Path:
        audio_path.write_text("audio", encoding="utf-8")
        return audio_path


class _AutomaticTranscriber:
    def transcribe(self, audio_path: Path, output_stem: Path, on_progress=None) -> Transcript:
        return Transcript(language="zh", segments=[TranscriptSegment(0.0, 4.0, "自动转写")])


class _FrameExtractor:
    def __init__(self) -> None:
        self.timestamps: list[float] = []

    def extract_frame(self, video_path: Path, timestamp_seconds: float, output_path: Path, cancellation=None) -> Path:
        self.timestamps.append(timestamp_seconds)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"jpeg")
        return output_path


class _PartiallyFailingFrameExtractor(_FrameExtractor):
    def extract_frame(self, video_path: Path, timestamp_seconds: float, output_path: Path, cancellation=None) -> Path:
        if not self.timestamps:
            self.timestamps.append(timestamp_seconds)
            raise RuntimeError("decoder failed")
        return super().extract_frame(video_path, timestamp_seconds, output_path, cancellation)


class _ChapterSummarizer:
    async def summarize(self, video, transcript, cancellation=None) -> SummaryDocument:
        return SummaryDocument(
            markdown="# 概况",
            summary_data={
                "title": "概况",
                "one_sentence_summary": "一句话",
                "core_problem": "问题",
                "chapters": [
                    {
                        "id": "chapter-1",
                        "title": "第一章",
                        "start_seconds": 0.0,
                        "end_seconds": 4.0,
                        "summary": "章节摘要",
                        "key_points": [],
                    }
                ],
                "key_takeaways": [],
            },
        )


class _TwoChapterSummarizer(_ChapterSummarizer):
    async def summarize(self, video, transcript, cancellation=None) -> SummaryDocument:
        document = await super().summarize(video, transcript, cancellation)
        document.summary_data["chapters"].append(
            {
                "id": "chapter-2",
                "title": "第二章",
                "start_seconds": 2.0,
                "end_seconds": 4.0,
                "summary": "第二章摘要",
                "key_points": [],
            }
        )
        return document


def _manual_input() -> ManualTranscriptInput:
    return ManualTranscriptInput(
        transcript=parse_srt_transcript(_SRT),
        raw_srt=_SRT,
        filename="lesson.srt",
    )


class GenerateVideoSummaryManualSrtTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_srt_skips_subtitle_detection_and_asr_then_commits_together(self) -> None:
        summarizer = _Summarizer()
        use_case = GenerateVideoSummary(
            media_processor=_UnexpectedMediaProcessor(),
            transcriber=_UnexpectedTranscriber(),
            transcript_enhancer=None,
            summarizer=summarizer,
            artifact_store=FileSystemGenerationArtifactStore(),
            subtitle_provider=_UnexpectedSubtitleProvider(),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "output"
            document = await use_case.run(root / "video.mp4", output_dir, manual_transcript=_manual_input())

            self.assertEqual(document.summary_data["title"], "新概况")
            self.assertEqual(summarizer.transcripts[0].full_text, "人工字幕第一句\n人工字幕第二句")
            self.assertEqual((output_dir / "transcript.manual.srt").read_text(encoding="utf-8"), _SRT)
            self.assertEqual(json.loads((output_dir / "transcript.source.json").read_text(encoding="utf-8"))["source"], "manual_srt")
            self.assertEqual(json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))["title"], "新概况")

    async def test_manual_srt_failure_keeps_existing_artifacts_unchanged(self) -> None:
        use_case = GenerateVideoSummary(
            media_processor=_UnexpectedMediaProcessor(),
            transcriber=_UnexpectedTranscriber(),
            transcript_enhancer=None,
            summarizer=_FailingSummarizer(),
            artifact_store=FileSystemGenerationArtifactStore(),
            subtitle_provider=_UnexpectedSubtitleProvider(),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "output"
            output_dir.mkdir()
            (output_dir / "summary.json").write_text('{"title":"旧概况"}', encoding="utf-8")
            (output_dir / "transcript.manual.srt").write_text("旧字幕", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "AI 概况生成失败"):
                await use_case.run(root / "video.mp4", output_dir, manual_transcript=_manual_input())

            self.assertEqual((output_dir / "summary.json").read_text(encoding="utf-8"), '{"title":"旧概况"}')
            self.assertEqual((output_dir / "transcript.manual.srt").read_text(encoding="utf-8"), "旧字幕")

    async def test_restore_automatic_transcript_removes_manual_source_only_after_success(self) -> None:
        use_case = GenerateVideoSummary(
            media_processor=_AutomaticMediaProcessor(),
            transcriber=_AutomaticTranscriber(),
            transcript_enhancer=None,
            summarizer=_Summarizer(),
            artifact_store=FileSystemGenerationArtifactStore(),
            manual_transcript_provider=ManualSrtTranscriptProvider(),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "output"
            output_dir.mkdir()
            (root / "video.mp4").write_bytes(b"video")
            (output_dir / "transcript.manual.srt").write_text(_SRT, encoding="utf-8")
            (output_dir / "transcript.source.json").write_text('{"source":"manual_srt"}', encoding="utf-8")

            await use_case.run(root / "video.mp4", output_dir, use_saved_manual_transcript=False)

            self.assertFalse((output_dir / "transcript.manual.srt").exists())
            self.assertFalse((output_dir / "transcript.source.json").exists())
            payload = json.loads((output_dir / "transcript.cleaned.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["segments"][0]["text"], "自动转写")

    async def test_chapter_screenshot_is_staged_with_summary(self) -> None:
        frame_extractor = _FrameExtractor()
        use_case = GenerateVideoSummary(
            media_processor=_UnexpectedMediaProcessor(),
            transcriber=_UnexpectedTranscriber(),
            transcript_enhancer=None,
            summarizer=_ChapterSummarizer(),
            artifact_store=FileSystemGenerationArtifactStore(),
            subtitle_provider=_UnexpectedSubtitleProvider(),
            frame_extractor=frame_extractor,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "output"
            document = await use_case.run(root / "video.mp4", output_dir, manual_transcript=_manual_input())

            self.assertEqual(frame_extractor.timestamps, [2.0])
            self.assertEqual(document.summary_data["chapters"][0]["image_filename"], "chapter-01.jpg")
            self.assertEqual((output_dir / "screenshots" / "chapter-01.jpg").read_bytes(), b"jpeg")
            markdown = (output_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("![章节插图](screenshots/chapter-01.jpg)", markdown)
            self.assertEqual(parse_markdown(markdown)["chapters"][0]["summary"], "章节摘要")

    async def test_chapter_screenshot_failure_preserves_summary_and_continues(self) -> None:
        frame_extractor = _PartiallyFailingFrameExtractor()
        use_case = GenerateVideoSummary(
            media_processor=_UnexpectedMediaProcessor(),
            transcriber=_UnexpectedTranscriber(),
            transcript_enhancer=None,
            summarizer=_TwoChapterSummarizer(),
            artifact_store=FileSystemGenerationArtifactStore(),
            subtitle_provider=_UnexpectedSubtitleProvider(),
            frame_extractor=frame_extractor,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "output"
            document = await use_case.run(root / "video.mp4", output_dir, manual_transcript=_manual_input())

            self.assertEqual(frame_extractor.timestamps, [2.0, 3.0])
            self.assertNotIn("image_filename", document.summary_data["chapters"][0])
            self.assertEqual(document.summary_data["chapters"][1]["image_filename"], "chapter-02.jpg")
            self.assertEqual(document.summary_data["generation_warnings"], ["第 1 章插图未生成，概况已保留。"])
            self.assertTrue((output_dir / "screenshots" / "chapter-02.jpg").is_file())
