"""为 transcript evidence 注入可被模型引用的精确 segment anchors。"""

from __future__ import annotations


def number_evidence_items_for_citations(items: list[dict[str, object]]) -> list[dict[str, object]]:
    """为证据项注入 source 编号，并为 transcript segments 注入 `[N.M]` anchors。"""
    return [
        _with_source_anchor_fields(item, index)
        for index, item in enumerate(items, start=1)
    ]


def _with_source_anchor_fields(item: dict[str, object], index: int) -> dict[str, object]:
    numbered = {
        **item,
        "source_number": index,
        "source_label": f"Source {index}",
    }
    source_type = str(item.get("source_type", "")).strip()
    source_family = str(item.get("source_family", "")).strip()
    if source_family != "transcript" and source_type not in {"transcript_chunk", "transcript_full"}:
        return numbered
    anchored_segments = _anchor_segments(item.get("segments"), index)
    if not anchored_segments:
        return numbered
    return {
        **numbered,
        "segments": anchored_segments,
        "text": _render_segment_anchor_lines(anchored_segments),
        "snippet": _render_segment_anchor_lines(anchored_segments),
    }


def _anchor_segments(raw_segments: object, source_number: int) -> list[dict[str, object]]:
    if not isinstance(raw_segments, list):
        return []
    segments: list[dict[str, object]] = []
    for segment_index, raw_segment in enumerate(raw_segments, start=1):
        if not isinstance(raw_segment, dict):
            continue
        text = _as_text(raw_segment.get("text"))
        start_seconds = _as_float(raw_segment.get("start_seconds"))
        end_seconds = _as_float(raw_segment.get("end_seconds"))
        if not text or start_seconds is None:
            continue
        segments.append(
            {
                "anchor_id": f"{source_number}.{segment_index}",
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "text": text,
            }
        )
    return segments


def _render_segment_anchor_lines(segments: list[dict[str, object]]) -> str:
    return "\n".join(
        f"[{segment['anchor_id']}] ({_format_seconds(segment['start_seconds'])}) {segment['text']}"
        for segment in segments
    )


def _format_seconds(value: object) -> str:
    seconds = int(float(value))
    minutes, second = divmod(seconds, 60)
    return f"{minutes:02d}:{second:02d}"


def _as_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
