from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import tomllib

from backend.llm_gateway.base_url import normalize_provider_base_url
from backend.common.filesystem import atomic_write_text


VALID_DEVICES = {"auto", "cpu", "gpu"}
VALID_ASR_PROVIDERS = {"faster_whisper"}
VALID_THEMES = {"light", "dark"}
VALID_TRANSCRIPTION_MODES = {"fast", "balanced", "accurate"}
VALID_PLANNER_TRANSPORTS = {"structured", "stream_buffered"}
VALID_WEB_SEARCH_PROVIDERS = {"litellm"}
VALID_WEB_SEARCH_MODES = {"native"}
VALID_WEB_SEARCH_CONTEXT_SIZES = {"low", "medium", "high"}
VALID_ANSWER_DETAIL_LEVELS = {"short", "medium", "long"}
VALID_REASONING_EFFORTS = {"none", "low", "medium", "high"}
VALID_LLM_PROVIDERS = {
    "ai21",
    "ai21_chat",
    "aiohttp_openai",
    "anthropic",
    "anthropic_text",
    "assemblyai",
    "azure",
    "azure_ai",
    "azure_text",
    "baseten",
    "bedrock",
    "cerebras",
    "clarifai",
    "cloudflare",
    "codestral",
    "cohere",
    "cohere_chat",
    "custom",
    "custom_openai",
    "dashscope",
    "databricks",
    "datarobot",
    "deepgram",
    "deepinfra",
    "deepseek",
    "elevenlabs",
    "empower",
    "featherless_ai",
    "fireworks_ai",
    "friendliai",
    "galadriel",
    "gemini",
    "github",
    "github_copilot",
    "groq",
    "hosted_vllm",
    "humanloop",
    "huggingface",
    "infinity",
    "jina_ai",
    "langfuse",
    "litellm_proxy",
    "lm_studio",
    "maritalk",
    "meta_llama",
    "mistral",
    "nebius",
    "nlp_cloud",
    "novita",
    "nvidia_nim",
    "nscale",
    "ollama",
    "oobabooga",
    "openai",
    "openrouter",
    "perplexity",
    "petals",
    "predibase",
    "replicate",
    "sagemaker",
    "sagemaker_chat",
    "sambanova",
    "snowflake",
    "text-completion-codestral",
    "text-completion-openai",
    "together_ai",
    "topaz",
    "triton",
    "vertex_ai",
    "vertex_ai_beta",
    "volcengine",
    "voyage",
    "watsonx",
    "watsonx_text",
    "xai",
    "xinference",
}
DEFAULT_AGENT_CONTEXT_WINDOW_TOKENS = 1_000_000
DEFAULT_AGENT_ANSWER_DETAIL_LEVEL = "medium"
DEFAULT_AGENT_REASONING_EFFORT = "none"
DEFAULT_AGENT_TALK_CUSTOM_PROMPT = ""
DEFAULT_AGENT_RESERVED_OUTPUT_TOKENS = 20_000
DEFAULT_AGENT_WARNING_THRESHOLD_RATIO = 0.60
DEFAULT_AGENT_COMPACT_THRESHOLD_RATIO = 0.80
DEFAULT_AGENT_BLOCKING_THRESHOLD_RATIO = 0.92
DEFAULT_AGENT_KEEP_TAIL_MESSAGES = 6
DEFAULT_AGENT_PROJECTION_MAX_TOKENS_RATIO = 0.08
DEFAULT_AGENT_DIRECT_SUMMARY_THRESHOLD_RATIO = 0.90
DEFAULT_AGENT_RETRIEVAL_EMBEDDING_PROVIDER = "fastembed"
DEFAULT_AGENT_RETRIEVAL_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_AGENT_RETRIEVAL_EMBEDDING_DEVICE = "cpu"
DEFAULT_AGENT_RETRIEVAL_EMBEDDING_BATCH_SIZE = 8
DEFAULT_AGENT_RETRIEVAL_MAX_HITS = 5
DEFAULT_AGENT_RETRIEVAL_RERANK_ENABLED = True
DEFAULT_VIDEO_GENERATION_CONCURRENCY = 1
DEFAULT_SUMMARY_CHUNK_CONCURRENCY = 1
DEFAULT_WEB_SEARCH_PROVIDER = "litellm"
DEFAULT_WEB_SEARCH_MODE = "native"
DEFAULT_WEB_SEARCH_CONTEXT_SIZE = "medium"
DEFAULT_WEB_SEARCH_MAX_RESULTS = 5
DEFAULT_WEB_SEARCH_TIMEOUT_SECONDS = 10
DEFAULT_CHAOXING_REQUEST_DELAY_SECONDS = 0.2
DEFAULT_CHAOXING_INIT_COURSE_DELAY_SECONDS = 0.3
SUPPORTED_HUGGINGFACE_ENV_KEYS = ("HF_ENDPOINT", "HF_HOME", "HUGGINGFACE_HUB_CACHE")


@dataclass(frozen=True)
class FasterWhisperSettings:
    device: str
    model_size: str
    compute_type: str
    transcription_mode: str
    models_dir: Path


@dataclass(frozen=True)
class AsrSettings:
    provider: str
    language: str
    transcript_enhancement_enabled: bool
    faster_whisper: FasterWhisperSettings


@dataclass(frozen=True)
class OpenAISettings:
    provider: str
    base_url: str
    model: str
    api_key: str


@dataclass(frozen=True)
class WorkspaceUiSettings:
    theme: str
    show_takeaways: bool


@dataclass(frozen=True)
class DebugSettings:
    mode: bool


@dataclass(frozen=True)
class AgentContextSettings:
    window_tokens: int
    answer_detail_level: str
    reasoning_effort: str
    talk_custom_prompt: str
    reserved_output_tokens: int
    warning_threshold_ratio: float
    compact_threshold_ratio: float
    blocking_threshold_ratio: float
    keep_tail_messages: int
    projection_max_tokens_ratio: float
    direct_summary_threshold_ratio: float
    planner_transport: str = "structured"


@dataclass(frozen=True)
class AgentRetrievalSettings:
    embedding_provider: str
    embedding_model: str
    embedding_device: str
    embedding_batch_size: int
    max_hits: int
    rerank_enabled: bool


@dataclass(frozen=True)
class GenerationConcurrencySettings:
    video_generation_concurrency: int
    summary_chunk_concurrency: int


@dataclass(frozen=True)
class WebSearchSettings:
    enabled: bool
    provider: str
    mode: str
    search_context_size: str
    max_results: int
    timeout_seconds: int


@dataclass(frozen=True)
class ChaoxingImportSettings:
    request_delay_seconds: float
    init_course_delay_seconds: float


@dataclass(frozen=True)
class ExternalImportSettings:
    chaoxing: ChaoxingImportSettings


@dataclass(frozen=True)
class AppSettings:
    asr: AsrSettings
    openai: OpenAISettings
    workspace_ui: WorkspaceUiSettings
    debug: DebugSettings
    agent_context: AgentContextSettings
    agent_retrieval: AgentRetrievalSettings
    generation: GenerationConcurrencySettings
    web_search: WebSearchSettings
    external_import: ExternalImportSettings


def load_settings(config_path: Path, root_dir: Path) -> AppSettings:
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    env_values = load_env_settings(root_dir)

    asr_payload = payload["asr"]
    provider = asr_payload["provider"].lower()
    if provider not in VALID_ASR_PROVIDERS:
        raise ValueError(f"Unsupported asr.provider: {provider}")

    faster_payload = asr_payload["faster_whisper"]
    faster_device = _normalize_device(
        faster_payload.get("device"),
        field_name="faster_whisper.device",
        default="auto",
    )

    faster_settings = FasterWhisperSettings(
        device=faster_device,
        model_size=faster_payload["model_size"],
        compute_type=faster_payload["compute_type"],
        transcription_mode=_normalize_transcription_mode(faster_payload.get("transcription_mode")),
        models_dir=root_dir / "data" / "models" / "faster-whisper",
    )

    asr_settings = AsrSettings(
        provider=provider,
        language=asr_payload.get("language", "zh"),
        transcript_enhancement_enabled=bool(asr_payload.get("transcript_enhancement_enabled", True)),
        faster_whisper=faster_settings,
    )

    openai_settings = OpenAISettings(
        provider=env_values.provider,
        base_url=normalize_openai_base_url(env_values.base_url),
        model=env_values.model,
        api_key=env_values.api_key,
    )

    workspace_ui_payload = payload.get("workspace_ui", {})
    workspace_ui_settings = WorkspaceUiSettings(
        theme=_normalize_theme(workspace_ui_payload.get("theme")),
        show_takeaways=bool(workspace_ui_payload.get("show_takeaways", True)),
    )
    debug_payload = payload.get("debug", {})
    debug_settings = DebugSettings(
        mode=bool(debug_payload.get("mode", False)),
    )
    agent_context_payload = payload.get("agent_context", {})
    agent_context_advanced_payload = agent_context_payload.get("advanced", {})
    agent_context_settings = AgentContextSettings(
        window_tokens=_normalize_positive_int(
            agent_context_payload.get("window_tokens"),
            default=DEFAULT_AGENT_CONTEXT_WINDOW_TOKENS,
        ),
        answer_detail_level=_normalize_choice(
            agent_context_payload.get("answer_detail_level"),
            default=DEFAULT_AGENT_ANSWER_DETAIL_LEVEL,
            allowed=VALID_ANSWER_DETAIL_LEVELS,
            field_name="agent_context.answer_detail_level",
        ),
        reasoning_effort=_normalize_choice(
            agent_context_payload.get("reasoning_effort"),
            default=DEFAULT_AGENT_REASONING_EFFORT,
            allowed=VALID_REASONING_EFFORTS,
            field_name="agent_context.reasoning_effort",
        ),
        talk_custom_prompt=_normalize_string(
            agent_context_payload.get("talk_custom_prompt"),
            default=DEFAULT_AGENT_TALK_CUSTOM_PROMPT,
        ),
        reserved_output_tokens=_normalize_positive_int(
            agent_context_advanced_payload.get("reserved_output_tokens"),
            default=DEFAULT_AGENT_RESERVED_OUTPUT_TOKENS,
        ),
        warning_threshold_ratio=_normalize_ratio(
            agent_context_advanced_payload.get("warning_threshold_ratio"),
            default=DEFAULT_AGENT_WARNING_THRESHOLD_RATIO,
        ),
        compact_threshold_ratio=_normalize_ratio(
            agent_context_advanced_payload.get("compact_threshold_ratio"),
            default=DEFAULT_AGENT_COMPACT_THRESHOLD_RATIO,
        ),
        blocking_threshold_ratio=_normalize_ratio(
            agent_context_advanced_payload.get("blocking_threshold_ratio"),
            default=DEFAULT_AGENT_BLOCKING_THRESHOLD_RATIO,
        ),
        keep_tail_messages=_normalize_positive_int(
            agent_context_advanced_payload.get("keep_tail_messages"),
            default=DEFAULT_AGENT_KEEP_TAIL_MESSAGES,
        ),
        projection_max_tokens_ratio=_normalize_ratio(
            agent_context_advanced_payload.get("projection_max_tokens_ratio"),
            default=DEFAULT_AGENT_PROJECTION_MAX_TOKENS_RATIO,
        ),
        direct_summary_threshold_ratio=_normalize_ratio(
            agent_context_advanced_payload.get("direct_summary_threshold_ratio"),
            default=DEFAULT_AGENT_DIRECT_SUMMARY_THRESHOLD_RATIO,
        ),
        planner_transport=_normalize_planner_transport(
            agent_context_advanced_payload.get("planner_transport")
        ),
    )
    agent_retrieval_payload = payload.get("agent_retrieval", {})
    agent_retrieval_settings = AgentRetrievalSettings(
        embedding_provider=_normalize_embedding_provider(
            agent_retrieval_payload.get("embedding_provider")
        ),
        embedding_model=_normalize_non_empty_string(
            agent_retrieval_payload.get("embedding_model"),
            default=DEFAULT_AGENT_RETRIEVAL_EMBEDDING_MODEL,
        ),
        embedding_device=_normalize_device(
            agent_retrieval_payload.get("embedding_device"),
            field_name="agent_retrieval.embedding_device",
            default=DEFAULT_AGENT_RETRIEVAL_EMBEDDING_DEVICE,
        ),
        embedding_batch_size=_normalize_positive_int(
            agent_retrieval_payload.get("embedding_batch_size"),
            default=DEFAULT_AGENT_RETRIEVAL_EMBEDDING_BATCH_SIZE,
        ),
        max_hits=_normalize_positive_int(
            agent_retrieval_payload.get("max_hits"),
            default=DEFAULT_AGENT_RETRIEVAL_MAX_HITS,
            field_name="agent_retrieval.max_hits",
        ),
        rerank_enabled=bool(
            agent_retrieval_payload.get("rerank_enabled", DEFAULT_AGENT_RETRIEVAL_RERANK_ENABLED)
        ),
    )
    generation_payload = payload.get("generation", {})
    generation_settings = GenerationConcurrencySettings(
        video_generation_concurrency=_normalize_positive_int(
            generation_payload.get("video_generation_concurrency"),
            default=DEFAULT_VIDEO_GENERATION_CONCURRENCY,
            field_name="generation.video_generation_concurrency",
        ),
        summary_chunk_concurrency=_normalize_positive_int(
            generation_payload.get("summary_chunk_concurrency"),
            default=DEFAULT_SUMMARY_CHUNK_CONCURRENCY,
            field_name="generation.summary_chunk_concurrency",
        ),
    )
    web_search_payload = payload.get("web_search", {})
    web_search_settings = WebSearchSettings(
        enabled=bool(web_search_payload.get("enabled", False)),
        provider=_normalize_choice(
            web_search_payload.get("provider"),
            default=DEFAULT_WEB_SEARCH_PROVIDER,
            allowed=VALID_WEB_SEARCH_PROVIDERS,
            field_name="web_search.provider",
        ),
        mode=_normalize_choice(
            web_search_payload.get("mode"),
            default=DEFAULT_WEB_SEARCH_MODE,
            allowed=VALID_WEB_SEARCH_MODES,
            field_name="web_search.mode",
        ),
        search_context_size=_normalize_choice(
            web_search_payload.get("search_context_size"),
            default=DEFAULT_WEB_SEARCH_CONTEXT_SIZE,
            allowed=VALID_WEB_SEARCH_CONTEXT_SIZES,
            field_name="web_search.search_context_size",
        ),
        max_results=_normalize_positive_int(
            web_search_payload.get("max_results"),
            default=DEFAULT_WEB_SEARCH_MAX_RESULTS,
            field_name="web_search.max_results",
        ),
        timeout_seconds=_normalize_positive_int(
            web_search_payload.get("timeout_seconds"),
            default=DEFAULT_WEB_SEARCH_TIMEOUT_SECONDS,
            field_name="web_search.timeout_seconds",
        ),
    )
    external_import_payload = payload.get("external_import", {})
    chaoxing_import_payload = external_import_payload.get("chaoxing", {})
    external_import_settings = ExternalImportSettings(
        chaoxing=ChaoxingImportSettings(
            request_delay_seconds=_normalize_non_negative_float(
                chaoxing_import_payload.get("request_delay_seconds"),
                default=DEFAULT_CHAOXING_REQUEST_DELAY_SECONDS,
                field_name="external_import.chaoxing.request_delay_seconds",
            ),
            init_course_delay_seconds=_normalize_non_negative_float(
                chaoxing_import_payload.get("init_course_delay_seconds"),
                default=DEFAULT_CHAOXING_INIT_COURSE_DELAY_SECONDS,
                field_name="external_import.chaoxing.init_course_delay_seconds",
            ),
        ),
    )

    return AppSettings(
        asr=asr_settings,
        openai=openai_settings,
        workspace_ui=workspace_ui_settings,
        debug=debug_settings,
        agent_context=agent_context_settings,
        agent_retrieval=agent_retrieval_settings,
        generation=generation_settings,
        web_search=web_search_settings,
        external_import=external_import_settings,
    )


def save_settings(config_path: Path, settings: AppSettings) -> None:
    atomic_write_text(config_path, _render_settings_toml(settings))


def replace_workspace_ui_settings(settings: AppSettings, workspace_ui: WorkspaceUiSettings) -> AppSettings:
    return replace(settings, workspace_ui=workspace_ui)


def replace_faster_whisper_model_size(settings: AppSettings, model_size: str) -> AppSettings:
    return replace(
        settings,
        asr=replace(
            settings.asr,
            faster_whisper=replace(settings.asr.faster_whisper, model_size=model_size),
        ),
    )


def replace_transcript_enhancement_enabled(settings: AppSettings, transcript_enhancement_enabled: bool) -> AppSettings:
    return replace(settings, asr=replace(settings.asr, transcript_enhancement_enabled=transcript_enhancement_enabled))


def replace_faster_whisper_transcription_mode(settings: AppSettings, transcription_mode: str) -> AppSettings:
    normalized_mode = _normalize_transcription_mode(transcription_mode)
    return replace(
        settings,
        asr=replace(
            settings.asr,
            faster_whisper=replace(settings.asr.faster_whisper, transcription_mode=normalized_mode),
        ),
    )


def replace_agent_retrieval_embedding_device(settings: AppSettings, embedding_device: str) -> AppSettings:
    normalized_device = _normalize_device(
        embedding_device,
        field_name="agent_retrieval.embedding_device",
        default=DEFAULT_AGENT_RETRIEVAL_EMBEDDING_DEVICE,
    )
    return replace(
        settings,
        agent_retrieval=replace(
            settings.agent_retrieval,
            embedding_device=normalized_device,
        ),
    )


def replace_agent_retrieval_runtime_settings(
    settings: AppSettings,
    *,
    embedding_device: str,
    max_hits: int,
    rerank_enabled: bool,
) -> AppSettings:
    normalized_device = _normalize_device(
        embedding_device,
        field_name="agent_retrieval.embedding_device",
        default=DEFAULT_AGENT_RETRIEVAL_EMBEDDING_DEVICE,
    )
    normalized_max_hits = _normalize_positive_int(
        max_hits,
        default=DEFAULT_AGENT_RETRIEVAL_MAX_HITS,
        field_name="agent_retrieval.max_hits",
    )
    return replace(
        settings,
        agent_retrieval=replace(
            settings.agent_retrieval,
            embedding_device=normalized_device,
            max_hits=normalized_max_hits,
            rerank_enabled=bool(rerank_enabled),
        ),
    )


def replace_agent_context_window_tokens(settings: AppSettings, window_tokens: int) -> AppSettings:
    normalized_window_tokens = _normalize_positive_int(
        window_tokens,
        default=DEFAULT_AGENT_CONTEXT_WINDOW_TOKENS,
    )
    return replace(
        settings,
        agent_context=replace(
            settings.agent_context,
            window_tokens=normalized_window_tokens,
        ),
    )


def replace_agent_context_answer_detail_level(settings: AppSettings, answer_detail_level: str) -> AppSettings:
    normalized_answer_detail_level = _normalize_choice(
        answer_detail_level,
        default=DEFAULT_AGENT_ANSWER_DETAIL_LEVEL,
        allowed=VALID_ANSWER_DETAIL_LEVELS,
        field_name="agent_context.answer_detail_level",
    )
    return replace(
        settings,
        agent_context=replace(
            settings.agent_context,
            answer_detail_level=normalized_answer_detail_level,
        ),
    )


def replace_agent_context_reasoning_effort(settings: AppSettings, reasoning_effort: str) -> AppSettings:
    normalized_reasoning_effort = _normalize_choice(
        reasoning_effort,
        default=DEFAULT_AGENT_REASONING_EFFORT,
        allowed=VALID_REASONING_EFFORTS,
        field_name="agent_context.reasoning_effort",
    )
    return replace(
        settings,
        agent_context=replace(
            settings.agent_context,
            reasoning_effort=normalized_reasoning_effort,
        ),
    )


def replace_agent_context_talk_custom_prompt(settings: AppSettings, talk_custom_prompt: str) -> AppSettings:
    return replace(
        settings,
        agent_context=replace(
            settings.agent_context,
            talk_custom_prompt=_normalize_string(
                talk_custom_prompt,
                default=DEFAULT_AGENT_TALK_CUSTOM_PROMPT,
            ),
        ),
    )


def replace_video_generation_concurrency(settings: AppSettings, video_generation_concurrency: int) -> AppSettings:
    normalized_concurrency = _normalize_positive_int(
        video_generation_concurrency,
        default=DEFAULT_VIDEO_GENERATION_CONCURRENCY,
        field_name="generation.video_generation_concurrency",
    )
    return replace(
        settings,
        generation=replace(
            settings.generation,
            video_generation_concurrency=normalized_concurrency,
        ),
    )


def replace_web_search_enabled(settings: AppSettings, web_search_enabled: bool) -> AppSettings:
    return replace(
        settings,
        web_search=replace(settings.web_search, enabled=bool(web_search_enabled)),
    )


def replace_chaoxing_import_settings(
    settings: AppSettings,
    *,
    request_delay_seconds: float,
    init_course_delay_seconds: float,
) -> AppSettings:
    return replace(
        settings,
        external_import=replace(
            settings.external_import,
            chaoxing=ChaoxingImportSettings(
                request_delay_seconds=_normalize_non_negative_float(
                    request_delay_seconds,
                    default=DEFAULT_CHAOXING_REQUEST_DELAY_SECONDS,
                    field_name="external_import.chaoxing.request_delay_seconds",
                ),
                init_course_delay_seconds=_normalize_non_negative_float(
                    init_course_delay_seconds,
                    default=DEFAULT_CHAOXING_INIT_COURSE_DELAY_SECONDS,
                    field_name="external_import.chaoxing.init_course_delay_seconds",
                ),
            ),
        ),
    )


def replace_openai_settings(
    settings: AppSettings,
    *,
    provider: str,
    base_url: str,
    model: str,
) -> AppSettings:
    return replace(
        settings,
        openai=OpenAISettings(
            provider=provider,
            base_url=normalize_openai_base_url(base_url),
            model=model,
            api_key=settings.openai.api_key,
        ),
    )


def _normalize_theme(value: object) -> str:
    if isinstance(value, str) and value in VALID_THEMES:
        return value
    return "light"


def _normalize_transcription_mode(value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_TRANSCRIPTION_MODES:
            return normalized
    return "fast"


def normalize_openai_base_url(value: str) -> str:
    return normalize_provider_base_url(value)


def apply_runtime_env_overrides(root_dir: Path) -> None:
    values = _load_dotenv(root_dir / ".env")
    for key in SUPPORTED_HUGGINGFACE_ENV_KEYS:
        if key not in values:
            continue
        value = values[key].strip()
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


def _render_settings_toml(settings: AppSettings) -> str:
    lines = [
        "[asr]",
        f'provider = "{settings.asr.provider}"',
        f'language = "{settings.asr.language}"',
        f"transcript_enhancement_enabled = {_toml_bool(settings.asr.transcript_enhancement_enabled)}",
        "",
        "[asr.faster_whisper]",
        f'device = "{settings.asr.faster_whisper.device}"',
        f'model_size = "{settings.asr.faster_whisper.model_size}"',
        f'compute_type = "{settings.asr.faster_whisper.compute_type}"',
        f'transcription_mode = "{settings.asr.faster_whisper.transcription_mode}"',
        "",
        "[workspace_ui]",
        f'theme = "{settings.workspace_ui.theme}"',
        f"show_takeaways = {_toml_bool(settings.workspace_ui.show_takeaways)}",
        "",
        "[debug]",
        f"mode = {_toml_bool(settings.debug.mode)}",
        "",
        "[agent_context]",
        f"window_tokens = {settings.agent_context.window_tokens}",
        f'answer_detail_level = "{settings.agent_context.answer_detail_level}"',
        f'reasoning_effort = "{settings.agent_context.reasoning_effort}"',
        f"talk_custom_prompt = {_toml_string(settings.agent_context.talk_custom_prompt)}",
        "",
        "[agent_context.advanced]",
        f"reserved_output_tokens = {settings.agent_context.reserved_output_tokens}",
        f"warning_threshold_ratio = {settings.agent_context.warning_threshold_ratio}",
        f"compact_threshold_ratio = {settings.agent_context.compact_threshold_ratio}",
        f"blocking_threshold_ratio = {settings.agent_context.blocking_threshold_ratio}",
        f"keep_tail_messages = {settings.agent_context.keep_tail_messages}",
        f"projection_max_tokens_ratio = {settings.agent_context.projection_max_tokens_ratio}",
        f"direct_summary_threshold_ratio = {settings.agent_context.direct_summary_threshold_ratio}",
        f'planner_transport = "{settings.agent_context.planner_transport}"',
        "",
        "[agent_retrieval]",
        f'embedding_provider = "{settings.agent_retrieval.embedding_provider}"',
        f'embedding_model = "{settings.agent_retrieval.embedding_model}"',
        f'embedding_device = "{settings.agent_retrieval.embedding_device}"',
        f"embedding_batch_size = {settings.agent_retrieval.embedding_batch_size}",
        f"max_hits = {settings.agent_retrieval.max_hits}",
        f"rerank_enabled = {_toml_bool(settings.agent_retrieval.rerank_enabled)}",
        "",
        "[generation]",
        f"video_generation_concurrency = {settings.generation.video_generation_concurrency}",
        f"summary_chunk_concurrency = {settings.generation.summary_chunk_concurrency}",
        "",
        "[web_search]",
        f"enabled = {_toml_bool(settings.web_search.enabled)}",
        f'provider = "{settings.web_search.provider}"',
        f'mode = "{settings.web_search.mode}"',
        f'search_context_size = "{settings.web_search.search_context_size}"',
        f"max_results = {settings.web_search.max_results}",
        f"timeout_seconds = {settings.web_search.timeout_seconds}",
        "",
        "[external_import.chaoxing]",
        f"request_delay_seconds = {settings.external_import.chaoxing.request_delay_seconds}",
        f"init_course_delay_seconds = {settings.external_import.chaoxing.init_course_delay_seconds}",
        "",
    ]
    return "\n".join(lines)


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _normalize_string(value: object, *, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return default


def _normalize_positive_int(value: object, *, default: int, field_name: str | None = None) -> int:
    if value is None:
        return default
    if isinstance(value, int) and value > 0:
        return value
    if field_name is not None:
        raise ValueError(f"{field_name} 必须是大于 0 的整数。")
    return default


def _normalize_non_negative_float(value: object, *, default: float, field_name: str) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是大于等于 0 的数字。")
    if isinstance(value, (int, float)):
        normalized = float(value)
        if normalized >= 0:
            return normalized
    raise ValueError(f"{field_name} 必须是大于等于 0 的数字。")


def _normalize_ratio(value: object, *, default: float) -> float:
    if isinstance(value, (int, float)):
        normalized = float(value)
        if 0 < normalized < 1:
            return normalized
    return default


def _normalize_planner_transport(value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_PLANNER_TRANSPORTS:
            return normalized
    return "structured"


def _normalize_choice(value: object, *, default: str, allowed: set[str], field_name: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"Unsupported {field_name}: {value!r}. Supported values: {', '.join(sorted(allowed))}")
    normalized = value.strip().lower()
    if normalized in allowed:
        return normalized
    raise ValueError(f"Unsupported {field_name}: {value!r}. Supported values: {', '.join(sorted(allowed))}")


def _normalize_embedding_provider(value: object) -> str:
    normalized = _normalize_non_empty_string(
        value,
        default=DEFAULT_AGENT_RETRIEVAL_EMBEDDING_PROVIDER,
    )
    if normalized != "fastembed":
        raise ValueError(f"Unsupported agent_retrieval.embedding_provider: {normalized}")
    return normalized


def _normalize_device(
    value: object,
    *,
    field_name: str,
    default: str,
) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(
            f"Unsupported {field_name}: {value!r}. Supported values: auto, cpu, gpu"
        )

    normalized = value.strip().lower()
    if normalized == "cuda":
        return "gpu"
    if normalized in VALID_DEVICES:
        return normalized
    raise ValueError(
        f"Unsupported {field_name}: {value!r}. Supported values: auto, cpu, gpu"
    )


def _normalize_non_empty_string(value: object, *, default: str) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return default


@dataclass(frozen=True)
class EnvSettings:
    provider: str
    base_url: str
    model: str
    api_key: str
    hf_endpoint: str = ""


def load_env_settings(root_dir: Path) -> EnvSettings:
    values = _load_dotenv(root_dir / ".env")
    return EnvSettings(
        provider=_normalize_env_provider(values.get("OPENAI_PROVIDER")),
        base_url=normalize_openai_base_url(values.get("OPENAI_BASE_URL", "").strip()),
        model=values.get("OPENAI_MODEL", "").strip(),
        api_key=values.get("OPENAI_API_KEY", "").strip(),
        hf_endpoint=values.get("HF_ENDPOINT", "").strip(),
    )


def save_env_settings(root_dir: Path, settings: EnvSettings) -> None:
    dotenv_path = root_dir / ".env"
    lines = dotenv_path.read_text(encoding="utf-8").splitlines() if dotenv_path.exists() else []
    replacements = {
        "OPENAI_PROVIDER": settings.provider,
        "OPENAI_BASE_URL": normalize_openai_base_url(settings.base_url),
        "OPENAI_MODEL": settings.model,
        "OPENAI_API_KEY": settings.api_key,
        "HF_ENDPOINT": settings.hf_endpoint.strip(),
    }
    next_lines: list[str] = []
    seen_keys: set[str] = set()

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            next_lines.append(raw_line)
            continue

        key, _ = raw_line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in replacements:
            next_lines.append(f"{normalized_key}={replacements[normalized_key]}")
            seen_keys.add(normalized_key)
        else:
            next_lines.append(raw_line)

    for key, value in replacements.items():
        if key not in seen_keys:
            next_lines.append(f"{key}={value}")

    atomic_write_text(dotenv_path, "\n".join(next_lines).rstrip() + "\n")


def _load_dotenv(dotenv_path: Path) -> dict[str, str]:
    if not dotenv_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        normalized_value = value.strip().strip('"').strip("'")
        if normalized_key:
            values[normalized_key] = normalized_value
    return values


def _normalize_env_provider(value: object) -> str:
    if not isinstance(value, str):
        return "openai"
    normalized = value.strip().lower()
    if not normalized or normalized == "openai_compatible":
        return "openai"
    if normalized == "qwen":
        return "dashscope"
    return normalized
