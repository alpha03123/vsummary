from __future__ import annotations

from backend.video_summary.library.models import (
    KnowledgeCardDTO,
    KnowledgeCardSourceRefDTO,
)


class RuleBasedKnowledgeCardGenerator:
    def run(self, *, title: str, summary_data: dict[str, object]) -> list[KnowledgeCardDTO]:
        cards: list[KnowledgeCardDTO] = []
        chapters = summary_data.get("chapters", [])
        if isinstance(chapters, list):
            for chapter_index, chapter in enumerate(chapters, start=1):
                if not isinstance(chapter, dict):
                    continue
                chapter_title = _require_text(chapter.get("title"))
                chapter_summary = _require_text(chapter.get("summary"))
                if chapter_title is None or chapter_summary is None:
                    continue

                source_ref = _build_source_ref(chapter=chapter, quote=chapter_summary)
                points = _collect_points(chapter.get("key_points"))
                if points:
                    for point_index, point in enumerate(points, start=1):
                        cards.append(
                            KnowledgeCardDTO(
                                id=f"kc-{chapter_index}-{point_index}",
                                title=point,
                                kind=_infer_kind(point),
                                summary=point,
                                details=chapter_summary,
                                tags=_collect_tags(chapter_title, point),
                                keywords=_collect_keywords(point, chapter_title),
                                source_refs=[source_ref],
                                related_card_ids=[],
                            )
                        )
                    continue

                cards.append(
                    KnowledgeCardDTO(
                        id=f"kc-{chapter_index}-summary",
                        title=chapter_title,
                        kind="concept",
                        summary=chapter_summary,
                        details=chapter_summary,
                        tags=_collect_tags(chapter_title, title),
                        keywords=_collect_keywords(chapter_title, chapter_summary),
                        source_refs=[source_ref],
                        related_card_ids=[],
                    )
                )

        takeaways = summary_data.get("key_takeaways", [])
        if isinstance(takeaways, list):
            for index, takeaway in enumerate(takeaways, start=1):
                takeaway_text = _require_text(takeaway)
                if takeaway_text is None:
                    continue
                cards.append(
                    KnowledgeCardDTO(
                        id=f"kc-takeaway-{index}",
                        title=takeaway_text,
                        kind="conclusion",
                        summary=takeaway_text,
                        details=takeaway_text,
                        tags=["关键结论"],
                        keywords=_collect_keywords(takeaway_text),
                        source_refs=[],
                        related_card_ids=[],
                    )
                )

        return _attach_related_card_ids(cards)


def _build_source_ref(*, chapter: dict[str, object], quote: str) -> KnowledgeCardSourceRefDTO:
    chapter_id = chapter.get("id")
    return KnowledgeCardSourceRefDTO(
        chapter_id=chapter_id.strip() if isinstance(chapter_id, str) and chapter_id.strip() else None,
        start_seconds=_as_seconds(chapter.get("start_seconds")),
        end_seconds=_as_seconds(chapter.get("end_seconds")),
        quote=quote,
    )


def _collect_points(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    points: list[str] = []
    for item in value:
        normalized = _require_text(item)
        if normalized is not None:
            points.append(normalized)
    return points


def _attach_related_card_ids(cards: list[KnowledgeCardDTO]) -> list[KnowledgeCardDTO]:
    tag_index: dict[str, list[str]] = {}
    for card in cards:
        for tag in card.tags:
            tag_index.setdefault(tag, []).append(card.id)

    return [
        KnowledgeCardDTO(
            id=card.id,
            title=card.title,
            kind=card.kind,
            summary=card.summary,
            details=card.details,
            tags=card.tags,
            keywords=card.keywords,
            source_refs=card.source_refs,
            related_card_ids=[
                candidate_id
                for tag in card.tags
                for candidate_id in tag_index.get(tag, [])
                if candidate_id != card.id
            ][:6],
        )
        for card in cards
    ]


def _infer_kind(text: str) -> str:
    normalized = text.lower()
    if any(keyword in normalized for keyword in ("案例", "example", "demo")):
        return "case"
    if any(keyword in normalized for keyword in ("步骤", "如何", "怎么", "实践", "使用")):
        return "method"
    if any(keyword in normalized for keyword in ("术语", "名词", "概念", "定义", "是什么", "原理")):
        return "term" if "术语" in normalized or "名词" in normalized else "concept"
    if any(keyword in normalized for keyword in ("结论", "建议", "注意")):
        return "conclusion"
    return "concept"


def _collect_tags(*values: object) -> list[str]:
    tags: list[str] = []
    for value in values:
        normalized = _require_text(value)
        if normalized is not None and normalized not in tags:
            tags.append(normalized)
    return tags[:4]


def _collect_keywords(*values: object) -> list[str]:
    keywords: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        sanitized = value.replace("，", " ").replace("。", " ").replace("：", " ")
        for chunk in sanitized.split():
            normalized = chunk.strip(" ,.;:!?()[]{}\"'").strip()
            if len(normalized) < 2 or normalized in keywords:
                continue
            keywords.append(normalized)
    return keywords[:8]


def _require_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _as_seconds(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
