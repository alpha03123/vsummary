"""AI 概况完成后按配置生成附加制品。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from backend.core.metering import bind_operation_id, current_operation_id

LOGGER = logging.getLogger(__name__)
_LABELS = {"mindmap": "思维导图", "knowledge_cards": "知识卡片"}


class AutoGenerateVideoArtifacts:
    """根据当前设置补齐导图和知识卡片。

    附加制品失败不应回滚已经生成的 AI 概况，因此逐项记录错误并继续执行。
    """

    def __init__(
        self,
        *,
        load_enabled_artifacts: Callable[[], tuple[str, ...]],
        generate_mindmap: Callable[[str, str], Awaitable[object]],
        generate_knowledge_cards: Callable[[str, str], Awaitable[object]],
        requires_visual_evidence: Callable[[str], bool] | None = None,
        wait_for_visual_evidence: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._load_enabled_artifacts = load_enabled_artifacts
        self._generate_mindmap = generate_mindmap
        self._generate_knowledge_cards = generate_knowledge_cards
        self._requires_visual_evidence = requires_visual_evidence or (lambda _artifact: False)
        self._wait_for_visual_evidence = wait_for_visual_evidence

    async def run(self, series_id: str, video_id: str, *, on_progress: Callable[[str, str], None] | None = None) -> list[str]:
        """Generate the enabled artifacts side by side; both are LLM-bound, so they overlap fully."""
        artifacts = [artifact for artifact in self._load_enabled_artifacts() if artifact in _LABELS]
        failed: list[str] = []
        if any(self._requires_visual_evidence(artifact) for artifact in artifacts):
            try:
                if self._wait_for_visual_evidence is None:
                    raise RuntimeError("自动生成的标准画面输入未配置视觉证据等待器。")
                await self._wait_for_visual_evidence(series_id, video_id)
            except Exception:
                LOGGER.exception("visual evidence for auto-generated artifacts failed for %s/%s", series_id, video_id)
                failed = [artifact for artifact in artifacts if self._requires_visual_evidence(artifact)]
        pending = [artifact for artifact in artifacts if artifact not in failed]

        def report() -> None:
            if on_progress is not None and pending:
                on_progress("auto_artifacts", "正在生成" + "和".join(_LABELS[artifact] for artifact in pending))

        async def generate(artifact: str) -> None:
            operation_id = current_operation_id()
            try:
                with bind_operation_id(f"{operation_id}:{artifact}" if operation_id else None):
                    if artifact == "mindmap":
                        await self._generate_mindmap(series_id, video_id)
                    else:
                        await self._generate_knowledge_cards(series_id, video_id)
            except Exception:
                LOGGER.exception("auto-generated %s failed for %s/%s", artifact, series_id, video_id)
                failed.append(artifact)
            finally:
                pending.remove(artifact)
                report()

        report()
        await asyncio.gather(*(generate(artifact) for artifact in list(pending)))
        return [artifact for artifact in artifacts if artifact in failed]
