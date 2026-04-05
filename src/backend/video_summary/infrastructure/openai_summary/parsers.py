from __future__ import annotations

import json
from typing import Any

from backend.video_summary.domain.models import VideoAsset


def parse_summary_payload(raw_text: str, video: VideoAsset) -> dict[str, Any]:
    parsed = extract_json_block(raw_text)

    chapters = [
        normalize_chapter(chapter, index)
        for index, chapter in enumerate(parsed.get("chapters", []))
        if isinstance(chapter, dict)
    ]
    key_takeaways = [
        str(item).strip() for item in parsed.get("key_takeaways", []) if str(item).strip()
    ]
    return {
        "title": str(parsed.get("title", video.title)).strip(),
        "one_sentence_summary": str(parsed.get("one_sentence_summary", "")).strip(),
        "core_problem": str(parsed.get("core_problem", "")).strip(),
        "chapters": chapters,
        "key_takeaways": key_takeaways,
    }


def parse_mindmap_payload(raw_text: str, *, title: str, duration_seconds: float) -> dict[str, Any]:
    parsed = extract_json_block(raw_text)
    default_root = {
        "id": "root",
        "title": title,
        "summary": "",
        "start_seconds": 0.0,
        "end_seconds": duration_seconds,
        "children": [],
    }
    root = parsed if isinstance(parsed, dict) and "children" in parsed else parsed.get("mindmap", default_root)
    return normalize_mindmap_node(root, "root")


def extract_json_block(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()

    direct_value = _try_load_json_object(candidate)
    if direct_value is not None:
        return direct_value

    last_valid_object: dict[str, Any] | None = None
    for start_index in _iter_object_starts(candidate):
        parsed = _extract_balanced_object(candidate, start_index)
        if parsed is not None:
            last_valid_object = parsed

    if last_valid_object is not None:
        return last_valid_object

    raise RuntimeError(f"Model did not return valid JSON object: {text[:400]}")


def normalize_chapter(chapter: dict[str, Any], index: int) -> dict[str, Any]:
    chapter_id = chapter.get("id") or f"chapter-{index + 1}"
    return {
        "id": str(chapter_id),
        "title": str(chapter.get("title", f"章节 {index + 1}")).strip(),
        "start_seconds": float(chapter.get("start_seconds", 0.0) or 0.0),
        "end_seconds": float(chapter.get("end_seconds", 0.0) or 0.0),
        "summary": str(chapter.get("summary", "")).strip(),
        "key_points": [str(item).strip() for item in chapter.get("key_points", []) if str(item).strip()],
    }


def normalize_mindmap_node(node: dict[str, Any], fallback_id: str) -> dict[str, Any]:
    children = node.get("children", [])
    normalized_children = [
        normalize_mindmap_node(child, f"{fallback_id}-{index + 1}")
        for index, child in enumerate(children)
        if isinstance(child, dict)
    ]
    return {
        "id": str(node.get("id", fallback_id)),
        "title": str(node.get("title", "")).strip(),
        "summary": str(node.get("summary", "")).strip(),
        "start_seconds": float(node.get("start_seconds", 0.0) or 0.0),
        "end_seconds": float(node.get("end_seconds", 0.0) or 0.0),
        "children": normalized_children,
    }


def _try_load_json_object(candidate: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _iter_object_starts(candidate: str):
    in_string = False
    escape = False
    for index, char in enumerate(candidate):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = in_string
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string and char == "{":
            yield index


def _extract_balanced_object(candidate: str, start_index: int) -> dict[str, Any] | None:
    depth = 0
    in_string = False
    escape = False
    for index in range(start_index, len(candidate)):
        char = candidate[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = in_string
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return _try_load_json_object(candidate[start_index : index + 1])
    return None
