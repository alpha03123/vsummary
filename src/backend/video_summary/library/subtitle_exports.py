"""将工作区转写渲染为浏览器原生字幕轨道。"""

from __future__ import annotations

from html import escape

from backend.video_summary.library.models import TranscriptSegmentDTO


def render_webvtt(segments: list[TranscriptSegmentDTO]) -> str:
    """将带时间轴的转写分段转换为 UTF-8 WebVTT 文本。"""
    cues = ["WEBVTT"]
    for segment in segments:
        cues.extend(
            [
                "",
                f"{_format_timestamp(segment.start_seconds)} --> {_format_timestamp(segment.end_seconds)}",
                _escape_cue_text(segment.text),
            ]
        )
    return "\n".join(cues) + "\n"


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
