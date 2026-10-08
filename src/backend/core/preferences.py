"""Opt-in user overrides. Deployment configuration is never written by this layer."""

from __future__ import annotations

from typing import Protocol, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
import json

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

from backend.core.context import WorkspaceContext

VALID_ANSWER_DETAIL_LEVELS = frozenset({"short", "medium", "long"})
VALID_AUTO_GENERATE_ARTIFACTS = frozenset({"mindmap", "knowledge_cards"})

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
        if value is not None and value not in VALID_ANSWER_DETAIL_LEVELS:
            raise ValueError("Unsupported answer detail level.")
        return value

    @field_validator("auto_generate_artifacts")
    @classmethod
    def artifacts(cls, value):
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


def current_model_profiles() -> dict[str, str]:
    return dict(_models.get())


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


class UserPreferenceStore(Protocol):
    def get(self, context: WorkspaceContext) -> dict[str, object]: ...

    def update(self, context: WorkspaceContext, values: dict[str, object]) -> dict[str, object]: ...
