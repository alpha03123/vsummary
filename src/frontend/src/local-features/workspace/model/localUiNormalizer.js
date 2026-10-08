const validLlmProviders = new Set([
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
]);
export function normalizeUiSettings(value) {
  const record = value && typeof value === "object" ? value : {};
  const autoGenerateArtifacts = Array.isArray(record.autoGenerateArtifacts)
    ? [...new Set(record.autoGenerateArtifacts.filter((item) => ["mindmap", "knowledge_cards"].includes(item)))]
    : [];
  return {
    showTakeaways: typeof record.showTakeaways === "boolean" ? record.showTakeaways : true,
    theme: record.theme === "dark" ? "dark" : "light",
    transcriptEnhancementEnabled:
      typeof record.transcriptEnhancementEnabled === "boolean" ? record.transcriptEnhancementEnabled : true,
    asrProvider:
      record.asrProvider === "aliyun_bailian" || record.asrProvider === "whisper_cpp"
        ? record.asrProvider
        : "faster_whisper",
    asrModelQuality:
      typeof record.asrModelQuality === "string" && record.asrModelQuality.trim()
        ? record.asrModelQuality.trim()
        : "large-v3-turbo",
    transcriptionMode:
      record.transcriptionMode === "accurate" || record.transcriptionMode === "balanced"
        ? record.transcriptionMode
        : "fast",
    asrCloudModel:
      typeof record.asrCloudModel === "string" && record.asrCloudModel.trim()
        ? record.asrCloudModel.trim()
        : "paraformer-v2",
    asrBaseUrl:
      typeof record.asrBaseUrl === "string" && record.asrBaseUrl.trim()
        ? record.asrBaseUrl.trim()
        : "https://dashscope.aliyuncs.com",
    asrApiKey: typeof record.asrApiKey === "string" ? record.asrApiKey : "",
    hasAsrApiKey: typeof record.hasAsrApiKey === "boolean" ? record.hasAsrApiKey : false,
    asrApiKeyMasked: typeof record.asrApiKeyMasked === "string" ? record.asrApiKeyMasked : "",
    runtimeCapabilities: normalizeRuntimeCapabilities(record.runtimeCapabilities),
    ragEmbeddingDevice:
      record.ragEmbeddingDevice === "gpu" || record.ragEmbeddingDevice === "auto"
        ? record.ragEmbeddingDevice
        : "cpu",
    ragMaxHits:
      typeof record.ragMaxHits === "number" && Number.isInteger(record.ragMaxHits) && record.ragMaxHits > 0
        ? record.ragMaxHits
        : 5,
    ragRerankEnabled:
      typeof record.ragRerankEnabled === "boolean" ? record.ragRerankEnabled : true,
    webSearchEnabled:
      typeof record.webSearchEnabled === "boolean" ? record.webSearchEnabled : false,
    llmProvider: validLlmProviders.has(record.llmProvider) ? record.llmProvider : "openai",
    openaiBaseUrl:
      typeof record.openaiBaseUrl === "string" && record.openaiBaseUrl.trim()
        ? record.openaiBaseUrl.trim()
        : "",
    openaiModel:
      typeof record.openaiModel === "string" && record.openaiModel.trim()
        ? record.openaiModel.trim()
        : "gpt-5.4",
    hfEndpoint:
      typeof record.hfEndpoint === "string"
        ? record.hfEndpoint.trim()
        : "https://hf-mirror.com",
    openaiApiKey: typeof record.openaiApiKey === "string" ? record.openaiApiKey : "",
    hasOpenaiApiKey: typeof record.hasOpenaiApiKey === "boolean" ? record.hasOpenaiApiKey : false,
    openaiApiKeyMasked: typeof record.openaiApiKeyMasked === "string" ? record.openaiApiKeyMasked : "",
    windowTokens:
      typeof record.windowTokens === "number" && Number.isInteger(record.windowTokens) && record.windowTokens > 0
        ? record.windowTokens
        : 1000000,
    answerDetailLevel:
      record.answerDetailLevel === "short" || record.answerDetailLevel === "long"
        ? record.answerDetailLevel
        : "medium",
    reasoningEffort:
      record.reasoningEffort === "low" || record.reasoningEffort === "medium" || record.reasoningEffort === "high"
        ? record.reasoningEffort
        : "none",
    talkCustomPrompt: typeof record.talkCustomPrompt === "string" ? record.talkCustomPrompt : "",
    videoGenerationConcurrency:
      typeof record.videoGenerationConcurrency === "number"
        && Number.isInteger(record.videoGenerationConcurrency)
        && record.videoGenerationConcurrency > 0
        ? record.videoGenerationConcurrency
        : 1,
    chapterVisualMode:
      record.chapterVisualMode === "off" ? "off" : "screenshots",
    maxVisualInputImages:
      typeof record.maxVisualInputImages === "number" && Number.isInteger(record.maxVisualInputImages) && record.maxVisualInputImages > 0
        ? record.maxVisualInputImages
        : 10,
    noteVisualMode: ["off", "screenshots"].includes(record.noteVisualMode) ? record.noteVisualMode : "off",
    aiSummaryMultimodalEnabled: typeof record.aiSummaryMultimodalEnabled === "boolean" ? record.aiSummaryMultimodalEnabled : false,
    mindmapVisualInput: ["none", "evidence", "frames"].includes(record.mindmapVisualInput) ? record.mindmapVisualInput : "none",
    cardsVisualInput: ["none", "evidence", "frames"].includes(record.cardsVisualInput) ? record.cardsVisualInput : "none",
    noteMaxImages: typeof record.noteMaxImages === "number" && Number.isInteger(record.noteMaxImages) && record.noteMaxImages > 0 ? record.noteMaxImages : 10,
    autoGenerateArtifacts,
    chaoxingRequestDelaySeconds: normalizeNonNegativeNumber(record.chaoxingRequestDelaySeconds, 0.2),
    chaoxingInitCourseDelaySeconds: normalizeNonNegativeNumber(record.chaoxingInitCourseDelaySeconds, 0.3),
  };
}
function normalizeRuntimeCapabilities(value) {
  if (!value || typeof value !== "object") {
    return null;
  }
  return {
    platform: typeof value.platform === "string" ? value.platform : "unknown",
    accelerator: typeof value.accelerator === "string" ? value.accelerator : "unknown",
    fasterWhisperAvailable: value.faster_whisper_available === true || value.fasterWhisperAvailable === true,
    gpuEmbeddingAvailable: value.gpu_embedding_available === true || value.gpuEmbeddingAvailable === true,
    unavailableReason:
      typeof value.unavailable_reason === "string"
        ? value.unavailable_reason
        : typeof value.unavailableReason === "string"
          ? value.unavailableReason
          : "",
  };
}

function normalizeNonNegativeNumber(value, fallback) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : fallback;
}
