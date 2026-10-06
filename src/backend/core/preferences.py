"""Opt-in user overrides. Deployment configuration is never written by this layer."""

from __future__ import annotations

from typing import Protocol, Mapping, TYPE_CHECKING
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
import json

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

from backend.core.context import WorkspaceContext

if TYPE_CHECKING:
    from backend.video_summary.infrastructure.config.settings import AppSettings

USER_OVERRIDABLE = frozenset({
    "ai_summary_multimodal_enabled", "auto_generate_artifacts", "answer_detail_level", "model_profile",
})


class UserPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ai_summary_multimodal_enabled: StrictBool | None = None
    auto_generate_artifacts: list[str] | None = None
    answer_detail_level: str | None = None
    model_profile: str | None = None

    @field_validator("answer_detail_level")
    @classmethod
    def answer_level(cls, value):
        from backend.video_summary.infrastructure.config.settings import VALID_ANSWER_DETAIL_LEVELS
        if value is not None and value not in VALID_ANSWER_DETAIL_LEVELS:
            raise ValueError("Unsupported answer detail level.")
        return value

    @field_validator("auto_generate_artifacts")
    @classmethod
    def artifacts(cls, value):
        from backend.video_summary.infrastructure.config.settings import VALID_AUTO_GENERATE_ARTIFACTS
        if value is not None and (len(value) != len(set(value)) or not set(value) <= VALID_AUTO_GENERATE_ARTIFACTS):
            raise ValueError("Unsupported or duplicate automatic artifact.")
        return value

    @field_validator("model_profile")
    @classmethod
    def profile(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Model profile must not be empty.")
        return value


_overrides: ContextVar[dict | None] = ContextVar("user_preference_overrides", default=None)
_models: ContextVar[Mapping[str, str]] = ContextVar("user_model_profiles", default={})


def current_preferences() -> dict | None:
    value = _overrides.get()
    return dict(value) if value is not None else None


def preference_cache_key() -> str:
    return json.dumps(current_preferences(), sort_keys=True)


@contextmanager
def bind_user_preferences(values: Mapping | None, model_profiles: Mapping[str, str] | None = None):
    validated = UserPreferences.model_validate(dict(values)).model_dump(exclude_none=True) if values is not None else None
    profiles = dict(model_profiles or {})
    if validated is not None and validated.get("model_profile") is not None and validated["model_profile"] not in profiles:
        raise ValueError("The selected model profile is not configured by the host.")
    preference_token = _overrides.set(validated)
    model_token = _models.set(profiles)
    try:
        yield
    finally:
        _models.reset(model_token)
        _overrides.reset(preference_token)


def resolve_user_settings(base: AppSettings, values: Mapping, model_profiles: Mapping[str, str] | None = None) -> AppSettings:
    selected = UserPreferences.model_validate(dict(values)).model_dump(exclude_none=True)
    if not set(selected) <= USER_OVERRIDABLE:
        raise ValueError("Preference is not user-overridable.")
    generation = {}
    if "ai_summary_multimodal_enabled" in selected:
        generation["ai_summary_multimodal_enabled"] = selected["ai_summary_multimodal_enabled"]
    if "auto_generate_artifacts" in selected:
        generation["auto_generate_artifacts"] = tuple(selected["auto_generate_artifacts"])
    result = replace(base, generation=replace(base.generation, **generation)) if generation else base
    if "answer_detail_level" in selected:
        result = replace(result, agent_context=replace(result.agent_context, answer_detail_level=selected["answer_detail_level"]))
    if "model_profile" in selected:
        profiles = model_profiles or {}
        profile = selected["model_profile"]
        if profile not in profiles:
            raise ValueError("The selected model profile is not configured by the host.")
        result = replace(result, openai=replace(result.openai, model=profiles[profile]))
    return result


def load_effective_settings(config_path, root_dir):
    from backend.video_summary.infrastructure.config.settings import load_settings
    base = load_settings(config_path, root_dir)
    values = current_preferences()
    return resolve_user_settings(base, values, _models.get()) if values is not None else base


class UserPreferenceStore(Protocol):
    def get(self, context: WorkspaceContext) -> dict[str, object]: ...

    def update(self, context: WorkspaceContext, values: dict[str, object]) -> dict[str, object]: ...
