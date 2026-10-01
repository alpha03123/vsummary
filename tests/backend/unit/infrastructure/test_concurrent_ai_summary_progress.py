from backend.video_summary.library.models import GeneratedVideoAiNoteDTO
from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor
from tests._api_fixtures import mock_service

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from backend.video_summary.domain.models import Transcript, TranscriptSegment, VideoAsset
from backend.video_summary.infrastructure.concurrent_ai_summary_runner import ConcurrentAiSummaryRunner
from backend.video_summary.infrastructure.visual_frame_pool import VisualFramePool


@pytest.mark.parametrize("multimodal,expected_stages", [
    (True, ["sample_frames", "sample_frames", "understand_frames", "ai_summary_completed"]),
    (False, ["generate_ai_summary", "ai_summary_completed"]),
])
def test_reports_actual_picture_work_only_when_enabled(tmp_path, multimodal, expected_stages):
    events = []
    generated = GeneratedVideoAiNoteDTO(content="# Title\nContent", note_visual_mode="off", note_max_images=0,
                                note_image_min_gap_seconds=0, citations=[], visual_evidence=[])
    generator = Mock()
    def generate(**kwargs):
        assert events[-1][0] in {"understand_frames", "generate_ai_summary"}
        return generated

    generator.run_ai_summary.side_effect = generate
    runner = ConcurrentAiSummaryRunner(
        generator=generator, max_input_images=1, multimodal_enabled=multimodal,
        note_visual_mode="off", note_max_images=0, note_image_min_gap_seconds=0,
        media_processor=mock_service(FfmpegMediaProcessor, probe_duration=10),
    )

    def frame_pool(**kwargs):
        kwargs["on_progress"](9, 9)
        return VisualFramePool(image_paths=[tmp_path / "grid.jpg"], timestamps_by_image=[[0.0]])

    with patch("backend.video_summary.infrastructure.concurrent_ai_summary_runner.build_or_load_visual_frame_pool", side_effect=frame_pool) as pool:
        runner._run_sync(
            video=VideoAsset(source_path=Path("video.mp4"), title="Video", duration_seconds=10),
            transcript=Transcript(language="zh", segments=[TranscriptSegment(start_seconds=0, end_seconds=10, text="Hello")]),
            output_dir=tmp_path, on_progress=lambda stage, detail: events.append((stage, detail)),
        )
    assert [stage for stage, _ in events] == expected_stages
    assert (tmp_path / "ai_summary.json").is_file()
    if multimodal:
        assert "9/9" in events[1][1]
        assert "识别画面" in events[2][1]
    else:
        pool.assert_not_called()


def test_picture_failure_does_not_report_completion(tmp_path):
    runner = ConcurrentAiSummaryRunner(
        generator=Mock(), max_input_images=1, multimodal_enabled=True,
        note_visual_mode="off", note_max_images=0, note_image_min_gap_seconds=0,
        media_processor=Mock(),
    )
    events = []
    with patch("backend.video_summary.infrastructure.concurrent_ai_summary_runner.build_or_load_visual_frame_pool", side_effect=RuntimeError("picture failed")):
        with pytest.raises(RuntimeError, match="picture failed"):
            runner._run_sync(video=Mock(), transcript=Mock(), output_dir=tmp_path,
                             on_progress=lambda stage, detail: events.append(stage))
    assert events == ["sample_frames"]
