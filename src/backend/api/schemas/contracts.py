"""API 请求/响应的 Pydantic 模型合约。

所有对外暴露的 DTO 模式集中定义在此处，供 API 路由实现、OpenAPI 文档
自动生成以及集成测试复用。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

class GenerateVideoSummaryRequest(BaseModel):
    """请求生成单个视频的结构化总结。

    transcript_enhancement_enabled 为 None 时沿用默认配置。
    """

    transcript_enhancement_enabled: bool | None = None


class GenerateMindmapRequest(BaseModel):
    """请求生成思维导图的选项。"""

    max_depth: int | None = Field(default=None, ge=2, le=5)


class GenerateSeriesSummariesRequest(BaseModel):
    """请求批量生成一个系列下所有视频的总结。

    run_id 用于幂等去重：相同 run_id 的重复请求会被忽略。
    """

    transcript_enhancement_enabled: bool | None = None
    run_id: str | None = None


class CancelSeriesSummariesRequest(BaseModel):
    """请求取消正在进行的系列批量生成任务。"""

    run_id: str | None = None


class AgentSeriesCreateRequest(BaseModel):
    """请求创建一个供 Agent 编排的空链接型系列。"""

    title: str = Field(max_length=200)


class AgentSeriesProcessRequest(BaseModel):
    """请求后台处理一个 Agent 系列或其中一个视频。"""

    video_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None
    transcript_enhancement_enabled: bool | None = None


class CreateVideoNoteRequest(BaseModel):
    """创建视频笔记的请求体。

    source 区分来源："manual" 为用户手写，"ai" 为 LLM 生成。
    """

    title: str
    content: str
    source: str = "manual"


class UpdateVideoNoteRequest(BaseModel):
    """更新视频笔记的请求体。"""

    title: str
    content: str


class UpdateVideoSummaryRequest(BaseModel):
    """更新用户修订后的原始 Markdown 总结。"""

    markdown: str


class UpdateVideoTranscriptRequest(BaseModel):
    """更新用户修订后的原始 Markdown 转写。"""

    markdown: str


class RenameTitleRequest(BaseModel):
    """更新系列或视频的展示标题。"""

    title: str = Field(min_length=1, max_length=200)


class LocalMediaPathImportRequest(BaseModel):
    """从运行后端的本机文件系统导入媒体。"""

    source_paths: list[str] = Field(min_length=1)
    storage_mode: str | None = None


class LocalMediaSeriesPathImportRequest(LocalMediaPathImportRequest):
    """从本机路径创建系列的请求。"""

    series_title: str = Field(min_length=1, max_length=200)


class RuntimeCapabilitiesResponse(BaseModel):
    """本机可用于本地 ASR 与 embedding 的硬件能力。"""

    platform: str
    accelerator: str
    faster_whisper_available: bool
    gpu_embedding_available: bool
    unavailable_reason: str | None = None


class WorkspaceSettingsResponse(BaseModel):
    """工作区全局设置的响应模型。

    包含前端 UI 主题、ASR 质量、RAG 参数、回答详细度、并发数等完整配置。
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
    answer_detail_level: str = "medium"
    reasoning_effort: str = "none"
    talk_custom_prompt: str = ""
    video_generation_concurrency: int
    web_search_enabled: bool
    chaoxing_request_delay_seconds: float = 0.2
    chaoxing_init_course_delay_seconds: float = 0.3
    runtime_capabilities: RuntimeCapabilitiesResponse


class UpdateWorkspaceSettingsRequest(BaseModel):
    """更新工作区全局设置的请求体。

    前端提交整个配置快照，后端全量覆盖。
    """

    theme: str
    show_takeaways: bool
    layout_mode: str
    transcript_enhancement_enabled: bool
    asr_provider: str = "faster_whisper"
    asr_model_quality: str
    transcription_mode: str
    asr_cloud_model: str = "paraformer-v2"
    asr_base_url: str = "https://dashscope.aliyuncs.com"
    asr_api_key: str | None = None
    rag_embedding_device: str
    rag_max_hits: int
    rag_rerank_enabled: bool
    window_tokens: int
    answer_detail_level: str = "medium"
    reasoning_effort: str = "none"
    talk_custom_prompt: str = ""
    video_generation_concurrency: int
    web_search_enabled: bool
    chaoxing_request_delay_seconds: float = 0.2
    chaoxing_init_course_delay_seconds: float = 0.3


class ProviderSettingsResponse(BaseModel):
    """LLM Provider 配置的响应模型。

    返回脱敏后的 API Key（仅展示前后各 4 位），避免明文泄露。
    """

    llm_provider: str
    openai_base_url: str
    openai_model: str
    has_openai_api_key: bool
    openai_api_key_masked: str
    hf_endpoint: str


class ProviderUsageTotalsResponse(BaseModel):
    """LLM token 用量总计。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ProviderUsageCategoryResponse(BaseModel):
    """按 generation/chat 分类的 LLM token 用量。"""

    category: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ProviderUsageProviderResponse(BaseModel):
    """按 provider + base_url + model 聚合的 LLM token 用量。"""

    provider: str
    base_url: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ProviderUsageRecordResponse(BaseModel):
    """最近一次 LLM token 用量记录。"""

    created_at: str
    category: str
    provider: str
    base_url: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ProviderUsageTimelineBucketResponse(BaseModel):
    """按时间桶聚合的 generation/chat token 用量。"""

    started_at: str
    generation_tokens: int
    chat_tokens: int
    total_tokens: int


class ProviderUsageResponse(BaseModel):
    """模型供应商页的 LLM token 用量统计响应。"""

    range: str
    total: ProviderUsageTotalsResponse
    by_category: list[ProviderUsageCategoryResponse]
    by_provider: list[ProviderUsageProviderResponse]
    recent: list[ProviderUsageRecordResponse]
    timeline_granularity: str
    timeline: list[ProviderUsageTimelineBucketResponse]


class ProviderApiKeyResponse(BaseModel):
    """明文 API Key 的响应模型。

    仅在用户主动请求查看/导出时返回，正常 settings 接口使用脱敏版本。
    """

    openai_api_key: str


class AsrApiKeyResponse(BaseModel):
    """明文 ASR API Key 的响应模型。"""

    asr_api_key: str


class TestAsrSettingsRequest(BaseModel):
    """测试 ASR provider 连通性的请求体。"""

    asr_provider: str = "faster_whisper"
    asr_cloud_model: str = "paraformer-v2"
    asr_base_url: str = "https://dashscope.aliyuncs.com"
    asr_api_key: str | None = None


class UpdateProviderSettingsRequest(BaseModel):
    """更新 LLM Provider 配置的请求体。

    openai_api_key 为 None 时表示不更新 Key（保持原有值）。
    """

    llm_provider: str
    openai_base_url: str
    openai_model: str
    openai_api_key: str | None = None
    hf_endpoint: str | None = None


class TestProviderSettingsResponse(BaseModel):
    """Provider 连通性测试的响应模型。

    ok 为 True 表示 API Key 有效、模型可达；message 包含成功/失败详情。
    """

    ok: bool
    message: str


class FasterWhisperModelResponse(BaseModel):
    """单个 faster-whisper 模型的状态快照。

    供前端展示模型下载进度、选中状态与推荐标记。
    """

    id: str
    label: str
    downloaded: bool
    current: bool
    recommended: bool
    status: str = "idle"
    progress: float | None = None
    detail: str | None = None
    error: str | None = None


class RagModelResponse(BaseModel):
    """单个 RAG 嵌入模型的状态快照。

    供前端展示嵌入模型下载进度、用途说明与错误信息。
    """

    key: str
    label: str
    repo_id: str
    local_path: str
    purpose: str
    downloaded: bool
    status: str
    progress: float | None = None
    detail: str | None = None
    error: str | None = None
