"""共享视频帧池：均匀采样、相邻去重并拼成九宫格视觉输入。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
from threading import Lock

from PIL import Image, ImageChops, ImageDraw, ImageStat

from backend.shared.filesystem import atomic_write_text
from backend.video_summary.generation.ports import NoVideoFramesError
from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor


GRID_COLUMNS = 3
GRID_ROWS = 3
TILES_PER_GRID = GRID_COLUMNS * GRID_ROWS
TILE_SIZE = (320, 180)
_POOL_LOCKS: dict[Path, Lock] = {}
_POOL_LOCKS_GUARD = Lock()


@dataclass(frozen=True)
class VisualFramePool:
    """同一视频、同一预算下可复用的九宫格视觉输入。"""

    image_paths: list[Path]
    timestamps_by_image: list[list[float]]


def build_or_load_visual_frame_pool(
    *,
    video_path: Path,
    output_dir: Path,
    max_input_images: int,
    media_processor: FfmpegMediaProcessor | None = None,
) -> VisualFramePool:
    """构建或复用按视频时间均匀覆盖的九宫格帧池。"""
    if max_input_images <= 0:
        raise ValueError("max_input_images 必须是正整数。")
    processor = media_processor or FfmpegMediaProcessor()
    pool_dir = output_dir / "visual_frame_pool" / f"grid-{max_input_images}"
    lock = _pool_lock(pool_dir)
    with lock:
        return _build_or_load_visual_frame_pool(
            video_path=video_path,
            pool_dir=pool_dir,
            max_input_images=max_input_images,
            processor=processor,
        )


def _build_or_load_visual_frame_pool(
    *,
    video_path: Path,
    pool_dir: Path,
    max_input_images: int,
    processor: FfmpegMediaProcessor,
) -> VisualFramePool:
    manifest_path = pool_dir / "manifest.json"
    raw_dir = pool_dir / "raw"
    cached = _load_pool(manifest_path, pool_dir)
    if cached is not None:
        _remove_raw_frames(raw_dir)
        return cached

    try:
        duration = processor.probe_duration(video_path)
        timestamps = _candidate_timestamps(duration, max_input_images * TILES_PER_GRID)
        raw_frames: list[tuple[float, Path]] = []
        for timestamp in timestamps:
            filename = f"{timestamp:.3f}".rstrip("0").rstrip(".") + ".jpg"
            target = raw_dir / filename
            try:
                processor.extract_frame(video_path, timestamp, target)
            except NoVideoFramesError:
                return VisualFramePool(image_paths=[], timestamps_by_image=[])
            except Exception:
                continue
            if target.is_file() and _is_distinct_frame(target, raw_frames[-1][1] if raw_frames else None):
                raw_frames.append((timestamp, target))

        grid_dir = pool_dir / "grids"
        image_paths: list[Path] = []
        timestamps_by_image: list[list[float]] = []
        for index in range(0, len(raw_frames), TILES_PER_GRID):
            group = raw_frames[index:index + TILES_PER_GRID]
            grid_path = grid_dir / f"grid-{index // TILES_PER_GRID + 1:02d}.jpg"
            _compose_grid(group, grid_path)
            image_paths.append(grid_path)
            timestamps_by_image.append([timestamp for timestamp, _ in group])

        pool_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            manifest_path,
            json.dumps(
                {
                    "max_input_images": max_input_images,
                    "images": [path.name for path in image_paths],
                    "timestamps": timestamps_by_image,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        return VisualFramePool(image_paths=image_paths, timestamps_by_image=timestamps_by_image)
    finally:
        _remove_raw_frames(raw_dir)


def _pool_lock(pool_dir: Path) -> Lock:
    key = pool_dir.resolve()
    with _POOL_LOCKS_GUARD:
        lock = _POOL_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _POOL_LOCKS[key] = lock
        return lock


def _candidate_timestamps(duration: float, target_count: int) -> list[float]:
    if duration <= 0:
        return [0.0]
    count = min(target_count, max(1, math.ceil(duration)))
    if count == 1:
        return [0.0]
    last = max(0.0, duration - 0.001)
    return [round(index * last / (count - 1), 3) for index in range(count)]


def _is_distinct_frame(path: Path, previous_path: Path | None) -> bool:
    if previous_path is None:
        return True
    with Image.open(path) as current, Image.open(previous_path) as previous:
        current_thumb = current.convert("L").resize((32, 18))
        previous_thumb = previous.convert("L").resize((32, 18))
        difference = ImageStat.Stat(ImageChops.difference(current_thumb, previous_thumb)).mean[0]
    return difference >= 2.0


def _compose_grid(group: list[tuple[float, Path]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (TILE_SIZE[0] * GRID_COLUMNS, TILE_SIZE[1] * GRID_ROWS), "black")
    draw = ImageDraw.Draw(canvas)
    for index, (timestamp, path) in enumerate(group):
        with Image.open(path) as source:
            tile = source.convert("RGB").resize(TILE_SIZE)
        x = (index % GRID_COLUMNS) * TILE_SIZE[0]
        y = (index // GRID_COLUMNS) * TILE_SIZE[1]
        canvas.paste(tile, (x, y))
        draw.rectangle((x + 6, y + 6, x + 78, y + 27), fill="black")
        draw.text((x + 10, y + 9), _format_timestamp(timestamp), fill="white")
    canvas.save(output_path, format="JPEG", quality=85)


def _load_pool(manifest_path: Path, pool_dir: Path) -> VisualFramePool | None:
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        names = payload.get("images")
        timestamps = payload.get("timestamps")
        if not isinstance(names, list) or not isinstance(timestamps, list) or len(names) != len(timestamps):
            return None
        paths = [pool_dir / "grids" / str(name) for name in names]
        if not all(path.is_file() for path in paths):
            return None
        normalized_timestamps = [[float(value) for value in group] for group in timestamps if isinstance(group, list)]
        if len(normalized_timestamps) != len(paths):
            return None
        return VisualFramePool(image_paths=paths, timestamps_by_image=normalized_timestamps)
    except (OSError, ValueError, TypeError):
        return None


def _remove_raw_frames(raw_dir: Path) -> None:
    if raw_dir.exists():
        shutil.rmtree(raw_dir)


def _format_timestamp(seconds: float) -> str:
    whole = max(0, int(seconds))
    minutes, second_part = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{second_part:02d}" if hours else f"{minutes:02d}:{second_part:02d}"
