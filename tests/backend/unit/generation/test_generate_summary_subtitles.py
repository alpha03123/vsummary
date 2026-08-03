from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.video_summary.domain.models import SummaryDocument, Transcript, TranscriptSegment
from backend.video_summary.generation.ports import NoTranscribableAudioError
from backend.video_summary.generation.usecases.generate_summary import GenerateVideoSummary


class _SubtitleSource:
    cache_identity = "test-subtitles"

    def load(self, video_path: Path, staging_dir: Path, cancellation=None) -> Transcript:
        return Transcript(
            language="zh",
            segments=[TranscriptSegment(0.0, 3.0, "使用字幕，不使用 ASR")],
        )


class _MediaProcessor:
    def probe_duration(self, video_path: Path) -> float:
        raise AssertionError("字幕命中时不应探测媒体时长")

    def extract_audio(self, video_path: Path, audio_path: Path, cancellation=None) -> Path:
        raise AssertionError("字幕命中时不应抽取音频")


class _Transcriber:
    def transcribe(self, audio_path: Path, output_stem: Path, on_progress=None) -> Transcript:
        raise AssertionError("字幕命中时不应调用 ASR")


class _ArtifactStore:
    async def save_cleaned_transcript(self, *, video, transcript, output_dir) -> None:
        self.transcript = transcript

    async def save_enhanced_transcript(self, *, transcript, output_dir) -> None:
        self.enhanced_transcript = transcript

    async def save_summary_document(self, *, document, output_dir) -> None:
        self.summary_document = document


class _Enhancer:
    def __init__(self) -> None:
        self.calls = 0

    async def enhance(self, video, transcript, cancellation=None) -> Transcript:
        self.calls += 1
        return Transcript(
            language=transcript.language,
            segments=[TranscriptSegment(0.0, 3.0, f"增强：{transcript.full_text}")],
        )


class _Summarizer:
    async def summarize(self, video, transcript, cancellation=None) -> SummaryDocument:
        assert video.duration_seconds == 3.0
        return SummaryDocument(markdown="# summary", summary_data={})


class _NoAudioMediaProcessor:
    def probe_duration(self, video_path: Path) -> float:
        return 12.0

    def extract_audio(self, video_path: Path, audio_path: Path, cancellation=None) -> Path:
        raise NoTranscribableAudioError("媒体文件不含音频流")


class _UnexpectedTranscriber:
    def transcribe(self, audio_path: Path, output_stem: Path, on_progress=None) -> Transcript:
        raise AssertionError("无音频流时不应调用 ASR")


class _UnexpectedSummarizer:
    async def summarize(self, video, transcript, cancellation=None) -> SummaryDocument:
        raise AssertionError("无可转写信息时不应调用总结模型")


class GenerateVideoSummarySubtitleTests(unittest.IsolatedAsyncioTestCase):
    async def test_subtitle_transcript_skips_media_and_asr(self) -> None:
        store = _ArtifactStore()
        use_case = GenerateVideoSummary(
            media_processor=_MediaProcessor(),
            transcriber=_Transcriber(),
            transcript_enhancer=None,
            summarizer=_Summarizer(),
            artifact_store=store,
            subtitle_provider=_SubtitleSource(),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            await use_case.run(root / "video.mp4", root / "output")
        assert store.transcript.full_text == "使用字幕，不使用 ASR"

    async def test_subtitle_transcript_can_be_enhanced(self) -> None:
        store = _ArtifactStore()
        enhancer = _Enhancer()
        use_case = GenerateVideoSummary(
            media_processor=_MediaProcessor(),
            transcriber=_Transcriber(),
            transcript_enhancer=enhancer,
            summarizer=_Summarizer(),
            artifact_store=store,
            subtitle_provider=_SubtitleSource(),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            video_path = root / "video.mp4"
            video_path.write_text("video", encoding="utf-8")
            await use_case.run(video_path, root / "output")

        assert enhancer.calls == 1
        assert store.enhanced_transcript.full_text == "增强：使用字幕，不使用 ASR"
        assert store.transcript.full_text == "增强：使用字幕，不使用 ASR"

    async def test_missing_subtitle_and_audio_writes_placeholder_artifacts(self) -> None:
        store = _ArtifactStore()
        enhancer = _Enhancer()
        use_case = GenerateVideoSummary(
            media_processor=_NoAudioMediaProcessor(),
            transcriber=_UnexpectedTranscriber(),
            transcript_enhancer=enhancer,
            summarizer=_UnexpectedSummarizer(),
            artifact_store=store,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            video_path = root / "silent.mp4"
            video_path.write_bytes(b"video")
            document = await use_case.run(video_path, root / "output")

        assert store.transcript.language == "und"
        assert store.transcript.full_text == "该视频没有可供转写的音频或中文字幕。"
        assert enhancer.calls == 0
        assert document.summary_data["transcription_status"] == "untranscribable"
        assert document.summary_data["one_sentence_summary"] == "该视频没有可供转写的信息，无法生成内容概况。"
        assert document.summary_data["key_takeaways"] == ["未找到可用中文字幕，且视频不含可供转写的音频流。"]
