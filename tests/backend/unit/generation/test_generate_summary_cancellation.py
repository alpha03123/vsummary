from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset
from backend.video_summary.generation.cancellation import GenerationCancellationContext
from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError, GenerateVideoSummary


class FakeArtifactStore:
    def __init__(self) -> None:
        self.saved_enhanced: list = []
        self.saved_cleaned: list = []
        self.saved_summary: list = []

    async def save_enhanced_transcript(self, *, transcript, output_dir) -> None:
        self.saved_enhanced.append(transcript)

    async def save_cleaned_transcript(self, *, video, transcript, output_dir) -> None:
        self.saved_cleaned.append(transcript)

    async def save_summary_document(self, *, document, output_dir) -> None:
        self.saved_summary.append(document)


class FakeMediaProcessor:
    def __init__(self, kill_event: asyncio.Event | None = None) -> None:
        self.kill_called = False
        self._kill_event = kill_event

    def probe_duration(self, video_path: Path) -> float:
        return 10.0

    def extract_audio(self, video_path: Path, audio_path: Path, cancellation=None) -> Path:
        if cancellation is not None:
            proc = MagicMock()
            proc.returncode = -9

            def fake_wait():
                if cancellation.cancel_requested:
                    self.kill_called = True

            proc.wait = fake_wait
            from backend.video_summary.generation.cancellation import ProcessHandle
            handle = ProcessHandle(_proc=proc)
            cancellation.register(handle)
            try:
                cancellation._cancel_event.wait(timeout=0.1)
                self.kill_called = True
            finally:
                cancellation.unregister(handle)
        return audio_path


class FakeTranscriber:
    def transcribe(self, audio_path, output_stem, on_progress=None) -> Transcript:
        return Transcript(language="zh", segments=[])


class FakeEnhancer:
    def __init__(self, chunks: int = 2) -> None:
        self._chunks = chunks
        self.calls = 0

    async def enhance(self, video, transcript, cancellation=None) -> Transcript:
        for i in range(self._chunks):
            if cancellation is not None and cancellation.cancel_requested:
                raise GenerateCancelledError("任务已取消")
            self.calls += 1
            await asyncio.sleep(0)
        return transcript


class FakeSummarizer:
    def __init__(self) -> None:
        self.calls = 0

    async def summarize(self, video, transcript, cancellation=None) -> SummaryDocument:
        if cancellation is not None and cancellation.cancel_requested:
            raise GenerateCancelledError("任务已取消")
        self.calls += 1
        return SummaryDocument(markdown="# Test", summary_data={"title": "Test"})


class GenerateVideoSummaryCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_audio_cancel_raises_generate_cancelled(self) -> None:
        cancellation = GenerationCancellationContext("series-1/video-1")
        media = FakeMediaProcessor()
        use_case = GenerateVideoSummary(
            media_processor=media,
            transcriber=FakeTranscriber(),
            transcript_enhancer=None,
            summarizer=FakeSummarizer(),
            artifact_store=FakeArtifactStore(),
        )

        async def cancel_soon():
            await asyncio.sleep(0.01)
            cancellation.request_cancel()

        video_path = Path("fake_video.mp4")
        output_dir = Path("fake_output")

        with patch("asyncio.to_thread", side_effect=_fake_to_thread):
            asyncio.create_task(cancel_soon())
            cancellation.request_cancel()
            with self.assertRaises(GenerateCancelledError):
                from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
                tracker = InMemoryProgressTracker()
                reporter = tracker.create_reporter("series-1/video-1")
                tracker.request_cancel("series-1/video-1")
                await use_case.run(video_path, output_dir, reporter, cancellation)

    async def test_enhance_transcript_cancel_between_chunks_does_not_save(self) -> None:
        cancellation = GenerationCancellationContext("series-1/video-1")
        enhancer = FakeEnhancer(chunks=3)
        store = FakeArtifactStore()

        class CancelAfterFirstChunkEnhancer:
            def __init__(self) -> None:
                self.calls = 0

            async def enhance(self, video, transcript, cancellation=None):
                for i in range(3):
                    if cancellation is not None and cancellation.cancel_requested:
                        raise GenerateCancelledError("任务已取消")
                    self.calls += 1
                    if self.calls == 1:
                        cancellation.request_cancel()
                    await asyncio.sleep(0)
                return transcript

        cancel_enhancer = CancelAfterFirstChunkEnhancer()
        use_case = GenerateVideoSummary(
            media_processor=FakeMediaProcessor(),
            transcriber=FakeTranscriber(),
            transcript_enhancer=cancel_enhancer,
            summarizer=FakeSummarizer(),
            artifact_store=store,
        )

        with patch("asyncio.to_thread", side_effect=_fake_to_thread):
            with self.assertRaises(GenerateCancelledError):
                await use_case.run(Path("v.mp4"), Path("out"), cancellation=cancellation)

        self.assertEqual(cancel_enhancer.calls, 1)
        self.assertEqual(store.saved_enhanced, [])
        self.assertEqual(store.saved_summary, [])

    async def test_summarize_cancel_does_not_save_summary(self) -> None:
        cancellation = GenerationCancellationContext("series-1/video-1")
        store = FakeArtifactStore()

        class CancelSummarizer:
            async def summarize(self, video, transcript, cancellation=None):
                if cancellation is not None:
                    cancellation.request_cancel()
                raise GenerateCancelledError("任务已取消")

        use_case = GenerateVideoSummary(
            media_processor=FakeMediaProcessor(),
            transcriber=FakeTranscriber(),
            transcript_enhancer=None,
            summarizer=CancelSummarizer(),
            artifact_store=store,
        )

        with patch("asyncio.to_thread", side_effect=_fake_to_thread):
            with self.assertRaises(GenerateCancelledError):
                await use_case.run(Path("v.mp4"), Path("out"), cancellation=cancellation)

        self.assertEqual(store.saved_summary, [])

    async def test_cancelled_error_is_not_wrapped_as_runtime_error(self) -> None:
        """GenerateCancelledError must not be swallowed by the except Exception branch."""
        cancellation = GenerationCancellationContext("series-1/video-1")

        class AlwaysCancelSummarizer:
            async def summarize(self, video, transcript, cancellation=None):
                raise GenerateCancelledError("取消")

        use_case = GenerateVideoSummary(
            media_processor=FakeMediaProcessor(),
            transcriber=FakeTranscriber(),
            transcript_enhancer=None,
            summarizer=AlwaysCancelSummarizer(),
            artifact_store=FakeArtifactStore(),
        )

        with patch("asyncio.to_thread", side_effect=_fake_to_thread):
            with self.assertRaises(GenerateCancelledError):
                await use_case.run(Path("v.mp4"), Path("out"), cancellation=cancellation)


async def _fake_to_thread(func, *args, **kwargs):
    return func(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
