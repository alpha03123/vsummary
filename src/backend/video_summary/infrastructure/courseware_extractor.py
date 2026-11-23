"""基于 FFmpeg + Pillow 的两阶段低开销视频课件（PPT / 板书页）提取器。

阶段 1（快扫）：
- 优先使用 `-skip_frame nokey`（仅解码 I 帧）+ 320px 缩略图 + `showinfo` 流式扫描；
- 若关键帧过少（例如短视频或长 GOP 视频），自动回退为单进程低帧率采样；
- 采用 4x4 网格分块像素差 + 梯度（边缘）差，自动忽略变化最大的 2 个角落/局部块（抑制画中画老师人像干扰）；
- 按换页跳变点切分出每页区间 `[start_t, end_t]`，默认选取 `end_t` 前最后一个稳定帧作为 `capture_t`（保留最完整板书/动画终点）；
- 使用 dHash 与主体块差值去重，并施加单视频硬性页数上限。

阶段 2（精抽）：
- 对最终保留的 `capture_t` 抽取原分辨率高清帧，缩放至最大宽度 1920px 并编码为 WebP。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image, ImageChops, ImageStat

from backend.video_summary.generation.ports import NoVideoFramesError
from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor
from backend.video_summary.infrastructure.visual_frame_pool import _EXTRACTION_SLOTS
from backend.video_summary.library.usecases.courseware import ExtractedCourseware, ExtractedSlideFile


_PTS_TIME_PATTERN = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
_THUMB_SIZE = (64, 36)
_GRID_COLS = 4
_GRID_ROWS = 4
_MAX_SLIDE_WIDTH = 1920
_WEBP_QUALITY = 82
_DEFAULT_MAX_SLIDES = 80
_MIN_SLIDE_DURATION_SECONDS = 2.0


@dataclass(frozen=True)
class _SampleFrame:
    timestamp: float
    grid_means: tuple[float, ...]
    grid_edges: tuple[float, ...]
    dhash: int


@dataclass(frozen=True)
class _SlideCandidate:
    start_seconds: float
    end_seconds: float
    capture_seconds: float
    sample: _SampleFrame
    change_score: float


class FfmpegCoursewareExtractor:
    """使用 FFmpeg 与 Pillow 提取视频课件页。"""

    def __init__(
        self,
        media_processor: FfmpegMediaProcessor | None = None,
        *,
        max_slides: int = _DEFAULT_MAX_SLIDES,
        change_threshold: float = 11.0,
    ) -> None:
        self._processor = media_processor or FfmpegMediaProcessor()
        self._max_slides = max(1, max_slides)
        self._change_threshold = change_threshold

    def extract(
        self,
        video_path: Path,
        output_dir: Path,
        *,
        on_progress: Callable[[str, float, str], None] | None = None,
    ) -> ExtractedCourseware:
        with _EXTRACTION_SLOTS:
            return self._extract_locked(video_path, output_dir, on_progress=on_progress)

    def _extract_locked(
        self,
        video_path: Path,
        output_dir: Path,
        *,
        on_progress: Callable[[str, float, str], None] | None,
    ) -> ExtractedCourseware:
        duration = max(0.0, float(self._processor.probe_duration(video_path)))
        raw_dir = output_dir / "samples"
        slides_dir = output_dir / "slides"
        raw_dir.mkdir(parents=True, exist_ok=True)
        slides_dir.mkdir(parents=True, exist_ok=True)
        try:
            samples = self._collect_samples(video_path, duration, raw_dir, on_progress=on_progress)
            if not samples:
                return ExtractedCourseware(duration_seconds=duration, slides=[])

            candidates = self._segment_slides(samples, duration)
            deduped = self._deduplicate_and_cap(candidates, duration)

            slides: list[ExtractedSlideFile] = []
            total = len(deduped)
            for ordinal, candidate in enumerate(deduped, start=1):
                if on_progress is not None:
                    ratio = ordinal / max(1, total)
                    on_progress("courseware", 55.0 + ratio * 35.0, f"正在抽取高清课件页 ({ordinal}/{total})")
                capture_ms = max(0, round(candidate.capture_seconds * 1000))
                raw_frame_path = raw_dir / f"hi-{ordinal:03d}.jpg"
                webp_filename = f"slide-{ordinal:03d}-{capture_ms}.webp"
                webp_path = slides_dir / webp_filename
                try:
                    self._processor.extract_frame(video_path, candidate.capture_seconds, raw_frame_path)
                except NoVideoFramesError:
                    return ExtractedCourseware(duration_seconds=duration, slides=[])
                except Exception:
                    continue
                if not raw_frame_path.is_file():
                    continue
                width, height = _convert_to_webp(raw_frame_path, webp_path)
                raw_frame_path.unlink(missing_ok=True)
                slides.append(
                    ExtractedSlideFile(
                        ordinal=len(slides) + 1,
                        start_seconds=candidate.start_seconds,
                        end_seconds=candidate.end_seconds,
                        capture_seconds=candidate.capture_seconds,
                        image_filename=webp_filename,
                        path=webp_path,
                        width=width,
                        height=height,
                    )
                )
            return ExtractedCourseware(duration_seconds=duration, slides=slides)
        finally:
            shutil.rmtree(raw_dir, ignore_errors=True)

    def _collect_samples(
        self,
        video_path: Path,
        duration: float,
        raw_dir: Path,
        *,
        on_progress: Callable[[str, float, str], None] | None,
    ) -> list[_SampleFrame]:
        # Only use native ffmpeg keyframe stream when self._processor is a standard FfmpegMediaProcessor
        # and the video is long enough that keyframe streaming pays off.
        if type(self._processor) is FfmpegMediaProcessor and duration >= 30.0:
            keyframe_samples = _extract_keyframe_samples_via_ffmpeg(video_path, raw_dir)
            min_expected = max(4, int(duration / 15.0))
            if len(keyframe_samples) >= min_expected:
                if on_progress is not None:
                    on_progress("courseware", 50.0, f"已完成关键帧扫描（共 {len(keyframe_samples)} 帧）")
                return keyframe_samples
            _clear_dir(raw_dir)

        timestamps = _uniform_sample_timestamps(duration)
        samples: list[_SampleFrame] = []
        for index, timestamp in enumerate(timestamps, start=1):
            target = raw_dir / f"sample-{index:05d}.jpg"
            try:
                self._processor.extract_frame(video_path, timestamp, target)
            except NoVideoFramesError:
                return []
            except Exception:
                continue
            if target.is_file():
                try:
                    samples.append(_analyze_sample_image(target, timestamp))
                except OSError:
                    pass
                finally:
                    target.unlink(missing_ok=True)
            if on_progress is not None and (index == len(timestamps) or index % 8 == 0):
                ratio = index / max(1, len(timestamps))
                on_progress("courseware", 10.0 + ratio * 42.0, f"正在扫描画面跳变 ({index}/{len(timestamps)})")
        return samples

    def _segment_slides(self, samples: list[_SampleFrame], duration: float) -> list[_SlideCandidate]:
        if not samples:
            return []
        effective_duration = max(duration, samples[-1].timestamp + 0.5)
        segments: list[_SlideCandidate] = []
        seg_start_idx = 0
        anchor_sample = samples[0]
        last_change_score = 100.0

        for idx in range(1, len(samples)):
            current = samples[idx]
            prev = samples[idx - 1]
            step_score = _frame_change_score(prev, current)
            drift_score = _frame_change_score(anchor_sample, current)
            is_jump = step_score >= self._change_threshold or (
                step_score >= self._change_threshold * 0.72 and drift_score >= self._change_threshold * 1.35
            )
            if is_jump:
                start_t = 0.0 if not segments else samples[seg_start_idx].timestamp
                end_t = current.timestamp
                # Capture the last stable frame of the finishing slide (complete board/slide state).
                capture_sample = samples[idx - 1]
                segments.append(
                    _SlideCandidate(
                        start_seconds=start_t,
                        end_seconds=max(start_t, end_t),
                        capture_seconds=capture_sample.timestamp,
                        sample=capture_sample,
                        change_score=last_change_score,
                    )
                )
                seg_start_idx = idx
                anchor_sample = current
                last_change_score = max(step_score, drift_score)

        start_t = 0.0 if not segments else samples[seg_start_idx].timestamp
        capture_sample = samples[-1]
        segments.append(
            _SlideCandidate(
                start_seconds=start_t,
                end_seconds=max(start_t, effective_duration),
                capture_seconds=capture_sample.timestamp,
                sample=capture_sample,
                change_score=last_change_score,
            )
        )
        return segments

    def _deduplicate_and_cap(
        self,
        candidates: list[_SlideCandidate],
        duration: float,
    ) -> list[_SlideCandidate]:
        if len(candidates) <= 1:
            return candidates

        # 1. Drop transient transition flashes (< 2.0s) when there are solid slides around them.
        min_dur = _MIN_SLIDE_DURATION_SECONDS if duration >= 12.0 else 0.4
        filtered = [c for c in candidates if (c.end_seconds - c.start_seconds) >= min_dur]
        if not filtered:
            filtered = candidates

        # 2. Merge / deduplicate slides that revisit an identical PPT page without board additions.
        deduped: list[_SlideCandidate] = []
        for candidate in filtered:
            if deduped and _is_duplicate_slide(deduped[-1].sample, candidate.sample, self._change_threshold):
                prev = deduped[-1]
                # Keep the later capture timestamp so progressive handwriting is preserved.
                deduped[-1] = _SlideCandidate(
                    start_seconds=prev.start_seconds,
                    end_seconds=candidate.end_seconds,
                    capture_seconds=candidate.capture_seconds,
                    sample=candidate.sample,
                    change_score=max(prev.change_score, candidate.change_score),
                )
                continue
            # Also check recent 3 slides in case the teacher briefly flipped back and forth.
            if any(
                _is_duplicate_slide(recent.sample, candidate.sample, self._change_threshold * 0.75)
                for recent in deduped[-3:]
            ):
                continue
            deduped.append(candidate)

        # 3. Enforce hard slide limit per video to protect disk & memory on dynamic videos.
        duration_minutes = max(1.0, duration / 60.0)
        dynamic_cap = min(self._max_slides, max(12, math.ceil(duration_minutes * 1.5)))
        if len(deduped) > dynamic_cap:
            first = deduped[0]
            ranked = sorted(
                deduped[1:],
                key=lambda item: item.change_score * math.log1p(max(1.0, item.end_seconds - item.start_seconds)),
                reverse=True,
            )[: dynamic_cap - 1]
            deduped = [first, *sorted(ranked, key=lambda item: item.start_seconds)]

        return deduped


def _extract_keyframe_samples_via_ffmpeg(video_path: Path, raw_dir: Path) -> list[_SampleFrame]:
    command = [
        "ffmpeg",
        "-v",
        "info",
        "-nostdin",
        "-y",
        "-threads",
        "1",
        "-skip_frame",
        "nokey",
        "-i",
        str(video_path),
        "-vf",
        "scale=320:-2,showinfo",
        "-vsync",
        "vfr",
        "-q:v",
        "6",
        str(raw_dir / "kf-%05d.jpg"),
    ]
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if proc.returncode != 0:
        return []
    timestamps = [float(match) for match in _PTS_TIME_PATTERN.findall(proc.stderr)]
    files = sorted(raw_dir.glob("kf-*.jpg"))
    if not files:
        return []
    samples: list[_SampleFrame] = []
    for idx, file_path in enumerate(files):
        ts = timestamps[idx] if idx < len(timestamps) else float(idx * 2.0)
        try:
            samples.append(_analyze_sample_image(file_path, ts))
        except OSError:
            pass
        finally:
            file_path.unlink(missing_ok=True)
    return samples


def _uniform_sample_timestamps(duration: float) -> list[float]:
    if duration <= 0.5:
        return [0.0]
    # Step size scales gently with video length: 1s for short clips, 2s up to 30m, up to 4s for 2h+ lectures.
    if duration <= 120.0:
        step = 1.0
    elif duration <= 1800.0:
        step = 2.0
    else:
        step = min(4.0, max(2.0, duration / 900.0))
    last = max(0.0, duration - 0.5)
    count = max(2, int(math.floor(last / step)) + 1)
    return [round(min(last, i * step), 3) for i in range(count)]


def _analyze_sample_image(image_path: Path, timestamp: float) -> _SampleFrame:
    with Image.open(image_path) as source:
        gray = source.convert("L").resize(_THUMB_SIZE, Image.Resampling.BILINEAR)
        # Lightweight edge intensity map via 1px horizontal + vertical shift difference.
        shifted_x = ImageChops.offset(gray, 1, 0)
        shifted_y = ImageChops.offset(gray, 0, 1)
        edges = ImageChops.add(ImageChops.difference(gray, shifted_x), ImageChops.difference(gray, shifted_y))

        cell_w = _THUMB_SIZE[0] // _GRID_COLS
        cell_h = _THUMB_SIZE[1] // _GRID_ROWS
        means: list[float] = []
        edge_means: list[float] = []
        for row in range(_GRID_ROWS):
            for col in range(_GRID_COLS):
                box = (col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h)
                means.append(float(ImageStat.Stat(gray.crop(box)).mean[0]))
                edge_means.append(float(ImageStat.Stat(edges.crop(box)).mean[0]))

        # 64-bit dHash (9x8 grayscale horizontal gradient)
        dhash_img = gray.resize((9, 8), Image.Resampling.BILINEAR)
        pixels = list(dhash_img.getdata())
        bits = 0
        for r in range(8):
            row_offset = r * 9
            for c in range(8):
                bits = (bits << 1) | (1 if pixels[row_offset + c] > pixels[row_offset + c + 1] else 0)

    return _SampleFrame(
        timestamp=round(timestamp, 3),
        grid_means=tuple(means),
        grid_edges=tuple(edge_means),
        dhash=bits,
    )


def _frame_change_score(first: _SampleFrame, second: _SampleFrame) -> float:
    cell_scores: list[float] = []
    for mean_a, mean_b, edge_a, edge_b in zip(
        first.grid_means, second.grid_means, first.grid_edges, second.grid_edges
    ):
        mean_diff = abs(mean_a - mean_b)
        edge_diff = abs(edge_a - edge_b)
        cell_scores.append(mean_diff * 0.65 + edge_diff * 1.45)
    cell_scores.sort()
    # Drop the 2 most volatile cells (e.g., Picture-in-Picture teacher webcam in a corner).
    core_cells = cell_scores[:-2] if len(cell_scores) > 2 else cell_scores
    avg_core = sum(core_cells) / max(1, len(core_cells))
    active_blocks = sum(1 for score in core_cells if score >= 8.0)
    return avg_core + active_blocks * 1.25


def _is_duplicate_slide(first: _SampleFrame, second: _SampleFrame, threshold: float) -> bool:
    hamming = (first.dhash ^ second.dhash).bit_count()
    score = _frame_change_score(first, second)
    return hamming <= 6 and score < threshold * 0.7


def _convert_to_webp(source_path: Path, target_path: Path) -> tuple[int, int]:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        if width > _MAX_SLIDE_WIDTH:
            new_height = max(1, round(height * (_MAX_SLIDE_WIDTH / width)))
            rgb = rgb.resize((_MAX_SLIDE_WIDTH, new_height), Image.Resampling.LANCZOS)
            width, height = rgb.size
        rgb.save(target_path, format="WEBP", quality=_WEBP_QUALITY)
        return width, height


def _clear_dir(directory: Path) -> None:
    for item in directory.iterdir():
        if item.is_file():
            item.unlink(missing_ok=True)
