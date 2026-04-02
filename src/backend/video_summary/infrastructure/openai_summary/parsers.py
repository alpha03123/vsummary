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
    mindmap = normalize_mindmap_node(
        parsed.get("mindmap", {"title": video.title, "children": []}),
        "root",
    )

    return {
        "title": str(parsed.get("title", video.title)).strip(),
        "one_sentence_summary": str(parsed.get("one_sentence_summary", "")).strip(),
        "core_problem": str(parsed.get("core_problem", "")).strip(),
        "chapters": chapters,
        "key_takeaways": key_takeaways,
        "mindmap": mindmap,
    }


def extract_json_block(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"Model did not return valid JSON: {text[:400]}")

    return json.loads(candidate[start : end + 1])


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

