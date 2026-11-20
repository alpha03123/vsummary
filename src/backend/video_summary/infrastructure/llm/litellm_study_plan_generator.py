"""基于 LiteLLM 的学习计划生成器：排课并写每课内容，或为代码切好的课只写内容。"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, Field

from backend.core.preferences import preference_cache_key
from backend.shared.llm import LiteLLMCompletionGateway
from backend.shared.llm.usage import LlmUsageCategory, LlmUsageRecorder
from backend.video_summary.infrastructure.config.settings import ensure_settings_file
from backend.video_summary.infrastructure.config.user_preferences import load_effective_settings
from backend.video_summary.infrastructure.llm.prompts.study_plan import (
    STUDY_PLAN_COPY_PROMPT_TEMPLATE,
    STUDY_PLAN_PROMPT_TEMPLATE,
)
from backend.video_summary.infrastructure.video_summary_runtime import build_litellm_completion_gateway


class StudySessionCopy(BaseModel):
    index: int = 0
    chapters: list[str] = Field(default_factory=list)
    title: str = ""
    goal: str = ""
    focus: list[str] = Field(default_factory=list)
    practice: list[str] = Field(default_factory=list)
    practice_minutes: int = 0


class StudyPlanCopy(BaseModel):
    overview: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    sessions: list[StudySessionCopy] = Field(default_factory=list)


def _context_block(context: str) -> str:
    return f"{context.strip()}\n" if context.strip() else ""


def build_study_plan_prompt(*, title: str, context: str, daily_minutes: int, videos: list[dict]) -> str:
    return STUDY_PLAN_PROMPT_TEMPLATE.format(
        daily_minutes=daily_minutes,
        max_minutes=round(daily_minutes * 1.3),
        title=title,
        context=_context_block(context),
        videos_json=json.dumps(videos, ensure_ascii=False, indent=1),
    )


def build_study_plan_copy_prompt(*, title: str, context: str, daily_minutes: int, sessions: list[dict]) -> str:
    return STUDY_PLAN_COPY_PROMPT_TEMPLATE.format(
        daily_minutes=daily_minutes,
        session_count=len(sessions),
        title=title,
        context=_context_block(context),
        sessions_json=json.dumps(sessions, ensure_ascii=False, indent=1),
    )


class ConfiguredStudyPlanGenerator:
    """按当前设置构建（并缓存）LLM 网关，生成学习计划文案。"""

    def __init__(self, root_dir: Path, usage_recorder: LlmUsageRecorder | None = None) -> None:
        self._root_dir = root_dir
        self._usage_recorder = usage_recorder
        self._config_path = root_dir / "config" / "settings.toml"
        self._dotenv_path = root_dir / ".env"
        self._lock = Lock()
        self._cached_signature: tuple[object, ...] | None = None
        self._cached_gateway: LiteLLMCompletionGateway | None = None

    async def aplan(self, *, title: str, context: str, daily_minutes: int, videos: list[dict]) -> StudyPlanCopy:
        prompt = build_study_plan_prompt(title=title, context=context, daily_minutes=daily_minutes, videos=videos)
        return await self._complete(prompt)

    async def acopy(self, *, title: str, context: str, daily_minutes: int, sessions: list[dict]) -> StudyPlanCopy:
        prompt = build_study_plan_copy_prompt(title=title, context=context, daily_minutes=daily_minutes, sessions=sessions)
        return await self._complete(prompt)

    async def _complete(self, prompt: str) -> StudyPlanCopy:
        return await self._gateway().acomplete_structured(
            [{"role": "user", "content": prompt}], response_model=StudyPlanCopy, retries=3)

    def _gateway(self) -> LiteLLMCompletionGateway:
        ensure_settings_file(self._config_path)
        signature = (
            preference_cache_key(),
            self._config_path.read_text(encoding="utf-8"),
            self._dotenv_path.read_text(encoding="utf-8") if self._dotenv_path.exists() else "",
        )
        with self._lock:
            if self._cached_gateway is None or self._cached_signature != signature:
                settings = load_effective_settings(config_path=self._config_path, root_dir=self._root_dir)
                self._cached_gateway = build_litellm_completion_gateway(
                    settings,
                    usage_recorder=self._usage_recorder,
                    usage_category=LlmUsageCategory.GENERATION if self._usage_recorder is not None else None,
                )
                self._cached_signature = signature
            return self._cached_gateway
