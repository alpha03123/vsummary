from backend.video_summary.infrastructure.llm.litellm_note_generator import _resolve_visual_evidence_timestamp


def test_resolves_second_precision_grid_label_to_real_frame_timestamp() -> None:
    assert _resolve_visual_evidence_timestamp(58.0, (51.443, 58.302, 61.731)) == 58.302


def test_rejects_timestamp_outside_grid_label_tolerance() -> None:
    assert _resolve_visual_evidence_timestamp(60.0, (51.443, 58.302)) is None
