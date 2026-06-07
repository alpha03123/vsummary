from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol

from backend.video_summary.infrastructure.faster_whisper_models import FasterWhisperModelManager
from backend.video_summary.infrastructure.rag_models import RAG_RERANKER_REQUIRED_MESSAGE, RagModelManager
from backend.video_summary.infrastructure.settings import (
    EnvSettings,
    VALID_THEMES,
    VALID_TRANSCRIPTION_MODES,
    VALID_ANSWER_DETAIL_LEVELS,
    VALID_LLM_PROVIDERS,
    VALID_REASONING_EFFORTS,
    WorkspaceUiSettings,
    load_env_settings,
    load_settings,
    normalize_openai_base_url,
    replace_agent_retrieval_runtime_settings,
    replace_agent_context_window_tokens,
    replace_agent_context_answer_detail_level,
    replace_agent_context_reasoning_effort,
    replace_faster_whisper_model_size,
    replace_faster_whisper_transcription_mode,
    replace_transcript_enhancement_enabled,
    replace_chaoxing_import_settings,
    replace_video_generation_concurrency,
    replace_web_search_enabled,
    replace_workspace_ui_settings,
    save_env_settings,
    save_settings,
)
from backend.shared.llm import LiteLLMCompletionGateway


class SettingsValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderSettings:
    llm_provider: str
    openai_base_url: str
    openai_model: str
    has_openai_api_key: bool
    openai_api_key_masked: str
    hf_endpoint: str


@dataclass(frozen=True)
class WorkspaceSettings:
    theme: str
    show_takeaways: bool
    transcript_enhancement_enabled: bool
    asr_model_quality: str
    transcription_mode: str
    rag_embedding_device: str
    rag_max_hits: int
    rag_rerank_enabled: bool
    window_tokens: int
    answer_detail_level: str
    reasoning_effort: str
    video_generation_concurrency: int
    web_search_enabled: bool
    chaoxing_request_delay_seconds: float
    chaoxing_init_course_delay_seconds: float


class SettingsServicePort(Protocol):
    def get_workspace_settings(self) -> WorkspaceSettings:
        ...

    def update_workspace_settings(
        self,
        *,
        theme: str,
        show_takeaways: bool,
        transcript_enhancement_enabled: bool,
        asr_model_quality: str,
        transcription_mode: str,
        rag_embedding_device: str,
        rag_max_hits: int,
        rag_rerank_enabled: bool,
        window_tokens: int,
        answer_detail_level: str,
        reasoning_effort: str,
        video_generation_concurrency: int,
        web_search_enabled: bool,
        chaoxing_request_delay_seconds: float = 0.2,
        chaoxing_init_course_delay_seconds: float = 0.3,
    ) -> WorkspaceSettings:
        ...

    def get_provider_settings(self) -> ProviderSettings:
        ...

    def get_openai_api_key(self) -> str:
        ...

    def update_provider_settings(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_model: str,
        openai_api_key: str | None,
        hf_endpoint: str | None,
    ) -> ProviderSettings:
        ...

    def test_provider_settings(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_model: str,
        openai_api_key: str | None,
        hf_endpoint: str | None,
    ) -> str:
        ...


class SettingsService:
    def __init__(
        self,
        *,
        config_path: Path,
        root_dir: Path,
        faster_whisper_model_manager: FasterWhisperModelManager,
        rag_model_manager: RagModelManager | None = None,
    ) -> None:
        self._config_path = config_path
        self._root_dir = root_dir
        self._faster_whisper_model_manager = faster_whisper_model_manager
        self._rag_model_manager = rag_model_manager
        self._settings_lock = Lock()

    def get_workspace_settings(self) -> WorkspaceSettings:
        settings = load_settings(self._config_path, self._root_dir)
        rag_rerank_enabled = settings.agent_retrieval.rerank_enabled and (
            self._rag_model_manager is None or self._rag_model_manager.is_downloaded("reranker")
        )
        return WorkspaceSettings(
            theme=settings.workspace_ui.theme,
            show_takeaways=settings.workspace_ui.show_takeaways,
            transcript_enhancement_enabled=settings.asr.transcript_enhancement_enabled,
            asr_model_quality=settings.asr.faster_whisper.model_size,
            transcription_mode=settings.asr.faster_whisper.transcription_mode,
            rag_embedding_device=settings.agent_retrieval.embedding_device,
            rag_max_hits=settings.agent_retrieval.max_hits,
            rag_rerank_enabled=rag_rerank_enabled,
            window_tokens=settings.agent_context.window_tokens,
            answer_detail_level=settings.agent_context.answer_detail_level,
            reasoning_effort=settings.agent_context.reasoning_effort,
            video_generation_concurrency=settings.generation.video_generation_concurrency,
            web_search_enabled=settings.web_search.enabled,
            chaoxing_request_delay_seconds=settings.external_import.chaoxing.request_delay_seconds,
            chaoxing_init_course_delay_seconds=settings.external_import.chaoxing.init_course_delay_seconds,
        )

    def update_workspace_settings(
        self,
        *,
        theme: str,
        show_takeaways: bool,
        transcript_enhancement_enabled: bool,
        asr_model_quality: str,
        transcription_mode: str,
        rag_embedding_device: str,
        rag_max_hits: int,
        rag_rerank_enabled: bool,
        window_tokens: int,
        answer_detail_level: str,
        reasoning_effort: str,
        video_generation_concurrency: int,
        web_search_enabled: bool,
        chaoxing_request_delay_seconds: float = 0.2,
        chaoxing_init_course_delay_seconds: float = 0.3,
    ) -> WorkspaceSettings:
        if theme not in VALID_THEMES:
            raise SettingsValidationError(f"unsupported theme '{theme}'")
        if not self._faster_whisper_model_manager.is_supported(asr_model_quality):
            raise SettingsValidationError(f"unsupported asr model '{asr_model_quality}'")
        if transcription_mode not in VALID_TRANSCRIPTION_MODES:
            raise SettingsValidationError(f"unsupported transcription mode '{transcription_mode}'")
        if window_tokens <= 0:
            raise SettingsValidationError("window_tokens 必须是正整数。")
        if answer_detail_level not in VALID_ANSWER_DETAIL_LEVELS:
            raise SettingsValidationError("answer_detail_level 必须是 short、medium 或 long。")
        if reasoning_effort not in VALID_REASONING_EFFORTS:
            raise SettingsValidationError("reasoning_effort 必须是 none、low、medium 或 high。")
        if rag_max_hits <= 0:
            raise SettingsValidationError("rag_max_hits 必须是正整数。")
        if video_generation_concurrency <= 0:
            raise SettingsValidationError("video_generation_concurrency 必须是正整数。")
        if chaoxing_request_delay_seconds < 0:
            raise SettingsValidationError("chaoxing_request_delay_seconds 必须是大于等于 0 的数字。")
        if chaoxing_init_course_delay_seconds < 0:
            raise SettingsValidationError("chaoxing_init_course_delay_seconds 必须是大于等于 0 的数字。")
        if (
            rag_rerank_enabled
            and self._rag_model_manager is not None
            and not self._rag_model_manager.is_downloaded("reranker")
        ):
            raise SettingsValidationError(RAG_RERANKER_REQUIRED_MESSAGE)

        with self._settings_lock:
            current_settings = load_settings(self._config_path, self._root_dir)
            next_settings = replace_workspace_ui_settings(
                current_settings,
                WorkspaceUiSettings(
                    theme=theme,
                    show_takeaways=show_takeaways,
                ),
            )
            next_settings = replace_transcript_enhancement_enabled(next_settings, transcript_enhancement_enabled)
            next_settings = replace_faster_whisper_model_size(next_settings, asr_model_quality)
            next_settings = replace_faster_whisper_transcription_mode(next_settings, transcription_mode)
            next_settings = replace_agent_retrieval_runtime_settings(
                next_settings,
                embedding_device=rag_embedding_device,
                max_hits=rag_max_hits,
                rerank_enabled=rag_rerank_enabled,
            )
            next_settings = replace_agent_context_window_tokens(next_settings, window_tokens)
            next_settings = replace_agent_context_answer_detail_level(next_settings, answer_detail_level)
            next_settings = replace_agent_context_reasoning_effort(next_settings, reasoning_effort)
            next_settings = replace_video_generation_concurrency(next_settings, video_generation_concurrency)
            next_settings = replace_web_search_enabled(next_settings, web_search_enabled)
            next_settings = replace_chaoxing_import_settings(
                next_settings,
                request_delay_seconds=chaoxing_request_delay_seconds,
                init_course_delay_seconds=chaoxing_init_course_delay_seconds,
            )
            save_settings(self._config_path, next_settings)

        return WorkspaceSettings(
            theme=theme,
            show_takeaways=show_takeaways,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
            asr_model_quality=asr_model_quality,
            transcription_mode=transcription_mode,
            rag_embedding_device=next_settings.agent_retrieval.embedding_device,
            rag_max_hits=next_settings.agent_retrieval.max_hits,
            rag_rerank_enabled=next_settings.agent_retrieval.rerank_enabled,
            window_tokens=next_settings.agent_context.window_tokens,
            answer_detail_level=next_settings.agent_context.answer_detail_level,
            reasoning_effort=next_settings.agent_context.reasoning_effort,
            video_generation_concurrency=next_settings.generation.video_generation_concurrency,
            web_search_enabled=next_settings.web_search.enabled,
            chaoxing_request_delay_seconds=next_settings.external_import.chaoxing.request_delay_seconds,
            chaoxing_init_course_delay_seconds=next_settings.external_import.chaoxing.init_course_delay_seconds,
        )

    def get_provider_settings(self) -> ProviderSettings:
        env_settings = load_env_settings(self._root_dir)
        return ProviderSettings(
            llm_provider=env_settings.provider,
            openai_base_url=env_settings.base_url,
            openai_model=env_settings.model,
            has_openai_api_key=bool(env_settings.api_key),
            openai_api_key_masked=_mask_api_key(env_settings.api_key),
            hf_endpoint=env_settings.hf_endpoint,
        )

    def get_openai_api_key(self) -> str:
        return load_env_settings(self._root_dir).api_key

    def update_provider_settings(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_model: str,
        openai_api_key: str | None,
        hf_endpoint: str | None,
    ) -> ProviderSettings:
        provider_settings = self._validate_provider_settings(
            llm_provider=llm_provider,
            openai_base_url=openai_base_url,
            openai_model=openai_model,
            openai_api_key=openai_api_key,
            hf_endpoint=hf_endpoint,
        )
        with self._settings_lock:
            self._save_provider_settings(
                llm_provider=provider_settings.llm_provider,
                openai_base_url=provider_settings.openai_base_url,
                openai_model=provider_settings.openai_model,
                openai_api_key=self._resolve_openai_api_key(openai_api_key),
                hf_endpoint=provider_settings.hf_endpoint,
            )
        return provider_settings

    def test_provider_settings(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_model: str,
        openai_api_key: str | None,
        hf_endpoint: str | None,
    ) -> str:
        provider_settings = self._validate_provider_settings(
            llm_provider=llm_provider,
            openai_base_url=openai_base_url,
            openai_model=openai_model,
            openai_api_key=openai_api_key,
            hf_endpoint=hf_endpoint,
        )
        gateway = LiteLLMCompletionGateway(
            provider=provider_settings.llm_provider,
            base_url=provider_settings.openai_base_url,
            model=provider_settings.openai_model,
            api_key=self._resolve_openai_api_key(openai_api_key),
            reasoning_effort=load_settings(self._config_path, self._root_dir).agent_context.reasoning_effort,
        )
        try:
            response = gateway.test_connection()
        except Exception as error:
            if _is_model_timeout(error):
                raise RuntimeError("模型超时") from error
            raise
        return response or "ok"

    def _save_provider_settings(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_model: str,
        openai_api_key: str,
        hf_endpoint: str,
    ) -> None:
        save_env_settings(
            self._root_dir,
            EnvSettings(
                provider=llm_provider,
                base_url=openai_base_url,
                model=openai_model,
                api_key=openai_api_key,
                hf_endpoint=hf_endpoint,
            ),
        )

    def _validate_provider_settings(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_model: str,
        openai_api_key: str | None,
        hf_endpoint: str | None,
    ) -> ProviderSettings:
        normalized_provider = llm_provider.strip()
        normalized_base_url = openai_base_url.strip()
        normalized_model = openai_model.strip()

        if normalized_provider == "qwen":
            normalized_provider = "dashscope"
        if normalized_provider not in VALID_LLM_PROVIDERS:
            raise SettingsValidationError(
                f"unsupported llm provider '{normalized_provider}'"
            )
        if normalized_base_url and not normalized_base_url.startswith(("http://", "https://")):
            raise SettingsValidationError(
                "模型接口地址必须包含 http:// 或 https://。"
            )
        if not normalized_model:
            raise SettingsValidationError("模型名称不能为空。")

        return ProviderSettings(
            llm_provider=normalized_provider,
            openai_base_url=normalize_openai_base_url(normalized_base_url),
            openai_model=normalized_model,
            has_openai_api_key=bool(self._resolve_openai_api_key(openai_api_key)),
            openai_api_key_masked=_mask_api_key(self._resolve_openai_api_key(openai_api_key)),
            hf_endpoint=(hf_endpoint or "").strip(),
        )

    def _resolve_openai_api_key(self, openai_api_key: str | None) -> str:
        if openai_api_key is None:
            return load_env_settings(self._root_dir).api_key
        return openai_api_key.strip()


def _mask_api_key(api_key: str) -> str:
    normalized = api_key.strip()
    if not normalized:
        return ""
    if len(normalized) <= 8:
        return "*" * len(normalized)
    return f"{normalized[:4]}{'*' * max(4, len(normalized) - 8)}{normalized[-4:]}"


def _is_model_timeout(error: Exception) -> bool:
    if isinstance(error, TimeoutError):
        return True
    message = str(error).lower()
    return "timeout" in message or "timed out" in message
