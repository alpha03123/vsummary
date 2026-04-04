from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.infrastructure.faster_whisper_models import FasterWhisperModelManager
from backend.video_summary.infrastructure.settings import (
    EnvSettings,
    VALID_THEMES,
    VALID_TRANSCRIPTION_MODES,
    WorkspaceUiSettings,
    load_env_settings,
    load_settings,
    replace_faster_whisper_model_size,
    replace_faster_whisper_transcription_mode,
    replace_openai_settings,
    replace_workspace_ui_settings,
    save_env_settings,
    save_settings,
)


class SettingsValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderSettings:
    llm_provider: str
    openai_base_url: str
    openai_model: str
    openai_api_key: str


@dataclass(frozen=True)
class ProviderSettingsUpdate:
    llm_provider: str
    openai_base_url: str
    openai_model: str
    openai_api_key: str


@dataclass(frozen=True)
class WorkspaceSettings:
    theme: str
    show_takeaways: bool
    ai_transcript_enhancement: bool
    asr_model_quality: str
    transcription_mode: str
    llm_provider: str
    openai_base_url: str
    openai_model: str


@dataclass(frozen=True)
class WorkspaceSettingsUpdate:
    theme: str
    show_takeaways: bool
    ai_transcript_enhancement: bool
    asr_model_quality: str
    transcription_mode: str
    llm_provider: str
    openai_base_url: str
    openai_model: str


class ApiSettingsService:
    def __init__(
        self,
        *,
        config_path: Path,
        root_dir: Path,
        faster_whisper_model_manager: FasterWhisperModelManager,
    ) -> None:
        self._config_path = config_path
        self._root_dir = root_dir
        self._faster_whisper_model_manager = faster_whisper_model_manager

    def get_workspace_settings(self) -> WorkspaceSettings:
        settings = load_settings(self._config_path, self._root_dir)
        return WorkspaceSettings(
            theme=settings.workspace_ui.theme,
            show_takeaways=settings.workspace_ui.show_takeaways,
            ai_transcript_enhancement=settings.workspace_ui.ai_transcript_enhancement,
            asr_model_quality=settings.asr.faster_whisper.model_size,
            transcription_mode=settings.asr.faster_whisper.transcription_mode,
            llm_provider=settings.openai.provider,
            openai_base_url=settings.openai.base_url,
            openai_model=settings.openai.model,
        )

    def update_workspace_settings(self, request: WorkspaceSettingsUpdate) -> WorkspaceSettings:
        if request.theme not in VALID_THEMES:
            raise SettingsValidationError(f"unsupported theme '{request.theme}'")
        if not self._faster_whisper_model_manager.is_supported(request.asr_model_quality):
            raise SettingsValidationError(f"unsupported asr model '{request.asr_model_quality}'")
        if request.transcription_mode not in VALID_TRANSCRIPTION_MODES:
            raise SettingsValidationError(f"unsupported transcription mode '{request.transcription_mode}'")

        provider_settings = self._validate_provider_settings(
            llm_provider=request.llm_provider,
            openai_base_url=request.openai_base_url,
            openai_model=request.openai_model,
            openai_api_key=load_env_settings(self._root_dir).api_key,
        )

        current_settings = load_settings(self._config_path, self._root_dir)
        next_settings = replace_workspace_ui_settings(
            current_settings,
            WorkspaceUiSettings(
                theme=request.theme,
                show_takeaways=request.show_takeaways,
                ai_transcript_enhancement=request.ai_transcript_enhancement,
            ),
        )
        next_settings = replace_faster_whisper_model_size(next_settings, request.asr_model_quality)
        next_settings = replace_faster_whisper_transcription_mode(next_settings, request.transcription_mode)
        next_settings = replace_openai_settings(
            next_settings,
            provider=provider_settings.llm_provider,
            base_url=provider_settings.openai_base_url,
            model=provider_settings.openai_model,
        )
        self._save_provider_settings(provider_settings, next_settings)

        return WorkspaceSettings(
            theme=request.theme,
            show_takeaways=request.show_takeaways,
            ai_transcript_enhancement=request.ai_transcript_enhancement,
            asr_model_quality=request.asr_model_quality,
            transcription_mode=request.transcription_mode,
            llm_provider=provider_settings.llm_provider,
            openai_base_url=provider_settings.openai_base_url,
            openai_model=provider_settings.openai_model,
        )

    def get_provider_settings(self) -> ProviderSettings:
        env_settings = load_env_settings(self._root_dir)
        return ProviderSettings(
            llm_provider=env_settings.provider,
            openai_base_url=env_settings.base_url,
            openai_model=env_settings.model,
            openai_api_key=env_settings.api_key,
        )

    def update_provider_settings(self, request: ProviderSettingsUpdate) -> ProviderSettings:
        provider_settings = self._validate_provider_settings(
            llm_provider=request.llm_provider,
            openai_base_url=request.openai_base_url,
            openai_model=request.openai_model,
            openai_api_key=request.openai_api_key,
        )
        current_settings = load_settings(self._config_path, self._root_dir)
        next_settings = replace_openai_settings(
            current_settings,
            provider=provider_settings.llm_provider,
            base_url=provider_settings.openai_base_url,
            model=provider_settings.openai_model,
        )
        self._save_provider_settings(provider_settings, next_settings)
        return provider_settings

    def _validate_provider_settings(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_model: str,
        openai_api_key: str,
    ) -> ProviderSettings:
        normalized_provider = llm_provider.strip()
        normalized_base_url = openai_base_url.strip()
        normalized_model = openai_model.strip()

        if normalized_provider != "openai_compatible":
            raise SettingsValidationError(f"unsupported llm provider '{normalized_provider}'")
        if not normalized_base_url:
            raise SettingsValidationError("openai_base_url is required")
        if not normalized_model:
            raise SettingsValidationError("openai_model is required")

        return ProviderSettings(
            llm_provider=normalized_provider,
            openai_base_url=normalized_base_url,
            openai_model=normalized_model,
            openai_api_key=openai_api_key,
        )

    def _save_provider_settings(self, provider_settings: ProviderSettings, settings) -> None:
        save_settings(self._config_path, settings)
        save_env_settings(
            self._root_dir,
            EnvSettings(
                provider=provider_settings.llm_provider,
                base_url=provider_settings.openai_base_url,
                model=provider_settings.openai_model,
                api_key=provider_settings.openai_api_key,
            ),
        )
