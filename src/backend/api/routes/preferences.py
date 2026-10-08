"""Only hosts opting into a preference store expose user override controls."""
from fastapi import APIRouter, Depends, HTTPException
from backend.api.di.container import ApiContainerDep
from backend.api.dependencies import get_workspace_context
from backend.core.context import WorkspaceContext
from backend.core.preferences import USER_OVERRIDABLE, UserPreferences
from backend.video_summary.infrastructure.config.user_preferences import resolve_user_settings
from backend.video_summary.infrastructure.config.settings import load_settings

router = APIRouter()


def _store(container):
    if container.preference_store is None:
        raise HTTPException(status_code=404, detail="User preference overrides are not enabled in this host.")
    return container.preference_store


@router.get("/api/preferences")
def get_preferences(container: ApiContainerDep, context: WorkspaceContext = Depends(get_workspace_context)):
    overrides = _store(container).get(context)
    effective = resolve_user_settings(load_settings(container.config_path, container.root_dir), overrides, container.model_profiles)
    return {"overrides": overrides, "effective": {
        "ai_summary_multimodal_enabled": effective.generation.ai_summary_multimodal_enabled,
        "auto_generate_artifacts": list(effective.generation.auto_generate_artifacts),
        "answer_detail_level": effective.agent_context.answer_detail_level,
        "model_profile": overrides.get("model_profile"),
    }, "overridable": sorted(USER_OVERRIDABLE), "model_profiles": list(container.model_profiles)}


@router.put("/api/preferences")
def update_preferences(values: UserPreferences, container: ApiContainerDep, context: WorkspaceContext = Depends(get_workspace_context)):
    payload = values.model_dump(exclude_none=True)
    try:
        resolve_user_settings(load_settings(container.config_path, container.root_dir), payload, container.model_profiles)
        _store(container).update(context, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return get_preferences(container, context)
