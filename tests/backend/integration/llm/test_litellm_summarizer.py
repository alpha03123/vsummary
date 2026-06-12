from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


from backend.video_summary.summary_generation.models import SummaryDocument, Transcript, TranscriptSegment, VideoAsset
from backend.video_summary.adapters.llm.summarizer import LiteLLMCompletionSummarizer
from backend.video_summary.summary_generation import SummaryPayload


class LiteLLMSummarizerModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_single_pass_when_transcript_fits_context_budget(self) -> None:
        gateway = FakeGateway()
        summarizer = LiteLLMCompletionSummarizer(
            gateway=gateway,
            context_window_tokens=4_000,
            reserved_output_tokens=200,
            direct_summary_threshold_ratio=0.9,
        )

        document = await summarizer.summarize(
            _build_video(),
            Transcript(
                language="zh",
                segments=[
                    TranscriptSegment(start_seconds=0.0, end_seconds=5.0, text="第一段内容"),
                    TranscriptSegment(start_seconds=5.0, end_seconds=10.0, text="第二段内容"),
                ],
            ),
        )

        self.assertIsInstance(document, SummaryDocument)
        self.assertEqual(gateway.text_call_count, 0)
        self.assertEqual(gateway.structured_call_count, 1)
        self.assertIn("[00:00-00:05] 第一段内容", gateway.structured_messages[0][0]["content"])
        self.assertIn("转写如下：", gateway.structured_messages[0][0]["content"])

    async def test_falls_back_to_chunk_pipeline_when_transcript_exceeds_budget(self) -> None:
        gateway = FakeGateway()
        summarizer = LiteLLMCompletionSummarizer(
            gateway=gateway,
            context_window_tokens=120,
            reserved_output_tokens=20,
            direct_summary_threshold_ratio=0.9,
        )

        transcript = Transcript(
            language="zh",
            segments=[
                TranscriptSegment(start_seconds=0.0, end_seconds=5.0, text="A" * 180),
                TranscriptSegment(start_seconds=5.0, end_seconds=10.0, text="B" * 180),
            ],
        )

        document = await summarizer.summarize(_build_video(), transcript)

        self.assertIsInstance(document, SummaryDocument)
        self.assertGreaterEqual(gateway.text_call_count, 1)
        self.assertEqual(gateway.structured_call_count, 1)
        self.assertIn("片段总结如下：", gateway.structured_messages[0][0]["content"])

    async def test_chunk_pipeline_can_run_multiple_chunk_requests_in_parallel(self) -> None:
        gateway = BlockingChunkGateway()
        summarizer = LiteLLMCompletionSummarizer(
            gateway=gateway,
            context_window_tokens=120,
            reserved_output_tokens=20,
            direct_summary_threshold_ratio=0.9,
            summary_chunk_concurrency=2,
        )
        transcript = _build_large_transcript()

        with patch(
            "backend.video_summary.adapters.llm.summarizer.chunk_segments",
            return_value=[
                [transcript.segments[0]],
                [transcript.segments[1]],
                [transcript.segments[2]],
            ],
        ):
            task = asyncio.create_task(summarizer.summarize(_build_video(), transcript))
            await asyncio.wait_for(gateway.started_two.wait(), timeout=1.0)
            self.assertGreaterEqual(gateway.max_active_calls, 2)
            gateway.release_calls.set()
            await task

    async def test_chunk_pipeline_preserves_prompt_order_when_chunk_requests_finish_out_of_order(self) -> None:
        gateway = OutOfOrderChunkGateway()
        summarizer = LiteLLMCompletionSummarizer(
            gateway=gateway,
            context_window_tokens=120,
            reserved_output_tokens=20,
            direct_summary_threshold_ratio=0.9,
            summary_chunk_concurrency=3,
        )
        transcript = _build_large_transcript()

        with patch(
            "backend.video_summary.adapters.llm.summarizer.chunk_segments",
            return_value=[
                [transcript.segments[0]],
                [transcript.segments[1]],
                [transcript.segments[2]],
            ],
        ):
            await summarizer.summarize(_build_video(), transcript)

        structured_prompt = gateway.structured_messages[0][0]["content"]
        self.assertLess(structured_prompt.index("chunk-1"), structured_prompt.index("chunk-2"))
        self.assertLess(structured_prompt.index("chunk-2"), structured_prompt.index("chunk-3"))

    async def test_chunk_pipeline_fails_whole_summary_when_any_chunk_fails(self) -> None:
        gateway = FailingChunkGateway()
        summarizer = LiteLLMCompletionSummarizer(
            gateway=gateway,
            context_window_tokens=120,
            reserved_output_tokens=20,
            direct_summary_threshold_ratio=0.9,
            summary_chunk_concurrency=2,
        )
        transcript = _build_large_transcript()

        with patch(
            "backend.video_summary.adapters.llm.summarizer.chunk_segments",
            return_value=[
                [transcript.segments[0]],
                [transcript.segments[1]],
            ],
        ):
            with self.assertRaisesRegex(RuntimeError, "chunk-2 failed"):
                await summarizer.summarize(_build_video(), transcript)

        self.assertEqual(gateway.structured_call_count, 0)


class FakeGateway:
    def __init__(self) -> None:
        self.text_call_count = 0
        self.structured_call_count = 0
        self.text_messages: list[list[dict[str, str]]] = []
        self.structured_messages: list[list[dict[str, str]]] = []

    async def acomplete_text(self, messages, *, temperature=0, response_format=None) -> str:
        del temperature, response_format
        self.text_call_count += 1
        self.text_messages.append(list(messages))
        return "## 片段主题\n- 示例片段摘要"

    async def acomplete_structured(self, messages, *, response_model, temperature=0, retries=2):
        del response_model, temperature, retries
        self.structured_call_count += 1
        self.structured_messages.append(list(messages))
        return SummaryPayload(
            title="视频标题",
            one_sentence_summary="一句话总结",
            core_problem="核心问题",
            chapters=[
                {
                    "id": "chapter-1",
                    "title": "章节一",
                    "start_seconds": 0.0,
                    "end_seconds": 10.0,
                    "summary": "章节摘要",
                    "key_points": ["要点"],
                }
            ],
            key_takeaways=["结论"],
        )


class BlockingChunkGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.active_calls = 0
        self.max_active_calls = 0
        self.started_two = asyncio.Event()
        self.release_calls = asyncio.Event()

    async def acomplete_text(self, messages, *, temperature=0, response_format=None) -> str:
        del messages, temperature, response_format
        self.text_call_count += 1
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        if self.active_calls >= 2:
            self.started_two.set()
        await self.release_calls.wait()
        self.active_calls -= 1
        return f"chunk-{self.text_call_count}"


class OutOfOrderChunkGateway(FakeGateway):
    async def acomplete_text(self, messages, *, temperature=0, response_format=None) -> str:
        del temperature, response_format
        self.text_call_count += 1
        self.text_messages.append(list(messages))
        current_call = self.text_call_count
        await asyncio.sleep(0.03 * (4 - current_call))
        return f"chunk-{current_call}"


class FailingChunkGateway(FakeGateway):
    async def acomplete_text(self, messages, *, temperature=0, response_format=None) -> str:
        del messages, temperature, response_format
        self.text_call_count += 1
        if self.text_call_count == 2:
            raise RuntimeError("chunk-2 failed")
        return "chunk-1"


def _build_video() -> VideoAsset:
    return VideoAsset(
        source_path=Path("video.mp4"),
        title="视频标题",
        duration_seconds=10.0,
    )


def _build_large_transcript() -> Transcript:
    return Transcript(
        language="zh",
        segments=[
            TranscriptSegment(start_seconds=0.0, end_seconds=5.0, text="A" * 180),
            TranscriptSegment(start_seconds=5.0, end_seconds=10.0, text="B" * 180),
            TranscriptSegment(start_seconds=10.0, end_seconds=15.0, text="C" * 180),
        ],
    )


if __name__ == "__main__":
    unittest.main()
