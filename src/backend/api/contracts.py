from __future__ import annotations

from pydantic import BaseModel


class GenerateVideoSummaryRequest(BaseModel):
    transcript_enhancement_enabled: bool | None = None


class CreateVideoNoteRequest(BaseModel):
    title: str
    content: str
    source: str = "manual"


class UpdateVideoNoteRequest(BaseModel):
    title: str
    content: str


class WorkspaceSettingsResponse(BaseModel):
    theme: str
    show_takeaways: bool
    transcript_enhancement_enabled: bool
    asr_model_quality: str
    transcription_mode: str
    rag_embedding_device: str
    rag_max_hits: int
    rag_rerank_enabled: bool
    window_tokens: int
    video_generation_concurrency: int


class UpdateWorkspaceSettingsRequest(BaseModel):
    theme: str
    show_takeaways: bool
    transcript_enhancement_enabled: bool
    asr_model_quality: str
    transcription_mode: str
    rag_embedding_device: str
    rag_max_hits: int
    rag_rerank_enabled: bool
    window_tokens: int
    video_generation_concurrency: int


class ProviderSettingsResponse(BaseModel):
    llm_provider: str
    openai_base_url: str
    openai_model: str
    has_openai_api_key: bool
    openai_api_key_masked: str
    hf_endpoint: str


class UpdateProviderSettingsRequest(BaseModel):
    llm_provider: str
    openai_base_url: str
    openai_model: str
    openai_api_key: str | None = None
    hf_endpoint: str | None = None


class TestProviderSettingsResponse(BaseModel):
    ok: bool
    message: str


class FasterWhisperModelResponse(BaseModel):
    id: str
    label: str
    downloaded: bool
    current: bool
    recommended: bool


class RagModelResponse(BaseModel):
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
