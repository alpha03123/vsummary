from backend.video_summary.library.models import TranscriptSegmentDTO
from backend.video_summary.library.subtitle_exports import render_webvtt


def test_render_webvtt_splits_long_transcript_segments_at_natural_pauses() -> None:
    vtt = render_webvtt(
        [
            TranscriptSegmentDTO(
                start_seconds=37.4,
                end_seconds=57.12,
                text="就好像前一两年,我们经常会听到的提示词工程、个人知识库,也就是RAG,还有就是大模型的本地部署以及微调。这些概念以及技术在最近一段时间很少被提及了,甚至是有些技术会被取代。",
            )
        ]
    )

    assert vtt.startswith("WEBVTT\n")
    assert vtt.count(" --> ") == 4
    assert "就好像前一两年,我们经常会听到的提示词工程、" in vtt
    assert "甚至是有些技术会被取代。" in vtt
    assert "00:00:37.400 -->" in vtt
    assert vtt.rstrip().endswith("甚至是有些技术会被取代。")
