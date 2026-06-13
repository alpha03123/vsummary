from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, Field

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.infrastructure.video_summary_runtime import build_litellm_completion_gateway
from backend.video_summary.infrastructure.settings import load_settings
from backend.video_summary.infrastructure.prompts import KNOWLEDGE_CARD_PROMPT_TEMPLATE
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
    return KNOWLEDGE_CARD_PROMPT_TEMPLATE.format(
        title=title,
        summary_json=json.dumps(summary_data, ensure_ascii=False, indent=2),
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
