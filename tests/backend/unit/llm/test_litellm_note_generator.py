from backend.video_summary.infrastructure.llm.litellm_note_generator import LiteLLMNoteGenerator, _resolve_visual_evidence_timestamp
from backend.video_summary.infrastructure.llm.litellm_note_generator import (
    AiSummaryCitationPayload,
    AiSummaryEvidencePayload,
    AiSummaryPayload,
    _build_ai_summary_citations,
    _to_generated_note,
    _to_generated_note_with_degraded_citations,
)
from backend.video_summary.library.models import AiSummaryVisualEvidenceDTO, TranscriptSegmentDTO, VideoAiNoteVisualContextDTO, VideoTranscriptDTO


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


def test_discards_unverified_visual_evidence_and_its_citation_without_rejecting_note() -> None:
    transcript = VideoTranscriptDTO(
        "series-1", "video-1", "视频标题", 20, [TranscriptSegmentDTO(2.5, 5.0, "真实转写内容")]
    )
    note = _to_generated_note(
        payload=AiSummaryPayload(
            markdown="转写事实[1]，模型推断的画面事实[2]。",
            visual_evidence=[AiSummaryEvidencePayload(timestamp_seconds=15.0, text="不存在的帧")],
            citations=[
                AiSummaryCitationPayload(citation_id=1, source_type="transcript", timestamp_seconds=2.5),
                AiSummaryCitationPayload(citation_id=2, source_type="visual", timestamp_seconds=15.0),
            ],
        ),
        transcript=transcript,
        allowed_timestamps=(8.25,),
        note_visual_mode="off",
        note_max_images=0,
        note_image_min_gap_seconds=0,
    )

    assert note.content == "转写事实[1]，模型推断的画面事实。"
    assert note.visual_evidence == ()
    assert [citation.id for citation in note.citations] == ["1"]


def test_degraded_citations_keep_verified_transcript_references_and_remove_useless_markers() -> None:
    transcript = VideoTranscriptDTO(
        "series-1", "video-1", "视频标题", 20, [TranscriptSegmentDTO(2.5, 5.0, "真实转写内容")]
    )
    note = _to_generated_note_with_degraded_citations(
        payload=AiSummaryPayload(
            markdown="真实依据[3]，不存在的时间[4]，未声明角标[9]。",
            citations=[
                AiSummaryCitationPayload(citation_id=3, source_type="transcript", timestamp_seconds=2.5),
                AiSummaryCitationPayload(citation_id=4, source_type="transcript", timestamp_seconds=15.0),
            ],
        ),
        transcript=transcript,
        allowed_timestamps=(),
        note_visual_mode="off",
        note_max_images=0,
        note_image_min_gap_seconds=0,
    )

    assert note.content == "真实依据[1]，不存在的时间，未声明角标。"
    assert [citation.id for citation in note.citations] == ["1"]


def test_retries_with_the_validation_error_then_keeps_note_without_unverified_citations() -> None:
    payload = AiSummaryPayload(
        markdown="完成的概括正文[1]。",
        citations=[AiSummaryCitationPayload(citation_id=1, source_type="transcript", timestamp_seconds=15.0)],
    )
    gateway = _SequencedGateway([payload, payload])
    transcript = VideoTranscriptDTO(
        "series-1", "video-1", "视频标题", 20, [TranscriptSegmentDTO(2.5, 5.0, "真实转写内容")]
    )

    note = LiteLLMNoteGenerator(gateway).run_ai_summary(
        transcript=transcript,
        summary=None,
        visual_context=VideoAiNoteVisualContextDTO(frames=[]),
        template="general",
        multimodal_enabled=False,
        note_visual_mode="off",
        note_max_images=0,
        note_image_min_gap_seconds=0,
    )

    assert len(gateway.messages) == 2
    assert "AI 概括引用了未提供的转写时间。" in gateway.messages[1][0]["content"]
    assert note.content == "完成的概括正文。"
    assert note.citations == ()


class _SequencedGateway:
    def __init__(self, payloads: list[AiSummaryPayload]) -> None:
        self._payloads = iter(payloads)
        self.messages = []

    def complete_structured(self, messages, **_kwargs):
        self.messages.append(messages)
        return next(self._payloads)
