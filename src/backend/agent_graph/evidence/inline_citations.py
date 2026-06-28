"""解析与过滤 LLM 流式回答中的 inline 数字引用（`[1]` / `[2.1]` ...）。

提供三个职责单一的工具函数：
- `resolve_inline_citations`：把回答中的 `[N]` / `[N.M]` 解析回 `evidence_id`，
  并剥离任何误输出的内部 ID 标记（`e1`、`local-1`、`web-2` 等）；
- `extract_inline_source_numbers`：上面那个函数的"只取编号"便捷封装；
- `filter_inline_citation_markers`：按白名单只保留合法的 citation 编号。

设计原则：引用编号必须与上游 `evidence_items` 顺序对齐；遇到模型"幻觉"
出来的未知编号必须抛错，而不是静默丢弃。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# 匹配回答正文中的 inline 数字引用 `[N]` 或 transcript segment anchor `[N.M]`。
INLINE_NUMBER_PATTERN = re.compile(r"\[(?P<value>\s*\d+(?:\.\d+)?\s*)\]")

# 匹配模型在流式输出时可能误输出的内部 ID 标记（命中后直接整段删除）。
EVIDENCE_ID_MARKER_PATTERN = re.compile(r"\[\s*(?:e+[0-9]+|local-\d+|web-\d+)\s*\]")


@dataclass(frozen=True)
class InlineCitationResolution:
    """inline 引用解析后的中间结果。

    Attributes:
        answer_text: 去除内部 ID 标记后的回答正文。
        used_source_numbers: 回答中实际引用过的 source 编号（按出现顺序）。
        used_evidence_ids: 与 `used_source_numbers` 一一对应的 evidence_id 列表。
        used_citation_ids: 回答中实际引用过的 citation id（按出现顺序）。
    """

    answer_text: str
    used_source_numbers: list[int]
    used_evidence_ids: list[str]
    used_citation_ids: list[str]


def extract_inline_source_numbers(
    answer_text: str,
    evidence_items: list[dict[str, object]],
) -> list[int]:
    """便捷封装：只返回回答中使用到的 source 编号列表。

    Args:
        answer_text: 模型流式输出的回答正文。
        evidence_items: 用于把编号映射回 evidence_id 的证据列表。

    Returns:
        按出现顺序排列的 source 编号列表。
    """
    return resolve_inline_citations(answer_text, evidence_items).used_source_numbers


def resolve_inline_citations(
    answer_text: str,
    evidence_items: list[dict[str, object]],
) -> InlineCitationResolution:
    """把回答中的 `[N]` / `[N.M]` 解析为 `evidence_id`，并清理内部 ID 标记。

    处理流程：
    1. 先用 `EVIDENCE_ID_MARKER_PATTERN` 把所有 `e1`、`local-1`、`web-2`
       这类内部 ID 标记整段删除，避免泄露内部命名；
    2. 用 `INLINE_NUMBER_PATTERN` 扫描 `[N]`，按出现顺序累计到
       `used_source_numbers` 与 `used_evidence_ids`；
    3. 收集"出现但 evidence_items 中不存在"的编号 —— 任何未知编号都
       会触发 `ValueError`，防止模型幻觉引用导致证据链断裂。

    Args:
        answer_text: 模型流式输出的回答正文。
        evidence_items: 顺序与编号一一对应的证据字典列表。

    Returns:
        解析后的 `InlineCitationResolution`，含去标记正文、引用编号、
        对应 evidence_id。

    Raises:
        ValueError: 模型输出了未在 `evidence_items` 中出现的引用编号。
    """
    citation_map = _build_citation_map(evidence_items)
    used_numbers: list[int] = []
    used_ids: list[str] = []
    used_citation_ids: list[str] = []
    unknown_numbers: list[str] = []
    cleaned_parts: list[str] = []
    last_index = 0
    answer_text = EVIDENCE_ID_MARKER_PATTERN.sub("", answer_text)
    for match in INLINE_NUMBER_PATTERN.finditer(answer_text):
        cleaned_parts.append(answer_text[last_index:match.start()])
        citation_id = match.group("value").strip()
        source_number = int(citation_id.split(".", 1)[0])
        evidence_id = citation_map.get(citation_id)
        if evidence_id is None:
            unknown_numbers.append(citation_id)
            cleaned_parts.append(match.group(0))
            last_index = match.end()
            continue
        if source_number not in used_numbers:
            used_numbers.append(source_number)
        if evidence_id not in used_ids:
            used_ids.append(evidence_id)
        if citation_id not in used_citation_ids:
            used_citation_ids.append(citation_id)
        cleaned_parts.append(f"[{citation_id}]")
        last_index = match.end()
    if unknown_numbers:
        joined_numbers = ", ".join(str(item) for item in dict.fromkeys(unknown_numbers))
        raise ValueError(f"模型输出了未知引用编号: {joined_numbers}")
    cleaned_parts.append(answer_text[last_index:])
    return InlineCitationResolution(
        answer_text="".join(cleaned_parts),
        used_source_numbers=used_numbers,
        used_evidence_ids=used_ids,
        used_citation_ids=used_citation_ids,
    )


def filter_inline_citation_markers(answer_text: str, available_ids: set[str]) -> str:
    """按白名单只保留合法的 inline 引用编号，其余整段删除。

    适用于"已经知道 answer 中允许出现哪些编号"的前置过滤场景（例如
    用户复制粘贴一段历史回答再次展示时）。

    Args:
        answer_text: 待过滤的原始回答文本。
        available_ids: 允许保留的引用编号集合（元素为字符串形式的 citation id）。

    Returns:
        过滤后的文本；未知编号的 `[N]` 整段替换为空字符串。
    """
    def replace_match(match: re.Match[str]) -> str:
        citation_id = match.group("value").strip()
        if citation_id in available_ids:
            return f"[{citation_id}]"
        return ""

    return INLINE_NUMBER_PATTERN.sub(replace_match, answer_text)


def _as_evidence_id(item: dict[str, object]) -> str | None:
    """读取证据项的 `evidence_id` 字段（缺失或空白时为 `None`）。

    Args:
        item: 证据项字典。

    Returns:
        非空 `evidence_id` 字符串；为 `None` 时表示该证据不应被编号引用。
    """
    value = item.get("evidence_id")
    if not isinstance(value, str):
        return None
    evidence_id = value.strip()
    return evidence_id or None


def _build_citation_map(evidence_items: list[dict[str, object]]) -> dict[str, str]:
    """按列表顺序把 `evidence_items` 映射成 citation id 字典。

    Args:
        evidence_items: 上游注入的证据字典列表。

    Returns:
        `citation_id -> evidence_id` 字典；缺 ID 的项被跳过。
    """
    citation_map: dict[str, str] = {}
    for index, item in enumerate(evidence_items, start=1):
        evidence_id = _as_evidence_id(item)
        if evidence_id is not None:
            source_number = _source_number(item, index)
            segment_anchor_ids = _segment_anchor_ids(item.get("segments"))
            if not segment_anchor_ids:
                citation_map[str(source_number)] = evidence_id
            for anchor_id in segment_anchor_ids:
                citation_map[anchor_id] = evidence_id
    return citation_map


def _source_number(item: dict[str, object], fallback: int) -> int:
    value = item.get("source_number")
    if isinstance(value, int) and value > 0:
        return value
    return fallback


def _segment_anchor_ids(raw_segments: object) -> list[str]:
    if not isinstance(raw_segments, list):
        return []
    anchor_ids: list[str] = []
    for segment in raw_segments:
        if not isinstance(segment, dict):
            continue
        anchor_id = segment.get("anchor_id")
        if isinstance(anchor_id, str) and re.fullmatch(r"\d+\.\d+", anchor_id.strip()):
            anchor_ids.append(anchor_id.strip())
    return anchor_ids
