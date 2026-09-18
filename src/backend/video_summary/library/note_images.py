"""笔记内视频图片标记的解析与校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.generation.ports import NoVideoFramesError


NOTE_IMAGE_MARKER = re.compile(r"\[\[IMG:(?P<timestamp>\d+(?::\d{2}){1,2}(?:\.\d+)?|\d+(?:\.\d+)?)\]\]")


@dataclass(frozen=True)
class NoteImageMarker:
    """一条已语法解析的笔记图片标记。"""

    raw: str
    seconds: float
    start: int
    end: int


def parse_note_image_markers(content: str) -> list[NoteImageMarker]:
    """只解析合法标记；不合法文本由调用方原样保留。"""
    result: list[NoteImageMarker] = []
    for match in NOTE_IMAGE_MARKER.finditer(content):
        try:
            seconds = parse_note_image_timestamp(match.group("timestamp"))
        except ValueError:
            continue
        result.append(NoteImageMarker(raw=match.group(0), seconds=seconds, start=match.start(), end=match.end()))
    return result


def parse_note_image_timestamp(value: str) -> float:
    """解析秒数或 MM:SS / HH:MM:SS 标记时间。"""
    parts = value.split(":")
    if len(parts) == 1:
        seconds = float(parts[0])
    elif len(parts) == 2:
        minutes, seconds_part = parts
        seconds = int(minutes) * 60 + float(seconds_part)
    elif len(parts) == 3:
        hours, minutes, seconds_part = parts
        seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds_part)
    else:
        raise ValueError("图片标记时间格式无效。")
    if seconds < 0:
        raise ValueError("图片标记时间不能小于 0。")
    return seconds


def format_note_image_timestamp(seconds: float) -> str:
    """生成稳定、适合路径与去重的秒数字符串。"""
    normalized = round(seconds, 3)
    return f"{normalized:.3f}".rstrip("0").rstrip(".")


def format_note_image_label(seconds: float) -> str:
    """生成面向用户的图片时间标题。"""
    whole_seconds = max(0, int(seconds))
    minutes, second_part = divmod(whole_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{second_part:02d}" if hours else f"{minutes:02d}:{second_part:02d}"


def materialize_note_frames(*, video_path: Path, output_dir: Path, content: str, frame_extractor) -> None:
    """为合法时间标记物化可复用帧；失败由调用方日志记录且不破坏正文。"""
    duration = frame_extractor.probe_duration(video_path)
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for marker in parse_note_image_markers(content):
        if marker.seconds > duration:
            continue
        filename = f"{format_note_image_timestamp(marker.seconds)}.jpg"
        target = frames_dir / filename
        if target.is_file():
            continue
        try:
            frame_extractor.extract_frame(video_path, marker.seconds, target)
        except NoVideoFramesError:
            return
