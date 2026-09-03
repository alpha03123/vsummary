"""将工作区转写渲染为浏览器原生字幕轨道。"""

from __future__ import annotations

from html import escape
import re

from backend.video_summary.library.models import TranscriptSegmentDTO

_CUE_BREAK_PATTERN = re.compile(r"[^,，、;；。！？!?]+[,，、;；。！？!?]*")
_MAX_CUE_CHARACTERS = 28


def render_webvtt(segments: list[TranscriptSegmentDTO]) -> str:
    """将带时间轴的转写分段转换为 UTF-8 WebVTT 文本。"""
    cues = ["WEBVTT"]
    for segment in segments:
        visual_cues = _split_visual_cues(segment.text)
        total_characters = sum(len(cue) for cue in visual_cues)
        elapsed = segment.start_seconds
        duration = segment.end_seconds - segment.start_seconds
        for index, cue_text in enumerate(visual_cues):
            if index == len(visual_cues) - 1:
                cue_end = segment.end_seconds
            else:
                cue_end = elapsed + duration * len(cue_text) / total_characters
            cues.extend(
                [
                    "",
                    f"{_format_timestamp(elapsed)} --> {_format_timestamp(cue_end)}",
                    _escape_cue_text(cue_text),
                ]
            )
            elapsed = cue_end
    return "\n".join(cues) + "\n"


def _split_visual_cues(text: str) -> list[str]:
    """按自然停顿切分过长转写，避免单个 cue 覆盖整个画面。"""
    normalized = " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split())
    if not normalized:
        raise ValueError("字幕文本不能为空。")

    phrases = _CUE_BREAK_PATTERN.findall(normalized) or [normalized]
    cues: list[str] = []
    current = ""
    for phrase in phrases:
        for part in _split_long_phrase(phrase):
            if current and len(current) + len(part) > _MAX_CUE_CHARACTERS:
                cues.append(current)
                current = part
            else:
                current += part
    if current:
        cues.append(current)
    return cues


def _split_long_phrase(phrase: str) -> list[str]:
    if len(phrase) <= _MAX_CUE_CHARACTERS:
        return [phrase]
    return [phrase[index:index + _MAX_CUE_CHARACTERS] for index in range(0, len(phrase), _MAX_CUE_CHARACTERS)]


def _format_timestamp(seconds: float) -> str:
    if not isinstance(seconds, int | float) or seconds < 0:
        raise ValueError("字幕时间必须是非负数。")
    total_milliseconds = round(seconds * 1000)
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def _escape_cue_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("字幕文本不能为空。")
    return "\n".join(escape(line, quote=False) for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
