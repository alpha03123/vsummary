"""Apply request-scoped user preferences to deployment settings."""

from dataclasses import replace
from typing import Mapping

from backend.core.preferences import (
    USER_OVERRIDABLE, UserPreferences, current_preferences, current_model_profiles,
)
from backend.video_summary.infrastructure.config.settings import AppSettings, load_settings


def resolve_user_settings(base: AppSettings, values: Mapping, model_profiles: Mapping[str, str] | None = None) -> AppSettings:
    selected = UserPreferences.model_validate(dict(values)).model_dump(exclude_none=True)
    if not set(selected) <= USER_OVERRIDABLE:
        raise ValueError("Preference is not user-overridable.")
    generation = {}
    if "ai_summary_multimodal_enabled" in selected:
        generation["ai_summary_multimodal_enabled"] = selected["ai_summary_multimodal_enabled"]
    if "auto_generate_artifacts" in selected:
        generation["auto_generate_artifacts"] = tuple(selected["auto_generate_artifacts"])
    multimodal = selected.get("ai_summary_multimodal_enabled", base.generation.ai_summary_multimodal_enabled)
    generation["chapter_visual_mode"] = "screenshots" if multimodal else "off"
    generation["note_visual_mode"] = "screenshots" if multimodal else "off"
    if not multimodal:
        generation["mindmap_visual_input"] = "none"
        generation["cards_visual_input"] = "none"
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
    base = load_settings(config_path, root_dir)
    values = current_preferences()
    return resolve_user_settings(base, values, current_model_profiles()) if values is not None else base
