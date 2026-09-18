from backend.video_summary.infrastructure.llm.litellm_note_generator import _resolve_visual_evidence_timestamp
from backend.video_summary.infrastructure.llm.litellm_note_generator import (
    AiSummaryCitationPayload,
    _build_ai_summary_citations,
)
from backend.video_summary.library.models import AiSummaryVisualEvidenceDTO, TranscriptSegmentDTO, VideoTranscriptDTO


def test_resolves_second_precision_grid_label_to_real_frame_timestamp() -> None:
    assert _resolve_visual_evidence_timestamp(58.0, (51.443, 58.302, 61.731)) == 58.302


def test_rejects_timestamp_outside_grid_label_tolerance() -> None:
    assert _resolve_visual_evidence_timestamp(60.0, (51.443, 58.302)) is None


def test_builds_seekable_citations_only_from_real_transcript_and_visual_evidence() -> None:
    transcript = VideoTranscriptDTO(
        series_id="series-1",
        video_id="video-1",
        title="视频标题",
        duration_seconds=20,
        segments=[TranscriptSegmentDTO(2.5, 5.0, "真实转写内容")],
    )
    citations = _build_ai_summary_citations(
        markdown="转写事实[1]，画面事实[2]。",
        citations=[
            AiSummaryCitationPayload(citation_id=1, source_type="transcript", timestamp_seconds=2.5),
            AiSummaryCitationPayload(citation_id=2, source_type="visual", timestamp_seconds=8.25),
        ],
        transcript=transcript,
        visual_evidence=[AiSummaryVisualEvidenceDTO(timestamp_seconds=8.25, text="真实画面描述")],
    )

    assert citations[0].slots[0].start_seconds == 2.5
    assert citations[0].slots[1].text == "真实转写内容"
    assert citations[1].slots[0].start_seconds == 8.25


def test_rejects_markers_without_matching_declared_citation() -> None:
    transcript = VideoTranscriptDTO("series-1", "video-1", "视频标题", 20, [TranscriptSegmentDTO(0, 1, "内容")])
    try:
        _build_ai_summary_citations(
            markdown="没有对应引用[1]。",
            citations=[],
            transcript=transcript,
            visual_evidence=[],
        )
    except ValueError as error:
        assert "一一对应" in str(error)
    else:
        raise AssertionError("缺少声明引用时必须失败")
