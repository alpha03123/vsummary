"""基于 LiteLLM 的知识卡片生成适配器。

把视频的 `summary_data` 提炼为一组结构化知识卡片（含标签、关键词与相关
卡片关联），并提供"按配置懒加载网关"的便捷封装，便于在后台线程中复用。
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, Field

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.infrastructure.video_summary_runtime import build_litellm_completion_gateway
from backend.video_summary.infrastructure.config.settings import ensure_settings_file, load_settings
from backend.video_summary.infrastructure.llm.prompts import KNOWLEDGE_CARD_PROMPT_TEMPLATE
from backend.video_summary.library.models import KnowledgeCardDTO


class KnowledgeCardPayload(BaseModel):
    """LLM 返回的单张知识卡片原始结构。

    字段与最终 `KnowledgeCardDTO` 接近，但保留 LLM 可能给出的原始字符串；
    后续清洗阶段会做去空白、限长、关联补全等处理。
    """

    id: str
    title: str
    kind: str
    summary: str
    details: str
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class KnowledgeCardCollectionPayload(BaseModel):
    """LLM 返回的"卡片集合"顶层结构，承载一组 `KnowledgeCardPayload`。"""

    cards: list[KnowledgeCardPayload] = Field(default_factory=list)


class LiteLLMKnowledgeCardGenerator:
    """通过 LiteLLM 同步调用 LLM 生成知识卡片的实现。

    业务场景：在系列知识记忆刷新钩子中，需要基于单个视频的总结数据提炼
    出可供检索/复习的"知识卡片"，并按标签建立卡片间的关联。

    实现要点：
    - 提示词构造：把 `title` / `summary_data`（JSON）注入
      `KNOWLEDGE_CARD_PROMPT_TEMPLATE` 模板；
    - 输出约束：使用 `KnowledgeCardCollectionPayload` Pydantic schema
      强制 LLM 输出结构，失败时由网关层最多重试 3 次；
    - 错误处理：解析失败、schema 不匹配等异常由网关层抛出，本类不做静默
      兜底；仅对"内容字段全部为空"的卡片做过滤；
    - 后处理：标签/关键词去重并限长，按标签共现补全 `related_card_ids`。
    """

    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        """注入 LiteLLM 网关实例。

        Args:
            gateway: 提供 `complete_structured` 能力的 LLM 网关（同步版本）。
        """
        self._gateway = gateway

    def run(self, *, title: str, summary_data: dict[str, object]) -> list[KnowledgeCardDTO]:
        """根据总结数据生成一批清洗后的知识卡片。

        Args:
            title: 视频标题，用于在提示词中给 LLM 上下文。
            summary_data: 已生成的总结数据字典，会被 JSON 序列化后注入提示词。

        Returns:
            经过空白裁剪、去重限长、关联补全后的 `KnowledgeCardDTO` 列表；
            原始 LLM 输出中"必填字段全空"的卡片会被过滤掉。

        Raises:
            RuntimeError: LLM 返回无法通过 schema 校验且重试仍失败时抛出。
        """
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
    """带配置缓存的知识卡片生成器。

    业务目的：让"系列知识记忆刷新"这种后台线程场景不必每次重新构造
    `LiteLLMCompletionGateway`，而是按 `settings.toml` + `.env` 的签名复用
    上一次构建好的网关；只要配置未变更就返回同一个生成器实例。
    """

    def __init__(self, root_dir: Path) -> None:
        """注入项目根目录，并据此定位 `settings.toml` 与 `.env`。

        Args:
            root_dir: 项目根目录（包含 `config/settings.toml` 与 `.env`）。
        """
        self._root_dir = root_dir
        self._config_path = root_dir / "config" / "settings.toml"
        self._dotenv_path = root_dir / ".env"
        self._generator_lock = Lock()
        self._cached_signature: tuple[str, str] | None = None
        self._cached_generator: LiteLLMKnowledgeCardGenerator | None = None

    def run(self, *, title: str, summary_data: dict[str, object]) -> list[KnowledgeCardDTO]:
        """获取（或复用缓存的）知识卡片生成器并运行一次。

        Args:
            title: 视频标题。
            summary_data: 已生成的总结数据字典。

        Returns:
            与 `LiteLLMKnowledgeCardGenerator.run` 同义的 `KnowledgeCardDTO` 列表。
        """
        generator = self._get_generator()
        return generator.run(title=title, summary_data=summary_data)

    def _get_generator(self) -> LiteLLMKnowledgeCardGenerator:
        """读取配置文件签名并按需重建/复用生成器。

        Returns:
            当前可用的 `LiteLLMKnowledgeCardGenerator` 实例。
        """
        ensure_settings_file(self._config_path)
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
    """渲染知识卡片提示词模板。

    Args:
        title: 视频标题。
        summary_data: 总结数据字典，使用 `ensure_ascii=False` 以保留中文。

    Returns:
        渲染完成的提示词字符串。
    """
    return KNOWLEDGE_CARD_PROMPT_TEMPLATE.format(
        title=title,
        summary_json=json.dumps(summary_data, ensure_ascii=False, indent=2),
    )


def _is_valid_card(card: KnowledgeCardPayload) -> bool:
    """校验一张卡片是否包含全部必要字段（去空白后非空）。"""
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
    """对一组字符串去空白、去重并按上限截断。

    Args:
        values: 原始字符串列表（可能含空串、重复或多余元素）。
        limit: 最多保留多少条。

    Returns:
        清洗后的字符串列表，顺序保持输入首次出现的位置。
    """
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
    """根据标签共现为每张卡片补全 `related_card_ids`（最多 6 个）。

    算法：先以标签为键建倒排索引（同一标签下出现的所有卡片 ID），再为每张
    卡片找出"共享至少一个标签"的其他卡片，按遍历顺序截断到 6 个。

    Args:
        cards: 已清洗字段的卡片列表。

    Returns:
        填充好 `related_card_ids` 的新卡片列表（不复用入参对象）。
    """
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
