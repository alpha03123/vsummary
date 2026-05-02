from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, Field

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.infrastructure.runtime import build_litellm_completion_gateway
from backend.video_summary.infrastructure.settings import load_settings
from backend.video_summary.library.models import KnowledgeCardDTO


class KnowledgeCardPayload(BaseModel):
    id: str
    title: str
    kind: str
    summary: str
    details: str
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class KnowledgeCardCollectionPayload(BaseModel):
    cards: list[KnowledgeCardPayload] = Field(default_factory=list)


class LiteLLMKnowledgeCardGenerator:
    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        self._gateway = gateway

    def run(self, *, title: str, summary_data: dict[str, object]) -> list[KnowledgeCardDTO]:
        prompt = build_knowledge_card_prompt(title=title, summary_data=summary_data)
        payload = self._gateway.complete_structured(
            [{"role": "user", "content": prompt}],
            response_model=KnowledgeCardCollectionPayload,
            retries=3,
        )
        cards = [
            KnowledgeCardDTO(
                id=card.id.strip(),
                title=card.title.strip(),
                kind=card.kind.strip(),
                summary=card.summary.strip(),
                details=card.details.strip(),
                tags=_dedupe_texts(card.tags, limit=4),
                keywords=_dedupe_texts(card.keywords, limit=8),
                related_card_ids=[],
            )
            for card in payload.cards
            if _is_valid_card(card)
        ]
        return _attach_related_card_ids(cards)


class ConfiguredKnowledgeCardGenerator:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._config_path = root_dir / "config" / "settings.toml"
        self._dotenv_path = root_dir / ".env"
        self._generator_lock = Lock()
        self._cached_signature: tuple[str, str] | None = None
        self._cached_generator: LiteLLMKnowledgeCardGenerator | None = None

    def run(self, *, title: str, summary_data: dict[str, object]) -> list[KnowledgeCardDTO]:
        generator = self._get_generator()
        return generator.run(title=title, summary_data=summary_data)

    def _get_generator(self) -> LiteLLMKnowledgeCardGenerator:
        signature = (
            self._config_path.read_text(encoding="utf-8"),
            self._dotenv_path.read_text(encoding="utf-8") if self._dotenv_path.exists() else "",
        )
        with self._generator_lock:
            if self._cached_generator is None or self._cached_signature != signature:
                settings = load_settings(config_path=self._config_path, root_dir=self._root_dir)
                gateway = build_litellm_completion_gateway(settings)
                self._cached_generator = LiteLLMKnowledgeCardGenerator(gateway)
                self._cached_signature = signature
            return self._cached_generator


def build_knowledge_card_prompt(*, title: str, summary_data: dict[str, object]) -> str:
    return (
        "请根据以下视频结构化概况，生成适合复习记忆的知识卡片 JSON。\n"
        "这些卡片的目标不是章节摘要，而是筛选出真正值得长期记住、可脱离视频独立理解的知识资产。\n"
        "允许三类内容：核心概念（concept）、方法论（method）、反常识洞见（insight）。\n\n"
        "要求：\n"
        "1. 只输出 JSON，不要输出额外解释。\n"
        "2. 优先产出 3 到 8 张高价值卡片，但不要为了凑数硬拆概念；如果信息密度很高，可以更多；如果信息不足，可以更少。\n"
        "3. 每张卡只讲一件事，必须是独立可读的短讲义，而不是章节提纲或摘要改写。\n"
        "4. title 使用混合式标题：有稳定术语就用术语；没有稳定术语时，用清晰的结论句。标题尽量简洁。\n"
        "5. kind 只能是 concept、method、insight 之一。\n"
        "6. summary 用 1 到 2 句说明这张卡的核心意思。\n"
        "7. details 写成 80 到 180 字左右的短讲义，补全主语与背景，让没看过视频的人也能看懂。\n"
        "8. 不要写“本章”“这一段”“视频里”“作者接着说”“前面提到”等依赖上下文的话。\n"
        "9. 不要按时间顺序罗列，不要重复生成意思相近的卡片，不要把一个大概念生硬拆成多个废卡。\n"
        "10. tags 和 keywords 只保留高信息量词汇，related_card_ids 不要输出，由系统后处理。\n\n"
        "输出 JSON 结构：\n"
        "{\n"
        '  "cards": [\n'
        "    {\n"
        '      "id": "kc-1",\n'
        '      "title": "卡片标题",\n'
        '      "kind": "concept",\n'
        '      "summary": "1到2句概括",\n'
        '      "details": "80到180字的短讲义正文",\n'
        '      "tags": ["标签1", "标签2"],\n'
        '      "keywords": ["关键词1", "关键词2"]\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"视频标题：{title}\n"
        "结构化概况 JSON：\n"
        f"{json.dumps(summary_data, ensure_ascii=False, indent=2)}\n"
    )


def _is_valid_card(card: KnowledgeCardPayload) -> bool:
    return all(
        (
            card.id.strip(),
            card.title.strip(),
            card.kind.strip(),
            card.summary.strip(),
            card.details.strip(),
        )
    )


def _dedupe_texts(values: list[str], *, limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in result:
            continue
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


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
            related_card_ids=[
                candidate_id
                for tag in card.tags
                for candidate_id in tag_index.get(tag, [])
                if candidate_id != card.id
            ][:6],
        )
        for card in cards
    ]
