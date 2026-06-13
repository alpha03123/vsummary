from __future__ import annotations

import re
from dataclasses import dataclass


INLINE_NUMBER_PATTERN = re.compile(r"\[(?P<value>\s*\d+\s*)\]")
EVIDENCE_ID_MARKER_PATTERN = re.compile(r"\[\s*(?:e+[0-9]+|local-\d+|web-\d+)\s*\]")


@dataclass(frozen=True)
class InlineCitationResolution:
    answer_text: str
    used_source_numbers: list[int]
    used_evidence_ids: list[str]


def extract_inline_source_numbers(
    answer_text: str,
    evidence_items: list[dict[str, object]],
) -> list[int]:
    return resolve_inline_citations(answer_text, evidence_items).used_source_numbers


def resolve_inline_citations(
    answer_text: str,
    evidence_items: list[dict[str, object]],
) -> InlineCitationResolution:
    source_map = _build_source_number_map(evidence_items)
    used_numbers: list[int] = []
    used_ids: list[str] = []
    unknown_numbers: list[int] = []
    cleaned_parts: list[str] = []
    last_index = 0
    answer_text = EVIDENCE_ID_MARKER_PATTERN.sub("", answer_text)
    for match in INLINE_NUMBER_PATTERN.finditer(answer_text):
        cleaned_parts.append(answer_text[last_index:match.start()])
        source_number = int(match.group("value").strip())
        evidence_id = source_map.get(source_number)
        if evidence_id is None:
            unknown_numbers.append(source_number)
            cleaned_parts.append(match.group(0))
            last_index = match.end()
            continue
        if source_number not in used_numbers:
            used_numbers.append(source_number)
        if evidence_id not in used_ids:
            used_ids.append(evidence_id)
        cleaned_parts.append(f"[{source_number}]")
        last_index = match.end()
    if unknown_numbers:
        joined_numbers = ", ".join(str(item) for item in dict.fromkeys(unknown_numbers))
        raise ValueError(f"模型输出了未知引用编号: {joined_numbers}")
    cleaned_parts.append(answer_text[last_index:])
    return InlineCitationResolution(
        answer_text="".join(cleaned_parts),
        used_source_numbers=used_numbers,
        used_evidence_ids=used_ids,
    )


def filter_inline_citation_markers(answer_text: str, available_ids: set[str]) -> str:
    def replace_match(match: re.Match[str]) -> str:
        citation_id = match.group("value").strip()
        if citation_id in available_ids:
            return f"[{citation_id}]"
        return ""

    return INLINE_NUMBER_PATTERN.sub(replace_match, answer_text)


def _as_evidence_id(item: dict[str, object]) -> str | None:
    value = item.get("evidence_id")
    if not isinstance(value, str):
        return None
    evidence_id = value.strip()
    return evidence_id or None


def _build_source_number_map(evidence_items: list[dict[str, object]]) -> dict[int, str]:
    source_map: dict[int, str] = {}
    for index, item in enumerate(evidence_items, start=1):
        evidence_id = _as_evidence_id(item)
        if evidence_id is not None:
            source_map[index] = evidence_id
    return source_map
