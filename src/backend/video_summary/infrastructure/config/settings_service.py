"""设置面板的服务层：`SettingsService` + `SettingsServicePort` Protocol。

本模块负责"把工作区设置/LLM provider 持久化并对外暴露安全视图"：
- `SettingsServicePort` 是供 API 路由、Agent 适配层依赖注入的 Port；
- `SettingsService` 是其实现：校验 + 落盘 `settings.toml` / `.env` +
  跑 LiteLLM 连通性测试。
所有写入都走原子写并由 `self._settings_lock` 串行化，避免并发覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol

from backend.video_summary.infrastructure.asr.faster_whisper_models import FasterWhisperModelManager
from backend.video_summary.infrastructure.asr.whisper_cpp_models import WhisperCppModelManager
from backend.video_summary.infrastructure.asr.aliyun_bailian_transcriber import _normalize_dashscope_base_address
from backend.video_summary.infrastructure.rag.rag_models import RAG_RERANKER_REQUIRED_MESSAGE, RagModelManager
from backend.video_summary.infrastructure.config.settings import (
    EnvSettings,
    VALID_ASR_PROVIDERS,
    VALID_THEMES,
    VALID_WORKSPACE_LAYOUT_MODES,
    VALID_TRANSCRIPTION_MODES,
    VALID_ANSWER_DETAIL_LEVELS,
    VALID_LLM_PROVIDERS,
    VALID_REASONING_EFFORTS,
    WorkspaceUiSettings,
    apply_runtime_env_overrides,
    load_env_settings,
    load_settings,
    normalize_openai_base_url,
    replace_agent_retrieval_runtime_settings,
    replace_aliyun_bailian_asr_settings,
    replace_asr_provider,
    replace_agent_context_window_tokens,
    replace_agent_context_answer_detail_level,
    replace_agent_context_reasoning_effort,
    replace_agent_context_talk_custom_prompt,
    replace_faster_whisper_model_size,
    replace_whisper_cpp_model,
    replace_faster_whisper_transcription_mode,
    replace_transcript_enhancement_enabled,
    replace_chaoxing_import_settings,
    replace_chapter_screenshots_enabled,
    replace_video_generation_concurrency,
    replace_web_search_enabled,
    replace_workspace_ui_settings,
    save_env_settings,
    save_settings,
)
from backend.video_summary.infrastructure.runtime_capabilities import detect_runtime_capabilities
from backend.shared.llm import LiteLLMCompletionGateway
from backend.shared.llm.base_url import resolve_openai_model_list_base_url


class SettingsValidationError(ValueError):
    """设置面板输入校验失败时抛出（区别于 `load_settings` 内部的 `ValueError`）。"""


@dataclass(frozen=True)
class ProviderSettings:
    """LLM provider / `.env` 配置的对外只读视图。

    Attributes:
        llm_provider: LLM provider 标识。
        openai_base_url: 归一化后的 OpenAI 兼容 base_url。
        openai_model: 模型名称。
        has_openai_api_key: 是否已配置 API Key（仅布尔，不暴露原文）。
        openai_api_key_masked: 脱敏后的 API Key，前 4 后 4 可见。
        hf_endpoint: HuggingFace 镜像 URL。
    """

    llm_provider: str
    openai_base_url: str
    openai_model: str
    has_openai_api_key: bool
    openai_api_key_masked: str
    hf_endpoint: str


@dataclass(frozen=True)
class WorkspaceSettings:
    """工作区可调配置的对外只读视图。

    Attributes:
        theme: UI 主题（`light` / `dark`）。
        show_takeaways: 是否在工作区显示"关键结论"区。
        transcript_enhancement_enabled: 是否启用 LLM 转写增强。
        asr_model_quality: faster-whisper 模型 ID。
        transcription_mode: 转写模式（`fast` / `balanced` / `accurate`）。
        rag_embedding_device: RAG embedding 计算设备。
        rag_max_hits: 单次检索返回的最大命中数。
        rag_rerank_enabled: 是否启用 BGE 重排序（受 reranker 模型下载状态影响）。
        window_tokens: LLM 上下文窗口大小。
        answer_detail_level: 答案详细程度。
        reasoning_effort: 推理深度。
        talk_custom_prompt: Agent 自定义问答提示词。
        video_generation_concurrency: 单视频级并发上限。
        chapter_screenshots_enabled: 是否为概括章节生成视频截图。
        web_search_enabled: 是否启用 Web 搜索。
        chaoxing_request_delay_seconds: 超星导入普通请求最小间隔。
        chaoxing_init_course_delay_seconds: 超星课程初始化额外等待。
    """

    theme: str
    show_takeaways: bool
    layout_mode: str
    transcript_enhancement_enabled: bool
    asr_provider: str
    asr_model_quality: str
    transcription_mode: str
    asr_cloud_model: str
    asr_base_url: str
    has_asr_api_key: bool
    asr_api_key_masked: str
    rag_embedding_device: str
    rag_max_hits: int
    rag_rerank_enabled: bool
    window_tokens: int
    answer_detail_level: str
    reasoning_effort: str
    talk_custom_prompt: str
    video_generation_concurrency: int
    chapter_screenshots_enabled: bool
    web_search_enabled: bool
    chaoxing_request_delay_seconds: float
    chaoxing_init_course_delay_seconds: float


class SettingsServicePort(Protocol):
    """设置服务对外暴露的 Protocol（供 API 路由/其他模块做依赖注入）。

    业务目的：把"读/写工作区设置"与"读/写 LLM provider 设置"封装成单一服务，
    避免上层直接耦合到 `settings.toml` 与 `.env` 的具体 IO。
    """

    def get_workspace_settings(self) -> WorkspaceSettings:
        """返回当前 `settings.toml` 中的工作区可调配置视图。"""
        ...

    def update_workspace_settings(
        self,
        *,
        theme: str,
        show_takeaways: bool,
        layout_mode: str,
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
        chapter_screenshots_enabled: bool = True,
        asr_provider: str = "faster_whisper",
        asr_cloud_model: str = "paraformer-v2",
        asr_base_url: str = "https://dashscope.aliyuncs.com",
        asr_api_key: str | None = None,
        talk_custom_prompt: str = "",
        chaoxing_request_delay_seconds: float = 0.2,
        chaoxing_init_course_delay_seconds: float = 0.3,
    ) -> WorkspaceSettings:
        """校验并把新的工作区配置落盘到 `settings.toml`。"""
        ...

    def get_provider_settings(self) -> ProviderSettings:
        """返回当前 `.env` 中的 LLM provider 配置视图（API Key 脱敏）。"""
        ...

    def get_openai_api_key(self) -> str:
        """返回当前 `.env` 中明文保存的 OpenAI API Key（供内部调用 LLM 使用）。"""
        ...

    def get_asr_api_key(self) -> str:
        """返回当前 `.env` 中明文保存的 ASR API Key。"""
        ...

    def test_asr_settings(
        self,
        *,
        asr_provider: str,
        asr_cloud_model: str,
        asr_base_url: str,
        asr_api_key: str | None,
    ) -> str:
        """测试 ASR provider 连接，返回回执文本。"""
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
        """校验并把新的 LLM provider 配置落盘到 `.env`。"""
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
        """用给定 provider 配置走一次 LiteLLM 连接测试，返回回执文本。"""
        ...

    def list_provider_models(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_api_key: str | None,
    ) -> list[str]:
        """通过 LiteLLM 探测当前供应商可用的模型标识。"""
        ...


class SettingsService:
    """设置面板的持久化与连通性测试服务。

    业务目的：把"读 + 改 + 落盘 + 测连接"封装为单一服务，作为 API 路由与
    LangGraph agent 之间的唯一设置入口；通过 `SettingsServicePort` 解耦具体
    存储实现。
    """

    def __init__(
        self,
        *,
        config_path: Path,
        root_dir: Path,
        faster_whisper_model_manager: FasterWhisperModelManager,
        whisper_cpp_model_manager: WhisperCppModelManager | None = None,
        rag_model_manager: RagModelManager | None = None,
    ) -> None:
        """注入 `settings.toml` 路径、项目根目录与 ASR / RAG 模型管理器。

        Args:
            config_path: `settings.toml` 文件路径。
            root_dir: 项目根目录（用于定位 `.env`）。
            faster_whisper_model_manager: 用于校验 asr_model_quality 是否受支持。
            rag_model_manager: 用于检测 reranker 模型是否已下载；为 `None` 时
                视为不强制要求（保留向后兼容）。
        """
        self._config_path = config_path
        self._root_dir = root_dir
        self._faster_whisper_model_manager = faster_whisper_model_manager
        self._whisper_cpp_model_manager = whisper_cpp_model_manager or WhisperCppModelManager(
            root_dir / "data" / "models" / "whisper-cpp"
        )
        self._rag_model_manager = rag_model_manager
        self._settings_lock = Lock()

    def get_workspace_settings(self) -> WorkspaceSettings:
        """把 `settings.toml` 转换为工作区可调配置视图。

        Returns:
            包含主题、转写开关、ASR / RAG / Agent / 外部导入等所有工作区可调
            字段的 `WorkspaceSettings`；`rag_rerank_enabled` 受 reranker 模型
            下载状态影响。
        """
        settings = load_settings(self._config_path, self._root_dir)
        env_settings = load_env_settings(self._root_dir)
        rag_rerank_enabled = settings.agent_retrieval.rerank_enabled and (
            self._rag_model_manager is None or self._rag_model_manager.is_downloaded("reranker")
        )
        return WorkspaceSettings(
            theme=settings.workspace_ui.theme,
            show_takeaways=settings.workspace_ui.show_takeaways,
            layout_mode=settings.workspace_ui.layout_mode,
            transcript_enhancement_enabled=settings.asr.transcript_enhancement_enabled,
            asr_provider=settings.asr.provider,
            asr_model_quality=(
                settings.asr.whisper_cpp.model
                if settings.asr.provider == "whisper_cpp"
                else settings.asr.faster_whisper.model_size
            ),
            transcription_mode=settings.asr.faster_whisper.transcription_mode,
            asr_cloud_model=settings.asr.aliyun_bailian.model,
            asr_base_url=settings.asr.aliyun_bailian.base_url,
            has_asr_api_key=bool(env_settings.dashscope_api_key),
            asr_api_key_masked=_mask_api_key(env_settings.dashscope_api_key),
            rag_embedding_device=settings.agent_retrieval.embedding_device,
            rag_max_hits=settings.agent_retrieval.max_hits,
            rag_rerank_enabled=rag_rerank_enabled,
            window_tokens=settings.agent_context.window_tokens,
            answer_detail_level=settings.agent_context.answer_detail_level,
            reasoning_effort=settings.agent_context.reasoning_effort,
            talk_custom_prompt=settings.agent_context.talk_custom_prompt,
            video_generation_concurrency=settings.generation.video_generation_concurrency,
            chapter_screenshots_enabled=settings.generation.chapter_screenshots_enabled,
            web_search_enabled=settings.web_search.enabled,
            chaoxing_request_delay_seconds=settings.external_import.chaoxing.request_delay_seconds,
            chaoxing_init_course_delay_seconds=settings.external_import.chaoxing.init_course_delay_seconds,
        )

    def update_workspace_settings(
        self,
        *,
        theme: str,
        show_takeaways: bool,
        layout_mode: str,
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
        chapter_screenshots_enabled: bool = True,
        asr_provider: str = "faster_whisper",
        asr_cloud_model: str = "paraformer-v2",
        asr_base_url: str = "https://dashscope.aliyuncs.com",
        asr_api_key: str | None = None,
        talk_custom_prompt: str = "",
        chaoxing_request_delay_seconds: float = 0.2,
        chaoxing_init_course_delay_seconds: float = 0.3,
    ) -> WorkspaceSettings:
        """校验并把工作区可调配置落盘到 `settings.toml`。

        校验项：主题枚举、ASR 模型是否被 faster-whisper 管理器支持、转写
        模式枚举、若干正整数 / 非负数约束；启用 rerank 但 reranker 未下载时
        拒绝。落盘走 `dataclasses.replace` 派生新 `AppSettings`，最终调用
        `save_settings` 原子写回。

        Args:
            theme: UI 主题。
            show_takeaways: 是否显示关键结论。
            transcript_enhancement_enabled: 是否启用 LLM 转写增强。
            asr_model_quality: faster-whisper 模型 ID。
            transcription_mode: 转写模式。
            rag_embedding_device: RAG embedding 设备。
            rag_max_hits: 单次检索最大命中数。
            rag_rerank_enabled: 是否启用 BGE rerank。
            window_tokens: LLM 上下文窗口大小。
            answer_detail_level: 答案详细程度。
            reasoning_effort: 推理深度。
            video_generation_concurrency: 单视频级并发上限。
            chapter_screenshots_enabled: 是否为概括章节生成视频截图。
            web_search_enabled: 是否启用 Web 搜索。
            talk_custom_prompt: Agent 自定义问答提示词。
            chaoxing_request_delay_seconds: 超星导入普通请求最小间隔。
            chaoxing_init_course_delay_seconds: 超星课程初始化额外等待。

        Returns:
            落盘后的 `WorkspaceSettings` 视图（已归一化字段）。

        Raises:
            SettingsValidationError: 任一字段校验失败。
        """
        if theme not in VALID_THEMES:
            raise SettingsValidationError(f"unsupported theme '{theme}'")
        if layout_mode not in VALID_WORKSPACE_LAYOUT_MODES:
            raise SettingsValidationError(f"unsupported workspace layout mode '{layout_mode}'")
        normalized_asr_provider = asr_provider.strip().lower()
        if normalized_asr_provider not in VALID_ASR_PROVIDERS:
            raise SettingsValidationError(f"unsupported asr provider '{normalized_asr_provider}'")
        capabilities = detect_runtime_capabilities()
        if normalized_asr_provider == "faster_whisper" and not capabilities.faster_whisper_available:
            raise SettingsValidationError(capabilities.unavailable_reason or "本机不支持 faster-whisper。")
        normalized_embedding_device = rag_embedding_device.strip().lower()
        if normalized_embedding_device in {"gpu", "cuda"} and not capabilities.gpu_embedding_available:
            raise SettingsValidationError(capabilities.unavailable_reason or "本机不支持 FastEmbed GPU。")
        model_manager = (
            self._whisper_cpp_model_manager
            if normalized_asr_provider == "whisper_cpp"
            else self._faster_whisper_model_manager
        )
        if normalized_asr_provider != "aliyun_bailian" and not model_manager.is_supported(asr_model_quality):
            raise SettingsValidationError(f"unsupported asr model '{asr_model_quality}'")
        if asr_base_url and not asr_base_url.strip().startswith(("http://", "https://")):
            raise SettingsValidationError("ASR API 地址必须包含 http:// 或 https://。")
        if not asr_cloud_model.strip():
            raise SettingsValidationError("ASR 云端模型名称不能为空。")
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
                    layout_mode=layout_mode,
                ),
            )
            next_settings = replace_transcript_enhancement_enabled(next_settings, transcript_enhancement_enabled)
            next_settings = replace_asr_provider(next_settings, normalized_asr_provider)
            if normalized_asr_provider == "whisper_cpp":
                next_settings = replace_whisper_cpp_model(next_settings, asr_model_quality)
            elif normalized_asr_provider == "faster_whisper":
                next_settings = replace_faster_whisper_model_size(next_settings, asr_model_quality)
            next_settings = replace_faster_whisper_transcription_mode(next_settings, transcription_mode)
            next_settings = replace_aliyun_bailian_asr_settings(
                next_settings,
                base_url=asr_base_url,
                model=asr_cloud_model,
            )
            next_settings = replace_agent_retrieval_runtime_settings(
                next_settings,
                embedding_device=rag_embedding_device,
                max_hits=rag_max_hits,
                rerank_enabled=rag_rerank_enabled,
            )
            next_settings = replace_agent_context_window_tokens(next_settings, window_tokens)
            next_settings = replace_agent_context_answer_detail_level(next_settings, answer_detail_level)
            next_settings = replace_agent_context_reasoning_effort(next_settings, reasoning_effort)
            next_settings = replace_agent_context_talk_custom_prompt(next_settings, talk_custom_prompt)
            next_settings = replace_video_generation_concurrency(next_settings, video_generation_concurrency)
            next_settings = replace_chapter_screenshots_enabled(next_settings, chapter_screenshots_enabled)
            next_settings = replace_web_search_enabled(next_settings, web_search_enabled)
            next_settings = replace_chaoxing_import_settings(
                next_settings,
                request_delay_seconds=chaoxing_request_delay_seconds,
                init_course_delay_seconds=chaoxing_init_course_delay_seconds,
            )
            save_settings(self._config_path, next_settings)
            if asr_api_key is not None:
                env_settings = load_env_settings(self._root_dir)
                save_env_settings(
                    self._root_dir,
                    EnvSettings(
                        provider=env_settings.provider,
                        base_url=env_settings.base_url,
                        model=env_settings.model,
                        api_key=env_settings.api_key,
                        hf_endpoint=env_settings.hf_endpoint,
                        dashscope_api_key=asr_api_key.strip(),
                    ),
                )
                apply_runtime_env_overrides(self._root_dir)

        env_settings = load_env_settings(self._root_dir)
        return WorkspaceSettings(
            theme=theme,
            show_takeaways=show_takeaways,
            layout_mode=layout_mode,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
            asr_provider=next_settings.asr.provider,
            asr_model_quality=(
                next_settings.asr.whisper_cpp.model
                if next_settings.asr.provider == "whisper_cpp"
                else next_settings.asr.faster_whisper.model_size
            ),
            transcription_mode=transcription_mode,
            asr_cloud_model=next_settings.asr.aliyun_bailian.model,
            asr_base_url=next_settings.asr.aliyun_bailian.base_url,
            has_asr_api_key=bool(env_settings.dashscope_api_key),
            asr_api_key_masked=_mask_api_key(env_settings.dashscope_api_key),
            rag_embedding_device=next_settings.agent_retrieval.embedding_device,
            rag_max_hits=next_settings.agent_retrieval.max_hits,
            rag_rerank_enabled=next_settings.agent_retrieval.rerank_enabled,
            window_tokens=next_settings.agent_context.window_tokens,
            answer_detail_level=next_settings.agent_context.answer_detail_level,
            reasoning_effort=next_settings.agent_context.reasoning_effort,
            talk_custom_prompt=next_settings.agent_context.talk_custom_prompt,
            video_generation_concurrency=next_settings.generation.video_generation_concurrency,
            chapter_screenshots_enabled=next_settings.generation.chapter_screenshots_enabled,
            web_search_enabled=next_settings.web_search.enabled,
            chaoxing_request_delay_seconds=next_settings.external_import.chaoxing.request_delay_seconds,
            chaoxing_init_course_delay_seconds=next_settings.external_import.chaoxing.init_course_delay_seconds,
        )

    def get_provider_settings(self) -> ProviderSettings:
        """把 `.env` 中的 LLM provider 配置转换为对外视图。

        Returns:
            含 provider / base_url / model / API Key 是否存在 / 脱敏 Key /
            HF 镜像的 `ProviderSettings`。
        """
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
        """读取 `.env` 中明文保存的 OpenAI API Key（供内部 LLM 调用使用）。"""
        return load_env_settings(self._root_dir).api_key

    def get_asr_api_key(self) -> str:
        """读取 `.env` 中明文保存的 ASR API Key。"""
        return load_env_settings(self._root_dir).dashscope_api_key

    def test_asr_settings(
        self,
        *,
        asr_provider: str,
        asr_cloud_model: str,
        asr_base_url: str,
        asr_api_key: str | None,
    ) -> str:
        """测试 ASR provider 连接，不持久化配置、不上传用户音频。"""
        normalized_provider = asr_provider.strip().lower()
        if normalized_provider not in VALID_ASR_PROVIDERS:
            raise SettingsValidationError(f"unsupported asr provider '{normalized_provider}'")
        if normalized_provider == "faster_whisper":
            return "本地 faster-whisper 无需云端连接测试。"
        if normalized_provider == "whisper_cpp":
            return "本地 whisper.cpp 无需云端连接测试。"
        if normalized_provider != "aliyun_bailian":
            raise SettingsValidationError(f"unsupported asr provider '{normalized_provider}'")

        model = asr_cloud_model.strip()
        if not model:
            raise SettingsValidationError("ASR 云端模型名称不能为空。")
        base_address = _normalize_dashscope_base_address(asr_base_url)
        api_key = self._resolve_asr_api_key(asr_api_key)
        if not api_key:
            raise SettingsValidationError("请先填写阿里云百炼 ASR API Key。")

        try:
            from dashscope.utils.oss_utils import OssUtils
        except ImportError as error:
            raise RuntimeError("dashscope is not installed.") from error

        try:
            response = OssUtils.get_upload_certificate(
                model=model,
                api_key=api_key,
                base_address=base_address,
            )
        except Exception as error:
            raise RuntimeError(f"阿里云百炼 ASR 连接失败：{error}") from error

        status_code = getattr(response, "status_code", None)
        if status_code != 200:
            code = getattr(response, "code", "") or ""
            message = getattr(response, "message", "") or str(response)
            raise RuntimeError(f"阿里云百炼 ASR 连接失败：{code} {message}".strip())
        return "阿里云百炼 ASR 连接正常。"

    def update_provider_settings(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_model: str,
        openai_api_key: str | None,
        hf_endpoint: str | None,
    ) -> ProviderSettings:
        """校验并把新的 LLM provider 配置落盘到 `.env`。

        Args:
            llm_provider: LLM provider 标识（`qwen` 会被归一为 `dashscope`）。
            openai_base_url: OpenAI 兼容 base_url。
            openai_model: 模型名称。
            openai_api_key: 新 API Key；为 `None` 时保留 `.env` 现有值。
            hf_endpoint: HuggingFace 镜像 URL；为 `None` 时按空字符串处理。

        Returns:
            归一化后的 `ProviderSettings`（含脱敏 API Key）。

        Raises:
            SettingsValidationError: provider 非法 / base_url 缺协议头 / model 为空。
        """
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
        """用给定 provider 配置走一次 LiteLLM 连接测试。

        Args:
            llm_provider: LLM provider 标识。
            openai_base_url: OpenAI 兼容 base_url。
            openai_model: 模型名称。
            openai_api_key: 候选 API Key；为 `None` 时使用 `.env` 现有值。
            hf_endpoint: HuggingFace 镜像 URL；为 `None` 时按空字符串处理。

        Returns:
            模型回执文本（网关为空时返回 `"ok"`）。

        Raises:
            SettingsValidationError: provider 非法 / base_url 缺协议头 / model 为空。
            RuntimeError: 模型超时（包装为"模型超时"）。
        """
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

    def list_provider_models(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_api_key: str | None,
    ) -> list[str]:
        """通过 LiteLLM 的 provider endpoint 探测模型列表，不持久化配置。"""
        provider_settings = self._validate_provider_settings(
            llm_provider=llm_provider,
            openai_base_url=openai_base_url,
            openai_model="model-discovery",
            openai_api_key=openai_api_key,
            hf_endpoint=None,
        )
        try:
            from litellm import get_valid_models
            from litellm.types.router import LiteLLM_Params
        except ImportError as error:
            raise RuntimeError("缺少 litellm 依赖，无法探测模型。") from error

        models = get_valid_models(
            check_provider_endpoint=True,
            custom_llm_provider=provider_settings.llm_provider,
            litellm_params=LiteLLM_Params(
                model="model-discovery",
                custom_llm_provider=provider_settings.llm_provider,
                api_base=_provider_model_list_api_base(
                    provider_settings.llm_provider,
                    provider_settings.openai_base_url,
                ) or None,
                api_key=self._resolve_openai_api_key(openai_api_key),
                timeout=15,
            ),
        )
        unique_models = sorted({model.strip() for model in models if isinstance(model, str) and model.strip()})
        if not unique_models:
            raise RuntimeError("未探测到可用模型，请检查接口地址、API Key 和供应商协议。")
        return unique_models

    def _save_provider_settings(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_model: str,
        openai_api_key: str,
        hf_endpoint: str,
    ) -> None:
        """把 LLM provider 配置封装为 `EnvSettings` 并落盘到 `.env`（原子写）。"""
        save_env_settings(
            self._root_dir,
            EnvSettings(
                provider=llm_provider,
                base_url=openai_base_url,
                model=openai_model,
                api_key=openai_api_key,
                hf_endpoint=hf_endpoint,
                dashscope_api_key=load_env_settings(self._root_dir).dashscope_api_key,
            ),
        )
        apply_runtime_env_overrides(self._root_dir)

    def _validate_provider_settings(
        self,
        *,
        llm_provider: str,
        openai_base_url: str,
        openai_model: str,
        openai_api_key: str | None,
        hf_endpoint: str | None,
    ) -> ProviderSettings:
        """归一化并校验 LLM provider 配置，返回可对外暴露的 `ProviderSettings`。

        校验项：provider 枚举（`qwen` → `dashscope`）、base_url 必须以
        `http://` 或 `https://` 开头（允许空字符串）、model 不能为空。`api_key`
        用于派生 `has_openai_api_key` / `openai_api_key_masked`，原文不出现在
        返回值中。

        Args:
            llm_provider: LLM provider 标识。
            openai_base_url: OpenAI 兼容 base_url（允许空字符串）。
            openai_model: 模型名称。
            openai_api_key: 候选 API Key；为 `None` 时回落到 `.env` 现有值。
            hf_endpoint: HuggingFace 镜像 URL；为 `None` 时按空字符串处理。

        Returns:
            归一化后的 `ProviderSettings`（API Key 脱敏）。

        Raises:
            SettingsValidationError: provider 非法 / base_url 缺协议头 / model 为空。
        """
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
        """解析"本次传入"的 API Key：`None` 时回落到 `.env` 现有值，其他值做 strip。"""
        if openai_api_key is None:
            return load_env_settings(self._root_dir).api_key
        return openai_api_key.strip()

    def _resolve_asr_api_key(self, asr_api_key: str | None) -> str:
        """解析"本次传入"的 ASR API Key：`None` 时回落到 `.env` 现有值。"""
        if asr_api_key is None:
            return load_env_settings(self._root_dir).dashscope_api_key
        return asr_api_key.strip()


def _provider_model_list_api_base(provider: str, base_url: str) -> str:
    """返回 LiteLLM provider 模型发现所需的 API base。"""
    if provider in {"openai", "litellm_proxy"}:
        return resolve_openai_model_list_base_url(base_url)
    return base_url


def _mask_api_key(api_key: str) -> str:
    """把 API Key 脱敏：长度 ≤ 8 全部 `*`，否则保留前 4 后 4 + 中间 `*`；空串返回空串。"""
    normalized = api_key.strip()
    if not normalized:
        return ""
    if len(normalized) <= 8:
        return "*" * len(normalized)
    return f"{normalized[:4]}{'*' * max(4, len(normalized) - 8)}{normalized[-4:]}"


def _is_model_timeout(error: Exception) -> bool:
    """判断异常是否表示"模型超时"：匹配 `TimeoutError` 或 message 中含 `timeout` / `timed out`。"""
    if isinstance(error, TimeoutError):
        return True
    message = str(error).lower()
    return "timeout" in message or "timed out" in message
