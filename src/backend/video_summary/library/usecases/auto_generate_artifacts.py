"""AI 概况完成后按配置生成附加制品。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

LOGGER = logging.getLogger(__name__)


class AutoGenerateVideoArtifacts:
    """根据当前设置补齐导图、知识卡片和笔记。

    附加制品失败不应回滚已经生成的 AI 概况，因此逐项记录错误并继续执行。
    """

    def __init__(
        self,
        *,
        load_enabled_artifacts: Callable[[], tuple[str, ...]],
        generate_mindmap: Callable[[str, str], Awaitable[object]],
        generate_knowledge_cards: Callable[[str, str], object],
        generate_note: Callable[[str, str], object],
    ) -> None:
        self._load_enabled_artifacts = load_enabled_artifacts
        self._generate_mindmap = generate_mindmap
        self._generate_knowledge_cards = generate_knowledge_cards
        self._generate_note = generate_note

    async def run(self, series_id: str, video_id: str) -> None:
        for artifact in self._load_enabled_artifacts():
            try:
                if artifact == "mindmap":
                    await self._generate_mindmap(series_id, video_id)
                elif artifact == "knowledge_cards":
                    await asyncio.to_thread(self._generate_knowledge_cards, series_id, video_id)
                elif artifact == "notes":
                    await asyncio.to_thread(self._generate_note, series_id, video_id)
            except Exception:
                LOGGER.exception("auto-generated %s failed for %s/%s", artifact, series_id, video_id)
