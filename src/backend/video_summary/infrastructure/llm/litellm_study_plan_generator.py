"""基于 LiteLLM 的学习计划文案生成器：给已切好的每一课写标题、目标、重点和练习。"""

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
from backend.video_summary.infrastructure.llm.prompts.study_plan import STUDY_PLAN_PROMPT_TEMPLATE
from backend.video_summary.infrastructure.video_summary_runtime import build_litellm_completion_gateway


class StudySessionCopy(BaseModel):
    index: int
    title: str = ""
    goal: str = ""
    focus: list[str] = Field(default_factory=list)
    practice: list[str] = Field(default_factory=list)


class StudyPlanCopy(BaseModel):
    overview: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    sessions: list[StudySessionCopy] = Field(default_factory=list)


def build_study_plan_prompt(*, title: str, context: str, daily_minutes: int, sessions: list[dict]) -> str:
    return STUDY_PLAN_PROMPT_TEMPLATE.format(
        daily_minutes=daily_minutes,
        session_count=len(sessions),
        title=title,
        context=context,
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

    async def arun(self, *, title: str, context: str, daily_minutes: int, sessions: list[dict]) -> StudyPlanCopy:
        prompt = build_study_plan_prompt(title=title, context=context, daily_minutes=daily_minutes, sessions=sessions)
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
