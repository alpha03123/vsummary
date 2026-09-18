"""AI 概况完成后按配置生成附加制品。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

LOGGER = logging.getLogger(__name__)


class AutoGenerateVideoArtifacts:
    """根据当前设置补齐导图和知识卡片。

    附加制品失败不应回滚已经生成的 AI 概况，因此逐项记录错误并继续执行。
    """

    def __init__(
        self,
        *,
        load_enabled_artifacts: Callable[[], tuple[str, ...]],
        generate_mindmap: Callable[[str, str], Awaitable[object]],
        generate_knowledge_cards: Callable[[str, str], object],
        requires_visual_evidence: Callable[[str], bool] | None = None,
        wait_for_visual_evidence: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._load_enabled_artifacts = load_enabled_artifacts
        self._generate_mindmap = generate_mindmap
        self._generate_knowledge_cards = generate_knowledge_cards
        self._requires_visual_evidence = requires_visual_evidence or (lambda _artifact: False)
        self._wait_for_visual_evidence = wait_for_visual_evidence

    async def run(self, series_id: str, video_id: str) -> None:
        visual_evidence_ready = False
        for artifact in self._load_enabled_artifacts():
            try:
                if self._requires_visual_evidence(artifact) and not visual_evidence_ready:
                    if self._wait_for_visual_evidence is None:
                        raise RuntimeError("自动生成的标准画面输入未配置视觉证据等待器。")
                    await self._wait_for_visual_evidence(series_id, video_id)
                    visual_evidence_ready = True
                if artifact == "mindmap":
                    await self._generate_mindmap(series_id, video_id)
                elif artifact == "knowledge_cards":
                    await asyncio.to_thread(self._generate_knowledge_cards, series_id, video_id)
            except Exception:
                LOGGER.exception("auto-generated %s failed for %s/%s", artifact, series_id, video_id)
