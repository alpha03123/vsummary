"""视频课件（PPT / 板书页）提取器、用例与 PDF 导出单元测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
import pytest

from backend.video_summary.infrastructure.courseware_extractor import FfmpegCoursewareExtractor
from backend.video_summary.library.models import VideoSourceDTO
from backend.video_summary.library.usecases.courseware import GenerateVideoCourseware, render_courseware_pdf


class _FakeSlideMediaProcessor:
    """按时间戳生成模拟网课画面：
    - 0~4s：第 1 页 PPT（4s 时手写板书比 0s 更完整，且右下角画中画每帧都在闪烁）
    - 5~9s：第 2 页 PPT（明显不同的几何排版）
    """

    def __init__(self, duration: float = 10.0) -> None:
        self._duration = duration

    def probe_duration(self, video_path: Path) -> float:
        return self._duration

    def extract_frame(self, video_path: Path, timestamp_seconds: float, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas = Image.new("RGB", (640, 360), "white")
        draw = ImageDraw.Draw(canvas)

        if timestamp_seconds < 4.5:
            # Slide 1: header box
            draw.rectangle((40, 30, 600, 90), fill=(30, 80, 180))
            # Progressive handwriting added near the end of slide 1 (t >= 3.0)
            if timestamp_seconds >= 3.0:
                draw.line((60, 150, 320, 150), fill=(20, 20, 20), width=4)
                draw.line((60, 190, 280, 190), fill=(20, 20, 20), width=4)
        else:
            # Slide 2: large diagram + dark table layout (major scene jump)
            draw.rectangle((0, 0, 640, 360), fill=(25, 28, 36))
            draw.rectangle((60, 50, 580, 300), outline=(240, 200, 60), width=6)
            for y in range(80, 280, 35):
                draw.line((90, y, 550, y), fill=(220, 220, 220), width=3)

        # Simulated teacher webcam in bottom-right corner changing every second (should be ignored)
        pip_color = (200, 50, 50) if int(round(timestamp_seconds)) % 2 == 0 else (50, 200, 50)
        draw.rectangle((520, 280, 635, 355), fill=pip_color)

        canvas.save(output_path, format="JPEG", quality=90)
        return output_path


class _FakeCoursewareWorkspace:
    def __init__(self, video_path: Path, *, audio_only: bool = False) -> None:
        self._video_path = video_path
        self._audio_only = audio_only
        self.saved_deck: dict[str, Any] | None = None
        self.saved_files: list[Path] = []

    def is_audio_only_media(self, series_id: str, video_id: str) -> bool:
        return self._audio_only

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        return VideoSourceDTO(
            series_id=series_id,
            video_id=video_id,
            title="考研高数强化第01讲",
            source_name=self._video_path.name,
            source_type="video",
            source_path=self._video_path,
            output_dir=self._video_path.parent / "out",
            processed=True,
        )

    def save_video_courseware(
        self,
        series_id: str,
        video_id: str,
        *,
        deck: dict[str, Any],
        slide_files: list[Path] | None = None,
    ) -> dict[str, Any]:
        self.saved_deck = deck
        self.saved_files = list(slide_files or [])
        return {
            "series_id": series_id,
            "video_id": video_id,
            "title": deck["title"],
            "slide_count": len(deck["slides"]),
            "slides": deck["slides"],
            "can_regenerate": True,
        }


def test_ffmpeg_courseware_extractor_captures_end_of_slide_and_ignores_pip(tmp_path: Path) -> None:
    video_file = tmp_path / "lecture.mp4"
    video_file.write_bytes(b"fake-video")
    processor = _FakeSlideMediaProcessor(duration=10.0)
    extractor = FfmpegCoursewareExtractor(media_processor=processor, change_threshold=10.0)

    result = extractor.extract(video_file, tmp_path / "out")

    assert len(result.slides) == 2
    first_slide, second_slide = result.slides
    # Slide 1 starts at 0.0 and captures the end frame of slide 1 (>= 3.0s) before jumping at 5.0s
    assert first_slide.start_seconds == 0.0
    assert first_slide.capture_seconds >= 3.0
    assert first_slide.end_seconds == 5.0
    assert first_slide.path.suffix == ".webp"
    assert first_slide.path.is_file()

    # Slide 2 starts at 5.0s and runs to the end
    assert second_slide.start_seconds == 5.0
    assert second_slide.end_seconds == 10.0
    assert second_slide.path.is_file()


def test_generate_video_courseware_and_render_pdf(tmp_path: Path) -> None:
    video_file = tmp_path / "lecture.mp4"
    video_file.write_bytes(b"fake-video")
    workspace = _FakeCoursewareWorkspace(video_file)
    extractor = FfmpegCoursewareExtractor(media_processor=_FakeSlideMediaProcessor(duration=10.0), change_threshold=10.0)
    use_case = GenerateVideoCourseware(workspace, extractor, temp_root=tmp_path / "temp")

    persisted_slides: list[Path] = []
    original_save = workspace.save_video_courseware

    def capture_save(series_id: str, video_id: str, *, deck: dict[str, Any], slide_files: list[Path] | None = None):
        for idx, file_path in enumerate(slide_files or [], start=1):
            copied = tmp_path / f"persisted-{idx}.webp"
            copied.write_bytes(file_path.read_bytes())
            persisted_slides.append(copied)
        return original_save(series_id, video_id, deck=deck, slide_files=slide_files)

    workspace.save_video_courseware = capture_save  # type: ignore[method-assign]
    result = use_case.run("series-1", "video-1")

    assert result is not None
    assert result["slide_count"] == 2
    assert len(persisted_slides) == 2

    pdf_bytes = render_courseware_pdf(persisted_slides)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 500


def test_generate_video_courseware_rejects_audio_only(tmp_path: Path) -> None:
    audio_file = tmp_path / "podcast.mp3"
    audio_file.write_bytes(b"fake-audio")
    workspace = _FakeCoursewareWorkspace(audio_file, audio_only=True)
    extractor = FfmpegCoursewareExtractor(media_processor=_FakeSlideMediaProcessor(duration=10.0))
    use_case = GenerateVideoCourseware(workspace, extractor, temp_root=tmp_path / "temp")

    with pytest.raises(ValueError, match="纯音频"):
        use_case.run("series-1", "video-1")
